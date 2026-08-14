from __future__ import annotations

import json
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4, uuid5

_LEGACY_SYNC_NAMESPACE = UUID("5051f301-81b8-493a-9905-c9de0dde4370")


def _sortable_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value).casefold())
    return "".join(character for character in normalized if not unicodedata.combining(character))


def _client_report_sort_key(row):
    """Group platform accounts by the person's final name, then platform."""
    full_name = " ".join(str(row["client_name"]).split())
    platform, separator, person = full_name.rpartition(" ")
    if not separator:
        platform = full_name
        person = full_name
    return _sortable_name(person), _sortable_name(platform), _sortable_name(full_name)


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self):
        with self.connect() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.execute("PRAGMA synchronous = NORMAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL COLLATE NOCASE,
                    price_cents INTEGER NOT NULL CHECK(price_cents >= 0),
                    barcode TEXT NOT NULL UNIQUE,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS clients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    notes TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS sales (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER NOT NULL REFERENCES clients(id),
                    sale_date TEXT NOT NULL,
                    total_cents INTEGER NOT NULL CHECK(total_cents >= 0),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS sale_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
                    product_id INTEGER NOT NULL REFERENCES products(id),
                    product_name TEXT NOT NULL,
                    quantity INTEGER NOT NULL CHECK(quantity > 0),
                    unit_price_cents INTEGER NOT NULL CHECK(unit_price_cents >= 0),
                    subtotal_cents INTEGER NOT NULL CHECK(subtotal_cents >= 0)
                );
                CREATE TABLE IF NOT EXISTS app_sequences (
                    name TEXT PRIMARY KEY,
                    next_value INTEGER NOT NULL CHECK(next_value > 0)
                );
                CREATE INDEX IF NOT EXISTS ix_sales_date ON sales(sale_date);
                CREATE INDEX IF NOT EXISTS ix_sales_client ON sales(client_id);
                CREATE INDEX IF NOT EXISTS ix_products_barcode ON products(barcode);
                CREATE INDEX IF NOT EXISTS ix_sale_items_sale ON sale_items(sale_id);
                CREATE INDEX IF NOT EXISTS ix_sale_items_product ON sale_items(product_id);
                INSERT OR IGNORE INTO app_sequences(name, next_value)
                VALUES (
                    'product_barcode',
                    COALESCE(
                        (SELECT seq + 1 FROM sqlite_sequence WHERE name='products'),
                        1
                    )
                );
            """)
            self._migrate_sync_schema(db)

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _ensure_column(db: sqlite3.Connection, table: str, definition: str):
        column = definition.split()[0]
        existing = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")

    def _migrate_sync_schema(self, db: sqlite3.Connection):
        for table in ("products", "clients", "sales", "sale_items"):
            self._ensure_column(db, table, "cloud_id TEXT")
            self._ensure_column(db, table, "cloud_revision INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(db, table, "updated_at TEXT")
        self._ensure_column(db, "sale_items", "created_at TEXT")
        self._ensure_column(db, "products", "deleted_at TEXT")
        self._ensure_column(db, "clients", "deleted_at TEXT")
        self._ensure_column(db, "sales", "deleted_at TEXT")
        db.executescript("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_products_cloud_id ON products(cloud_id);
            CREATE UNIQUE INDEX IF NOT EXISTS ux_clients_cloud_id ON clients(cloud_id);
            CREATE UNIQUE INDEX IF NOT EXISTS ux_sales_cloud_id ON sales(cloud_id);
            CREATE UNIQUE INDEX IF NOT EXISTS ux_sale_items_cloud_id ON sale_items(cloud_id);
            CREATE TABLE IF NOT EXISTS sync_outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_cloud_id TEXT NOT NULL,
                operation TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                last_error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(entity_type, entity_cloud_id)
            );
            CREATE TABLE IF NOT EXISTS sync_conflicts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_cloud_id TEXT NOT NULL,
                local_payload_json TEXT NOT NULL,
                remote_payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                resolved_at TEXT
            );
            CREATE TABLE IF NOT EXISTS sync_state (
                name TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_sync_outbox_status
            ON sync_outbox(status, entity_type, id);
        """)
        now = self._utc_now()
        for table in ("products", "clients", "sales", "sale_items"):
            rows = db.execute(
                f"SELECT id FROM {table} WHERE cloud_id IS NULL OR cloud_id=''"
            ).fetchall()
            db.executemany(
                f"UPDATE {table} SET cloud_id=?, updated_at=COALESCE(updated_at, ?) WHERE id=?",
                [
                    (self._legacy_cloud_id(table, row["id"]), now, row["id"])
                    for row in rows
                ],
            )
            db.execute(
                f"UPDATE {table} SET updated_at=? WHERE updated_at IS NULL OR updated_at=''",
                (now,),
            )
        db.execute(
            "UPDATE sale_items SET created_at=? WHERE created_at IS NULL OR created_at=''",
            (now,),
        )
        if not db.execute(
            "SELECT 1 FROM sync_state WHERE name='initial_outbox_created'"
        ).fetchone():
            self._queue_initial_sync(db)
            db.execute(
                "INSERT INTO sync_state(name, value) VALUES('initial_outbox_created', ?)",
                (now,),
            )

    @staticmethod
    def _row_dict(row) -> dict:
        return {key: row[key] for key in row.keys()}

    @staticmethod
    def _legacy_cloud_id(table: str, local_id: int) -> str:
        return str(uuid5(_LEGACY_SYNC_NAMESPACE, f"{table}:{int(local_id)}"))

    def _product_payload(self, row) -> dict:
        return {
            "id": row["cloud_id"],
            "name": row["name"],
            "price_cents": int(row["price_cents"]),
            "barcode": row["barcode"],
            "active": bool(row["active"]),
            "created_at": row["created_at"],
            "deleted_at": row["deleted_at"],
            "expected_revision": int(row["cloud_revision"]),
        }

    def _client_payload(self, row) -> dict:
        return {
            "id": row["cloud_id"],
            "name": row["name"],
            "notes": row["notes"],
            "active": bool(row["active"]),
            "created_at": row["created_at"],
            "deleted_at": row["deleted_at"],
            "expected_revision": int(row["cloud_revision"]),
        }

    def _sale_payload(self, db: sqlite3.Connection, sale_id: int) -> dict:
        sale = db.execute(
            """SELECT s.*, c.cloud_id client_cloud_id
               FROM sales s JOIN clients c ON c.id=s.client_id WHERE s.id=?""",
            (sale_id,),
        ).fetchone()
        items = db.execute(
            """SELECT si.*, p.cloud_id product_cloud_id
               FROM sale_items si JOIN products p ON p.id=si.product_id
               WHERE si.sale_id=? ORDER BY si.id""",
            (sale_id,),
        ).fetchall()
        return {
            "sale": {
                "id": sale["cloud_id"],
                "client_id": sale["client_cloud_id"],
                "sale_date": sale["sale_date"],
                "total_cents": int(sale["total_cents"]),
                "created_at": sale["created_at"],
                "expected_revision": int(sale["cloud_revision"]),
            },
            "items": [
                {
                    "id": item["cloud_id"],
                    "product_id": item["product_cloud_id"],
                    "product_name": item["product_name"],
                    "quantity": int(item["quantity"]),
                    "unit_price_cents": int(item["unit_price_cents"]),
                    "subtotal_cents": int(item["subtotal_cents"]),
                }
                for item in items
            ],
        }

    def _queue_change(
        self,
        db: sqlite3.Connection,
        entity_type: str,
        cloud_id: str,
        operation: str,
        payload: dict,
    ):
        now = self._utc_now()
        db.execute(
            """INSERT INTO sync_outbox(
                   entity_type, entity_cloud_id, operation, payload_json,
                   status, last_error, created_at, updated_at
               ) VALUES(?,?,?,?, 'pending', '', ?, ?)
               ON CONFLICT(entity_type, entity_cloud_id) DO UPDATE SET
                   operation=excluded.operation,
                   payload_json=excluded.payload_json,
                   status='pending',
                   last_error='',
                   updated_at=excluded.updated_at""",
            (
                entity_type,
                cloud_id,
                operation,
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                now,
                now,
            ),
        )

    def _queue_initial_sync(self, db: sqlite3.Connection):
        for row in db.execute("SELECT * FROM products ORDER BY id"):
            self._queue_change(db, "product", row["cloud_id"], "upsert", self._product_payload(row))
        for row in db.execute("SELECT * FROM clients ORDER BY id"):
            self._queue_change(db, "client", row["cloud_id"], "upsert", self._client_payload(row))
        for row in db.execute("SELECT id, cloud_id FROM sales ORDER BY id"):
            self._queue_change(db, "sale", row["cloud_id"], "upsert", self._sale_payload(db, row["id"]))

    @staticmethod
    def _barcode_for_serial(serial: int) -> str:
        if not 1 <= serial <= 999_999_999:
            raise RuntimeError("A sequência de códigos de barras chegou ao limite suportado.")
        body = f"290{serial:09d}"
        checksum = (
            10
            - sum(
                (3 if index % 2 else 1) * int(number)
                for index, number in enumerate(body)
            )
            % 10
        ) % 10
        return body + str(checksum)

    def _reserve_barcode(self, db: sqlite3.Connection) -> str:
        for _attempt in range(100):
            serial = (uuid4().int % 999_999_999) + 1
            code = self._barcode_for_serial(serial)
            if not db.execute(
                "SELECT 1 FROM products WHERE barcode=?", (code,)
            ).fetchone():
                return code
        raise RuntimeError("Não foi possível gerar um código de barras único.")

    def generate_barcode(self) -> str:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            return self._reserve_barcode(db)

    @staticmethod
    def _clean_name(value: str, field: str) -> str:
        name = str(value).strip()
        if not name:
            raise ValueError(f"{field} não pode ficar vazio.")
        return name

    @staticmethod
    def _nonnegative_integer(value: int, field: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{field} deve ser um número inteiro não negativo.")
        return value

    def add_product(self, name: str, price_cents: int) -> int:
        name = self._clean_name(name, "O nome do produto")
        price_cents = self._nonnegative_integer(price_cents, "O preço")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            barcode = self._reserve_barcode(db)
            cloud_id = str(uuid4())
            now = self._utc_now()
            cur = db.execute(
                """INSERT INTO products(
                       name, price_cents, barcode, cloud_id, cloud_revision, updated_at
                   ) VALUES(?,?,?,?,0,?)""",
                (name, price_cents, barcode, cloud_id, now),
            )
            row = db.execute("SELECT * FROM products WHERE id=?", (cur.lastrowid,)).fetchone()
            self._queue_change(db, "product", cloud_id, "upsert", self._product_payload(row))
            return cur.lastrowid

    def update_product(self, product_id: int, name: str, price_cents: int):
        name = self._clean_name(name, "O nome do produto")
        price_cents = self._nonnegative_integer(price_cents, "O preço")
        with self.connect() as db:
            now = self._utc_now()
            result = db.execute(
                "UPDATE products SET name=?, price_cents=?, updated_at=? WHERE id=?",
                (name, price_cents, now, product_id),
            )
            if result.rowcount != 1:
                raise ValueError("O produto selecionado não existe mais.")
            row = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
            self._queue_change(db, "product", row["cloud_id"], "upsert", self._product_payload(row))

    def delete_product(self, product_id: int):
        with self.connect() as db:
            now = self._utc_now()
            result = db.execute(
                "UPDATE products SET active=0, deleted_at=?, updated_at=? WHERE id=?",
                (now, now, product_id),
            )
            if result.rowcount != 1:
                raise ValueError("O produto selecionado não existe mais.")
            row = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
            self._queue_change(db, "product", row["cloud_id"], "upsert", self._product_payload(row))

    def list_products(self, search: str = "", include_inactive: bool = False):
        sql = "SELECT * FROM products WHERE name LIKE ?"
        args = [f"%{search.strip()}%"]
        if not include_inactive:
            sql += " AND active=1"
        return self._all(sql + " ORDER BY name", args)

    def product_by_barcode(self, barcode: str):
        return self._one("SELECT * FROM products WHERE barcode=? AND active=1", (barcode.strip(),))

    def add_client(self, name: str, notes: str = "") -> int:
        name = self._clean_name(name, "O nome do cliente")
        with self.connect() as db:
            cloud_id = str(uuid4())
            now = self._utc_now()
            cur = db.execute(
                """INSERT INTO clients(
                       name, notes, cloud_id, cloud_revision, updated_at
                   ) VALUES(?,?,?,0,?)""",
                (name, notes.strip(), cloud_id, now),
            )
            row = db.execute("SELECT * FROM clients WHERE id=?", (cur.lastrowid,)).fetchone()
            self._queue_change(db, "client", cloud_id, "upsert", self._client_payload(row))
            return cur.lastrowid

    def update_client(self, client_id: int, name: str, notes: str = ""):
        name = self._clean_name(name, "O nome do cliente")
        with self.connect() as db:
            now = self._utc_now()
            result = db.execute(
                "UPDATE clients SET name=?, notes=?, updated_at=? WHERE id=?",
                (name, notes.strip(), now, client_id),
            )
            if result.rowcount != 1:
                raise ValueError("O cliente selecionado não existe mais.")
            row = db.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
            self._queue_change(db, "client", row["cloud_id"], "upsert", self._client_payload(row))

    def delete_client(self, client_id: int):
        with self.connect() as db:
            now = self._utc_now()
            result = db.execute(
                "UPDATE clients SET active=0, deleted_at=?, updated_at=? WHERE id=?",
                (now, now, client_id),
            )
            if result.rowcount != 1:
                raise ValueError("O cliente selecionado não existe mais.")
            row = db.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
            self._queue_change(db, "client", row["cloud_id"], "upsert", self._client_payload(row))

    def list_clients(self, search: str = "", include_inactive: bool = False):
        sql = "SELECT * FROM clients WHERE name LIKE ?"
        args = [f"%{search.strip()}%"]
        if not include_inactive:
            sql += " AND active=1"
        return self._all(sql + " ORDER BY name", args)

    def client_by_id(self, client_id: int):
        return self._one("SELECT * FROM clients WHERE id=?", (client_id,))

    def save_sale(self, client_id: int, sale_date: str, items: list[dict], sale_id: int | None = None) -> int:
        if not items:
            raise ValueError("A venda precisa ter ao menos um item.")
        try:
            date.fromisoformat(sale_date)
        except (TypeError, ValueError) as exc:
            raise ValueError("A data da venda é inválida.") from exc
        normalized_items = []
        for item in items:
            quantity = self._nonnegative_integer(item["quantity"], "A quantidade")
            if quantity == 0:
                raise ValueError("A quantidade deve ser maior que zero.")
            unit_price = self._nonnegative_integer(
                item["unit_price_cents"], "O preço unitário"
            )
            normalized_items.append(
                {
                    **item,
                    "product_name": self._clean_name(
                        item["product_name"], "O nome do produto"
                    ),
                    "quantity": quantity,
                    "unit_price_cents": unit_price,
                }
            )
        total = sum(
            item["quantity"] * item["unit_price_cents"]
            for item in normalized_items
        )
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM clients WHERE id=?", (client_id,)).fetchone():
                raise ValueError("O cliente selecionado não existe mais.")
            if sale_id is None:
                cloud_id = str(uuid4())
                now = self._utc_now()
                cur = db.execute(
                    """INSERT INTO sales(
                           client_id, sale_date, total_cents, cloud_id,
                           cloud_revision, updated_at
                       ) VALUES(?,?,?,?,0,?)""",
                    (client_id, sale_date, total, cloud_id, now),
                )
                sale_id = cur.lastrowid
            else:
                now = self._utc_now()
                result = db.execute(
                    """UPDATE sales
                       SET client_id=?, sale_date=?, total_cents=?, updated_at=?
                       WHERE id=?""",
                    (client_id, sale_date, total, now, sale_id),
                )
                if result.rowcount != 1:
                    raise ValueError("A venda selecionada não existe mais.")
                db.execute("DELETE FROM sale_items WHERE sale_id=?", (sale_id,))
            db.executemany(
                """INSERT INTO sale_items(
                       sale_id, product_id, product_name, quantity,
                       unit_price_cents, subtotal_cents, cloud_id,
                       cloud_revision, updated_at
                   ) VALUES(?,?,?,?,?,?,?,0,?)""",
                [
                    (
                        sale_id,
                        item["product_id"],
                        item["product_name"],
                        item["quantity"],
                        item["unit_price_cents"],
                        item["quantity"] * item["unit_price_cents"],
                        str(uuid4()),
                        now,
                    )
                    for item in normalized_items
                ],
            )
            sale = db.execute("SELECT cloud_id FROM sales WHERE id=?", (sale_id,)).fetchone()
            self._queue_change(
                db,
                "sale",
                sale["cloud_id"],
                "upsert",
                self._sale_payload(db, sale_id),
            )
        return int(sale_id)

    def list_sales(self, start: str | None = None, end: str | None = None, client_id: int | None = None):
        sql = """SELECT s.id, s.sale_date, c.name client_name, s.total_cents,
                 COALESCE(SUM(si.quantity),0) item_count FROM sales s JOIN clients c ON c.id=s.client_id
                 LEFT JOIN sale_items si ON si.sale_id=s.id WHERE 1=1"""
        args = []
        if start:
            sql += " AND s.sale_date>=?"
            args.append(start)
        if end:
            sql += " AND s.sale_date<=?"
            args.append(end)
        if client_id is not None:
            sql += " AND s.client_id=?"
            args.append(client_id)
        sql += " GROUP BY s.id ORDER BY s.sale_date DESC, s.id DESC"
        return self._all(sql, args)

    def get_sale(self, sale_id: int):
        sale = self._one("SELECT * FROM sales WHERE id=?", (sale_id,))
        items = self._all("SELECT * FROM sale_items WHERE sale_id=? ORDER BY id", (sale_id,))
        return sale, items

    def delete_sale(self, sale_id: int):
        with self.connect() as db:
            sale = db.execute(
                "SELECT cloud_id, cloud_revision FROM sales WHERE id=?", (sale_id,)
            ).fetchone()
            if not sale:
                raise ValueError("A venda selecionada não existe mais.")
            self._queue_change(
                db,
                "sale",
                sale["cloud_id"],
                "delete",
                {
                    "id": sale["cloud_id"],
                    "expected_revision": int(sale["cloud_revision"]),
                },
            )
            db.execute("DELETE FROM sales WHERE id=?", (sale_id,))

    def revenue_report(self, start: str, end: str, client_id: int | None = None):
        try:
            start_date = date.fromisoformat(start)
            end_date = date.fromisoformat(end)
        except (TypeError, ValueError) as exc:
            raise ValueError("Informe um período válido no formato AAAA-MM-DD.") from exc
        if start_date > end_date:
            raise ValueError("A data inicial não pode ser posterior à data final.")
        sql = """SELECT c.id client_id, c.name client_name,
                        SUM(s.total_cents) total_cents,
                        COALESCE(SUM(items.product_count), 0) product_count
                 FROM sales s
                 JOIN clients c ON c.id=s.client_id
                 LEFT JOIN (
                     SELECT sale_id, SUM(quantity) product_count
                     FROM sale_items
                     GROUP BY sale_id
                 ) items ON items.sale_id=s.id
                 WHERE s.sale_date BETWEEN ? AND ?"""
        args = [start, end]
        if client_id is not None:
            sql += " AND c.id=?"
            args.append(client_id)
        sql += " GROUP BY c.id, c.name"
        return sorted(self._all(sql, args), key=_client_report_sort_key)

    def dashboard_stats(self, month_start: str, month_end: str):
        with self.connect() as db:
            products = db.execute("SELECT COUNT(*) total FROM products WHERE active=1").fetchone()["total"]
            clients = db.execute("SELECT COUNT(*) total FROM clients WHERE active=1").fetchone()["total"]
            sales = db.execute(
                "SELECT COUNT(*) quantity, COALESCE(SUM(total_cents),0) revenue FROM sales WHERE sale_date BETWEEN ? AND ?",
                (month_start, month_end),
            ).fetchone()
            return {
                "products": products,
                "clients": clients,
                "sales": sales["quantity"],
                "revenue_cents": sales["revenue"],
            }

    def backup(self, destination: str | Path) -> Path:
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        target = destination / f"controle_vendas_backup_{datetime.now():%Y%m%d_%H%M%S_%f}.db"
        source = sqlite3.connect(self.path, timeout=10.0)
        dest = sqlite3.connect(target, timeout=10.0)
        try:
            source.backup(dest)
            result = dest.execute("PRAGMA quick_check").fetchone()[0]
            if result != "ok":
                raise RuntimeError("O banco de backup não passou na verificação de integridade.")
        finally:
            dest.close()
            source.close()
        return target

    def pending_sync_changes(self):
        return self._all(
            """SELECT * FROM sync_outbox
               WHERE status='pending'
               ORDER BY CASE entity_type
                   WHEN 'product' THEN 1
                   WHEN 'client' THEN 2
                   WHEN 'sale' THEN 3
                   ELSE 9 END, id"""
        )

    def pending_sync_count(self) -> int:
        row = self._one("SELECT COUNT(*) total FROM sync_outbox WHERE status='pending'")
        return int(row["total"])

    def rebase_initial_sync_changes(self, snapshot: dict[str, list[dict]]):
        remote_by_type = {
            "product": {row["id"]: row for row in snapshot.get("products", [])},
            "client": {row["id"]: row for row in snapshot.get("clients", [])},
            "sale": {row["id"]: row for row in snapshot.get("sales", [])},
        }
        now = self._utc_now()
        with self.connect() as db:
            changes = db.execute(
                "SELECT * FROM sync_outbox WHERE status='pending' ORDER BY id"
            ).fetchall()
            for change in changes:
                payload = json.loads(change["payload_json"])
                if change["entity_type"] == "sale" and change["operation"] != "delete":
                    record = payload["sale"]
                else:
                    record = payload
                if int(record.get("expected_revision", 0)) != 0:
                    continue
                remote = remote_by_type.get(change["entity_type"], {}).get(
                    change["entity_cloud_id"]
                )
                if not remote:
                    continue
                revision = int(remote.get("revision", 1))
                record["expected_revision"] = revision
                table = {
                    "product": "products",
                    "client": "clients",
                    "sale": "sales",
                }[change["entity_type"]]
                db.execute(
                    f"UPDATE {table} SET cloud_revision=? WHERE cloud_id=?",
                    (revision, change["entity_cloud_id"]),
                )
                db.execute(
                    "UPDATE sync_outbox SET payload_json=?, updated_at=? WHERE id=?",
                    (
                        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                        now,
                        change["id"],
                    ),
                )

    def unresolved_conflict_count(self) -> int:
        row = self._one(
            "SELECT COUNT(*) total FROM sync_conflicts WHERE resolved_at IS NULL"
        )
        return int(row["total"])

    def mark_sync_change_done(self, change_id: int):
        with self.connect() as db:
            db.execute("DELETE FROM sync_outbox WHERE id=?", (change_id,))

    def record_cloud_revision(self, entity_type: str, cloud_id: str, revision: int):
        table = {"product": "products", "client": "clients", "sale": "sales"}.get(
            entity_type
        )
        if not table:
            return
        with self.connect() as db:
            db.execute(
                f"UPDATE {table} SET cloud_revision=? WHERE cloud_id=?",
                (int(revision), cloud_id),
            )

    def record_sync_conflict(self, change, remote_payload: dict | None):
        now = self._utc_now()
        with self.connect() as db:
            db.execute(
                """INSERT INTO sync_conflicts(
                       entity_type, entity_cloud_id, local_payload_json,
                       remote_payload_json, created_at
                   ) VALUES(?,?,?,?,?)""",
                (
                    change["entity_type"],
                    change["entity_cloud_id"],
                    change["payload_json"],
                    json.dumps(remote_payload or {}, ensure_ascii=False),
                    now,
                ),
            )
            db.execute(
                """UPDATE sync_outbox
                   SET status='conflict', last_error=?, updated_at=? WHERE id=?""",
                (
                    "Outra máquina alterou este registro antes da sincronização.",
                    now,
                    change["id"],
                ),
            )

    def resolve_conflicts(self, keep_local: bool):
        now = self._utc_now()
        with self.connect() as db:
            conflicts = db.execute(
                "SELECT * FROM sync_conflicts WHERE resolved_at IS NULL ORDER BY id"
            ).fetchall()
            for conflict in conflicts:
                outbox = db.execute(
                    """SELECT * FROM sync_outbox
                       WHERE entity_type=? AND entity_cloud_id=?""",
                    (conflict["entity_type"], conflict["entity_cloud_id"]),
                ).fetchone()
                if keep_local and outbox:
                    local_payload = json.loads(conflict["local_payload_json"])
                    remote_payload = json.loads(conflict["remote_payload_json"])
                    revision = int(remote_payload.get("revision", 0))
                    if conflict["entity_type"] == "sale":
                        local_payload["sale"]["expected_revision"] = revision
                    else:
                        local_payload["expected_revision"] = revision
                    table = {
                        "product": "products",
                        "client": "clients",
                        "sale": "sales",
                    }.get(conflict["entity_type"])
                    if table:
                        db.execute(
                            f"UPDATE {table} SET cloud_revision=? WHERE cloud_id=?",
                            (revision, conflict["entity_cloud_id"]),
                        )
                    db.execute(
                        """UPDATE sync_outbox
                           SET payload_json=?, status='pending', last_error='', updated_at=?
                           WHERE id=?""",
                        (
                            json.dumps(local_payload, ensure_ascii=False, separators=(",", ":")),
                            now,
                            outbox["id"],
                        ),
                    )
                elif outbox:
                    db.execute("DELETE FROM sync_outbox WHERE id=?", (outbox["id"],))
                db.execute(
                    "UPDATE sync_conflicts SET resolved_at=? WHERE id=?",
                    (now, conflict["id"]),
                )

    def apply_cloud_snapshot(self, snapshot: dict[str, list[dict]]):
        pending = {
            row["entity_cloud_id"]
            for row in self._all("SELECT entity_cloud_id FROM sync_outbox")
        }
        with self.connect() as db:
            for record in snapshot.get("products", []):
                if record["id"] in pending:
                    continue
                local = db.execute(
                    "SELECT id FROM products WHERE cloud_id=?", (record["id"],)
                ).fetchone()
                values = (
                    record["name"],
                    int(record["price_cents"]),
                    record["barcode"],
                    int(bool(record["active"])),
                    record.get("created_at") or self._utc_now(),
                    record.get("updated_at") or self._utc_now(),
                    record.get("deleted_at"),
                    int(record.get("revision", 1)),
                )
                if local:
                    db.execute(
                        """UPDATE products SET
                               name=?, price_cents=?, barcode=?, active=?, created_at=?,
                               updated_at=?, deleted_at=?, cloud_revision=?
                           WHERE id=?""",
                        (*values, local["id"]),
                    )
                else:
                    db.execute(
                        """INSERT INTO products(
                               name, price_cents, barcode, active, created_at,
                               updated_at, deleted_at, cloud_revision, cloud_id
                           ) VALUES(?,?,?,?,?,?,?,?,?)""",
                        (*values, record["id"]),
                    )

            for record in snapshot.get("clients", []):
                if record["id"] in pending:
                    continue
                local = db.execute(
                    "SELECT id FROM clients WHERE cloud_id=?", (record["id"],)
                ).fetchone()
                values = (
                    record["name"],
                    record.get("notes") or "",
                    int(bool(record["active"])),
                    record.get("created_at") or self._utc_now(),
                    record.get("updated_at") or self._utc_now(),
                    record.get("deleted_at"),
                    int(record.get("revision", 1)),
                )
                if local:
                    db.execute(
                        """UPDATE clients SET
                               name=?, notes=?, active=?, created_at=?, updated_at=?,
                               deleted_at=?, cloud_revision=? WHERE id=?""",
                        (*values, local["id"]),
                    )
                else:
                    db.execute(
                        """INSERT INTO clients(
                               name, notes, active, created_at, updated_at,
                               deleted_at, cloud_revision, cloud_id
                           ) VALUES(?,?,?,?,?,?,?,?)""",
                        (*values, record["id"]),
                    )

            items_by_sale: dict[str, list[dict]] = {}
            for item in snapshot.get("sale_items", []):
                items_by_sale.setdefault(item["sale_id"], []).append(item)
            for record in snapshot.get("sales", []):
                if record["id"] in pending:
                    continue
                local = db.execute(
                    "SELECT id FROM sales WHERE cloud_id=?", (record["id"],)
                ).fetchone()
                if record.get("deleted_at"):
                    if local:
                        db.execute("DELETE FROM sales WHERE id=?", (local["id"],))
                    continue
                client = db.execute(
                    "SELECT id FROM clients WHERE cloud_id=?", (record["client_id"],)
                ).fetchone()
                if not client:
                    continue
                values = (
                    client["id"],
                    record["sale_date"],
                    int(record["total_cents"]),
                    record.get("created_at") or self._utc_now(),
                    record.get("updated_at") or self._utc_now(),
                    int(record.get("revision", 1)),
                )
                if local:
                    sale_id = local["id"]
                    db.execute(
                        """UPDATE sales SET client_id=?, sale_date=?, total_cents=?,
                               created_at=?, updated_at=?, cloud_revision=?, deleted_at=NULL
                           WHERE id=?""",
                        (*values, sale_id),
                    )
                    db.execute("DELETE FROM sale_items WHERE sale_id=?", (sale_id,))
                else:
                    cursor = db.execute(
                        """INSERT INTO sales(
                               client_id, sale_date, total_cents, created_at,
                               updated_at, cloud_revision, cloud_id
                           ) VALUES(?,?,?,?,?,?,?)""",
                        (*values, record["id"]),
                    )
                    sale_id = cursor.lastrowid
                for item in items_by_sale.get(record["id"], []):
                    product = db.execute(
                        "SELECT id FROM products WHERE cloud_id=?", (item["product_id"],)
                    ).fetchone()
                    if not product:
                        continue
                    db.execute(
                        """INSERT INTO sale_items(
                               sale_id, product_id, product_name, quantity,
                               unit_price_cents, subtotal_cents, cloud_id,
                               cloud_revision, created_at, updated_at
                           ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (
                            sale_id,
                            product["id"],
                            item["product_name"],
                            int(item["quantity"]),
                            int(item["unit_price_cents"]),
                            int(item["subtotal_cents"]),
                            item["id"],
                            int(item.get("revision", 1)),
                            item.get("created_at") or self._utc_now(),
                            item.get("updated_at") or self._utc_now(),
                        ),
                    )
            db.execute(
                """INSERT INTO sync_state(name, value) VALUES('last_sync_at', ?)
                   ON CONFLICT(name) DO UPDATE SET value=excluded.value""",
                (self._utc_now(),),
            )

    def _all(self, sql, args=()):
        with self.connect() as db:
            return db.execute(sql, args).fetchall()

    def _one(self, sql, args=()):
        with self.connect() as db:
            return db.execute(sql, args).fetchone()
