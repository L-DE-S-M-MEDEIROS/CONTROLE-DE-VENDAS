from __future__ import annotations

import base64
import ctypes
import json
import os
import threading
import time
import urllib.error
import urllib.request
from ctypes import wintypes
from pathlib import Path

from .cloud_config import AUTHORIZED_EMAIL, SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL


class CloudError(RuntimeError):
    """A safe, user-facing cloud synchronization error."""


class NotConnectedError(CloudError):
    pass


class CloudConflictError(CloudError):
    pass


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _protect_for_current_windows_user(data: bytes) -> bytes:
    if os.name != "nt":
        return base64.b64encode(data)
    buffer = ctypes.create_string_buffer(data)
    source = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    target = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    if not crypt32.CryptProtectData(
        ctypes.byref(source),
        "Vendas PRO Supabase",
        None,
        None,
        None,
        0x01,
        ctypes.byref(target),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)


def _unprotect_for_current_windows_user(data: bytes) -> bytes:
    if os.name != "nt":
        return base64.b64decode(data)
    buffer = ctypes.create_string_buffer(data)
    source = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    target = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    if not crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0x01, ctypes.byref(target)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)


class SessionStore:
    """Persist refresh tokens encrypted for the current Windows account."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> dict | None:
        try:
            plain = _unprotect_for_current_windows_user(self.path.read_bytes())
            session = json.loads(plain.decode("utf-8"))
            return session if isinstance(session, dict) else None
        except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    def save(self, session: dict):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        protected = _protect_for_current_windows_user(
            json.dumps(session, separators=(",", ":")).encode("utf-8")
        )
        temporary = self.path.with_suffix(".tmp")
        temporary.write_bytes(protected)
        temporary.replace(self.path)

    def clear(self):
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


class SupabaseClient:
    def __init__(self, session_path: str | Path):
        self.session_store = SessionStore(session_path)
        self.session = self.session_store.load()
        self._session_lock = threading.RLock()

    @property
    def connected_email(self) -> str | None:
        if not self.session:
            return None
        user = self.session.get("user") or {}
        return str(user.get("email") or "").lower() or None

    @property
    def has_session(self) -> bool:
        return bool(self.session and self.session.get("refresh_token"))

    @staticmethod
    def _error_message(payload, status: int) -> str:
        if isinstance(payload, dict):
            message = (
                payload.get("msg")
                or payload.get("message")
                or payload.get("error_description")
                or payload.get("error")
            )
            code = payload.get("error_code") or payload.get("code")
            if code in {"invalid_credentials", "email_not_confirmed"}:
                return "E-mail ou senha inválidos para a conta autorizada."
            if message:
                return str(message)
        if status in {401, 403}:
            return "A sessão não tem autorização para acessar os dados da empresa."
        return "O Supabase não conseguiu concluir a solicitação."

    def _request_json(
        self,
        method: str,
        url: str,
        payload=None,
        *,
        access_token: str | None = None,
        headers: dict | None = None,
        timeout: int = 20,
    ):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request_headers = {
            "apikey": SUPABASE_PUBLISHABLE_KEY,
            "Accept": "application/json",
            "User-Agent": "Vendas-PRO-Desktop/1",
        }
        if body is not None:
            request_headers["Content-Type"] = "application/json"
        if access_token:
            request_headers["Authorization"] = f"Bearer {access_token}"
        if headers:
            request_headers.update(headers)
        request = urllib.request.Request(
            url, data=body, headers=request_headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                error_payload = json.loads(raw.decode("utf-8")) if raw else None
            except (json.JSONDecodeError, UnicodeDecodeError):
                error_payload = None
            raw_message = ""
            if isinstance(error_payload, dict):
                raw_message = str(
                    error_payload.get("message") or error_payload.get("msg") or ""
                )
            if "VENDAS_PRO_CONFLICT" in raw_message:
                raise CloudConflictError(
                    "Outra máquina alterou o mesmo registro antes desta sincronização."
                ) from exc
            raise CloudError(self._error_message(error_payload, exc.code)) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise CloudError(
                "Sem conexão com o Supabase. Os dados continuam salvos neste computador e serão sincronizados depois."
            ) from exc

    def login(self, email: str, password: str):
        normalized = str(email).strip().lower()
        if normalized != AUTHORIZED_EMAIL:
            raise CloudError("Somente o e-mail autorizado da empresa pode conectar.")
        if not password:
            raise CloudError("Informe a senha da conta autorizada.")
        response = self._request_json(
            "POST",
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            {"email": normalized, "password": password},
        )
        returned_email = str((response.get("user") or {}).get("email") or "").lower()
        if returned_email != AUTHORIZED_EMAIL:
            raise CloudError("A conta autenticada não é a conta autorizada da empresa.")
        self._save_session(response)
        return response

    def _save_session(self, response: dict):
        session = {
            "access_token": response["access_token"],
            "refresh_token": response["refresh_token"],
            "expires_at": int(
                response.get("expires_at")
                or (time.time() + int(response.get("expires_in", 3600)))
            ),
            "user": response.get("user") or (self.session or {}).get("user") or {},
        }
        with self._session_lock:
            self.session = session
            self.session_store.save(session)

    def _access_token(self) -> str:
        with self._session_lock:
            if not self.session or not self.session.get("refresh_token"):
                raise NotConnectedError("Conecte a conta da empresa para sincronizar.")
            if int(self.session.get("expires_at", 0)) > time.time() + 90:
                return str(self.session["access_token"])
            response = self._request_json(
                "POST",
                f"{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token",
                {"refresh_token": self.session["refresh_token"]},
            )
            returned_email = str((response.get("user") or {}).get("email") or "").lower()
            if returned_email != AUTHORIZED_EMAIL:
                self.session_store.clear()
                self.session = None
                raise CloudError("A sessão não pertence à conta autorizada da empresa.")
            self._save_session(response)
            return str(self.session["access_token"])

    def logout(self):
        try:
            token = self._access_token()
            self._request_json(
                "POST", f"{SUPABASE_URL}/auth/v1/logout", access_token=token
            )
        except CloudError:
            pass
        finally:
            with self._session_lock:
                self.session = None
                self.session_store.clear()

    def _rest(self, method: str, path: str, payload=None, headers: dict | None = None):
        token = self._access_token()
        return self._request_json(
            method,
            f"{SUPABASE_URL}/rest/v1/{path}",
            payload,
            access_token=token,
            headers=headers,
        )

    def upsert(self, table: str, record: dict):
        self._rest(
            "POST",
            f"{table}?on_conflict=id",
            record,
            {"Prefer": "resolution=merge-duplicates,return=minimal"},
        )

    def save_product(self, record: dict) -> int:
        revision = self._rest(
            "POST", "rpc/controle_vendas_save_product", {"product_record": record}
        )
        return int(revision)

    def save_client(self, record: dict) -> int:
        revision = self._rest(
            "POST", "rpc/controle_vendas_save_client", {"client_record": record}
        )
        return int(revision)

    def save_sale(self, sale_record: dict, item_records: list[dict]) -> int:
        revision = self._rest(
            "POST",
            "rpc/controle_vendas_save_sale",
            {
                "sale_record": sale_record,
                "item_records": item_records,
                "expected_revision": int(sale_record.get("expected_revision", 0)),
            },
        )
        return int(revision)

    def delete_sale(self, cloud_id: str, expected_revision: int) -> int:
        revision = self._rest(
            "POST",
            "rpc/controle_vendas_delete_sale",
            {
                "target_sale_id": cloud_id,
                "expected_revision": int(expected_revision),
            },
        )
        return int(revision)

    def fetch_snapshot(self) -> dict[str, list[dict]]:
        snapshot = self._rest("POST", "rpc/controle_vendas_snapshot", {})
        expected = {"products", "clients", "sales", "sale_items"}
        if not isinstance(snapshot, dict) or not expected.issubset(snapshot):
            raise CloudError("O Supabase retornou dados em formato inesperado.")
        if any(not isinstance(snapshot[key], list) for key in expected):
            raise CloudError("O Supabase retornou dados em formato inesperado.")
        return {key: snapshot[key] for key in expected}


class CloudSyncManager:
    def __init__(self, database, session_path: str | Path):
        self.database = database
        self.client = SupabaseClient(session_path)
        self._lock = threading.Lock()

    @property
    def connected_email(self):
        return self.client.connected_email

    @property
    def has_session(self):
        return self.client.has_session

    def login_and_sync(self, email: str, password: str):
        self.client.login(email, password)
        return self.sync_once()

    def logout(self):
        self.client.logout()

    def sync_once(self) -> dict:
        if not self._lock.acquire(blocking=False):
            return {"busy": True, "uploaded": 0, "downloaded": 0}
        uploaded = 0
        conflict_found = False
        try:
            if self.database.pending_sync_count():
                initial_snapshot = self.client.fetch_snapshot()
                self.database.rebase_initial_sync_changes(initial_snapshot)
            for change in self.database.pending_sync_changes():
                payload = json.loads(change["payload_json"])
                try:
                    if change["entity_type"] == "product":
                        revision = self.client.save_product(payload)
                    elif change["entity_type"] == "client":
                        revision = self.client.save_client(payload)
                    elif change["entity_type"] == "sale" and change["operation"] == "delete":
                        revision = self.client.delete_sale(
                            change["entity_cloud_id"], payload["expected_revision"]
                        )
                    elif change["entity_type"] == "sale":
                        revision = self.client.save_sale(payload["sale"], payload["items"])
                    else:
                        raise CloudError("Existe uma alteração local desconhecida na fila.")
                    self.database.record_cloud_revision(
                        change["entity_type"], change["entity_cloud_id"], revision
                    )
                    self.database.mark_sync_change_done(change["id"])
                    uploaded += 1
                except CloudConflictError:
                    snapshot = self.client.fetch_snapshot()
                    key = {
                        "product": "products",
                        "client": "clients",
                        "sale": "sales",
                    }[change["entity_type"]]
                    remote = next(
                        (
                            record
                            for record in snapshot[key]
                            if record["id"] == change["entity_cloud_id"]
                        ),
                        None,
                    )
                    self.database.record_sync_conflict(change, remote)
                    conflict_found = True
            snapshot = self.client.fetch_snapshot()
            self.database.apply_cloud_snapshot(snapshot)
            downloaded = sum(len(records) for records in snapshot.values())
            if conflict_found:
                raise CloudConflictError(
                    "Foi detectada uma edição simultânea em outra máquina. Nenhuma alteração foi sobrescrita; escolha qual versão manter em Configurações."
                )
            return {"busy": False, "uploaded": uploaded, "downloaded": downloaded}
        finally:
            self._lock.release()
