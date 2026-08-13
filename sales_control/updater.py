from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from packaging.version import InvalidVersion, Version

from .build_config import GITHUB_REPOSITORY

INSTALLER_NAME = "ControleDeVendas-Setup.exe"
CHECKSUM_NAME = "SHA256.txt"
MAX_INSTALLER_SIZE = 250 * 1024 * 1024
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    title: str
    notes: str
    installer_url: str
    installer_name: str
    installer_size: int
    checksum_url: str
    release_url: str


def configured_repository() -> str:
    return os.getenv("VENDAS_PRO_UPDATE_REPO", GITHUB_REPOSITORY).strip()


def _request_json(url: str):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "Vendas-PRO-Updater",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            _validated_asset_url(response.geturl())
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError("Ainda não existe uma atualização publicada.") from exc
        if exc.code == 403:
            raise UpdateError("O GitHub limitou temporariamente a consulta. Tente novamente mais tarde.") from exc
        raise UpdateError(f"O GitHub respondeu com erro {exc.code}.") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise UpdateError("O GitHub retornou uma resposta inválida.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UpdateError("Não foi possível conectar ao GitHub. Verifique a internet.") from exc


def _validated_asset_url(value: object) -> str:
    url = str(value or "")
    parsed = urllib.parse.urlparse(url)
    trusted_hosts = {
        "github.com",
        "api.github.com",
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
    }
    if parsed.scheme != "https" or parsed.hostname not in trusted_hosts:
        raise UpdateError("A atualização publicada contém um endereço de download não confiável.")
    return url


def check_for_update(current_version: str) -> UpdateInfo | None:
    repository = configured_repository()
    if not REPOSITORY_PATTERN.fullmatch(repository):
        raise UpdateError("O serviço de atualização ainda não foi vinculado corretamente ao GitHub.")

    release = _request_json(f"https://api.github.com/repos/{repository}/releases/latest")
    if not isinstance(release, dict):
        raise UpdateError("O GitHub retornou dados de atualização inválidos.")
    if release.get("draft") or release.get("prerelease"):
        raise UpdateError("A versão encontrada ainda não é uma publicação estável.")

    remote_text = str(release.get("tag_name", "")).lstrip("vV")
    try:
        remote_version = Version(remote_text)
        installed_version = Version(current_version)
    except InvalidVersion as exc:
        raise UpdateError("A versão publicada no GitHub não segue o padrão esperado.") from exc
    if remote_version <= installed_version:
        return None

    assets = release.get("assets") or []
    installer = next((asset for asset in assets if asset.get("name") == INSTALLER_NAME), None)
    checksum = next((asset for asset in assets if asset.get("name") == CHECKSUM_NAME), None)
    if not installer:
        raise UpdateError("A nova versão não possui o instalador oficial.")
    if not checksum:
        raise UpdateError("A nova versão não possui o arquivo SHA-256 obrigatório.")
    try:
        installer_size = int(installer.get("size") or 0)
    except (TypeError, ValueError) as exc:
        raise UpdateError("O tamanho do instalador publicado é inválido.") from exc
    if installer_size <= 0 or installer_size > MAX_INSTALLER_SIZE:
        raise UpdateError("O tamanho do instalador publicado é inválido.")

    return UpdateInfo(
        version=str(remote_version),
        title=str(release.get("name") or f"Versão {remote_version}"),
        notes=str(release.get("body") or "Atualização disponível.").strip(),
        installer_url=_validated_asset_url(installer.get("browser_download_url")),
        installer_name=INSTALLER_NAME,
        installer_size=installer_size,
        checksum_url=_validated_asset_url(checksum.get("browser_download_url")),
        release_url=str(release.get("html_url") or ""),
    )


def _download_bytes(url: str, maximum_size: int = 64 * 1024) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Vendas-PRO-Updater"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if urllib.parse.urlparse(url).scheme == "https":
                _validated_asset_url(response.geturl())
            data = response.read(maximum_size + 1)
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        raise UpdateError("Não foi possível baixar a verificação SHA-256.") from exc
    if len(data) > maximum_size:
        raise UpdateError("O arquivo de verificação SHA-256 é inválido.")
    return data


def _expected_checksum(checksum_text: str, installer_name: str) -> str:
    pattern = re.compile(
        rf"^([a-fA-F0-9]{{64}})\s+\*?{re.escape(installer_name)}\s*$",
        re.MULTILINE,
    )
    match = pattern.search(checksum_text)
    if not match:
        raise UpdateError("O SHA-256 publicado não corresponde ao instalador oficial.")
    return match.group(1).lower()


def download_update(info: UpdateInfo, progress=None) -> Path:
    if info.installer_size <= 0 or info.installer_size > MAX_INSTALLER_SIZE:
        raise UpdateError("O tamanho do instalador publicado é inválido.")
    update_dir = Path(tempfile.gettempdir()) / "VendasPRO-Atualizacao"
    update_dir.mkdir(parents=True, exist_ok=True)
    installer_path = update_dir / INSTALLER_NAME
    partial_path = installer_path.with_suffix(".exe.part")
    installer_path.unlink(missing_ok=True)
    partial_path.unlink(missing_ok=True)

    try:
        checksum_text = _download_bytes(info.checksum_url).decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise UpdateError("O arquivo de verificação SHA-256 é inválido.") from exc
    expected = _expected_checksum(checksum_text, INSTALLER_NAME)
    request = urllib.request.Request(info.installer_url, headers={"User-Agent": "Vendas-PRO-Updater"})
    digest = hashlib.sha256()
    downloaded = 0
    executable_header = bytearray()
    try:
        with urllib.request.urlopen(request, timeout=60) as response, open(partial_path, "wb") as output:
            if urllib.parse.urlparse(info.installer_url).scheme == "https":
                _validated_asset_url(response.geturl())
            try:
                total = int(
                    response.headers.get("Content-Length")
                    or info.installer_size
                    or 0
                )
            except (TypeError, ValueError) as exc:
                raise UpdateError("O tamanho informado para o download é inválido.") from exc
            if total <= 0 or total > MAX_INSTALLER_SIZE:
                raise UpdateError("O tamanho informado para o download é inválido.")
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                if downloaded + len(chunk) > MAX_INSTALLER_SIZE:
                    raise UpdateError("O instalador excede o limite de tamanho permitido.")
                if len(executable_header) < 2:
                    executable_header.extend(chunk[: 2 - len(executable_header)])
                output.write(chunk)
                digest.update(chunk)
                downloaded += len(chunk)
                if progress:
                    progress(downloaded, total)
        if info.installer_size and downloaded != info.installer_size:
            raise UpdateError("O download ficou incompleto. Tente novamente.")
        if bytes(executable_header) != b"MZ":
            raise UpdateError("O arquivo baixado não é um instalador do Windows válido.")
        if digest.hexdigest().lower() != expected:
            raise UpdateError("A verificação de segurança SHA-256 da atualização falhou.")
        os.replace(partial_path, installer_path)
        return installer_path
    except UpdateError:
        partial_path.unlink(missing_ok=True)
        installer_path.unlink(missing_ok=True)
        raise
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        partial_path.unlink(missing_ok=True)
        installer_path.unlink(missing_ok=True)
        raise UpdateError("Falha ao baixar o instalador da atualização.") from exc


def launch_installer(installer_path: Path):
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [str(installer_path), "/VERYSILENT"],
        close_fds=True,
        creationflags=flags,
    )


def installed_setup_path() -> Path:
    return Path(sys.executable).resolve().parent / "VendasPRO-Instalador.exe"


def rollback_available() -> bool:
    app_dir = Path(sys.executable).resolve().parent
    return (app_dir / "ControleDeVendas.rollback.exe").is_file() and installed_setup_path().is_file()


def launch_rollback():
    setup = installed_setup_path()
    if not rollback_available():
        raise UpdateError("Não há uma versão anterior disponível para recuperação.")
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [str(setup), "/ROLLBACK", "/VERYSILENT"],
        close_fds=True,
        creationflags=flags,
    )
