from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path


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
        row = db.execute(
            "SELECT next_value FROM app_sequences WHERE name='product_barcode'"
        ).fetchone()
        serial = int(row["next_value"])
        while True:
            code = self._barcode_for_serial(serial)
            serial += 1
            if not db.execute(
                "SELECT 1 FROM products WHERE barcode=?", (code,)
            ).fetchone():
                db.execute(
                    "UPDATE app_sequences SET next_value=? WHERE name='product_barcode'",
                    (serial,),
                )
                return code

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
            cur = db.execute(
                "INSERT INTO products(name, price_cents, barcode) VALUES(?,?,?)",
                (name, price_cents, barcode),
            )
            return cur.lastrowid

    def update_product(self, product_id: int, name: str, price_cents: int):
        name = self._clean_name(name, "O nome do produto")
        price_cents = self._nonnegative_integer(price_cents, "O preço")
        with self.connect() as db:
            result = db.execute(
                "UPDATE products SET name=?, price_cents=? WHERE id=?",
                (name, price_cents, product_id),
            )
            if result.rowcount != 1:
                raise ValueError("O produto selecionado não existe mais.")

    def delete_product(self, product_id: int):
        with self.connect() as db:
            used = db.execute("SELECT 1 FROM sale_items WHERE product_id=? LIMIT 1", (product_id,)).fetchone()
            if used:
                db.execute("UPDATE products SET active=0 WHERE id=?", (product_id,))
            else:
                db.execute("DELETE FROM products WHERE id=?", (product_id,))

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
            cur = db.execute(
                "INSERT INTO clients(name, notes) VALUES(?,?)",
                (name, notes.strip()),
            )
            return cur.lastrowid

    def update_client(self, client_id: int, name: str, notes: str = ""):
        name = self._clean_name(name, "O nome do cliente")
        with self.connect() as db:
            result = db.execute(
                "UPDATE clients SET name=?, notes=? WHERE id=?",
                (name, notes.strip(), client_id),
            )
            if result.rowcount != 1:
                raise ValueError("O cliente selecionado não existe mais.")

    def delete_client(self, client_id: int):
        with self.connect() as db:
            used = db.execute("SELECT 1 FROM sales WHERE client_id=? LIMIT 1", (client_id,)).fetchone()
            if used:
                db.execute("UPDATE clients SET active=0 WHERE id=?", (client_id,))
            else:
                db.execute("DELETE FROM clients WHERE id=?", (client_id,))

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
                cur = db.execute(
                    "INSERT INTO sales(client_id, sale_date, total_cents) VALUES(?,?,?)",
                    (client_id, sale_date, total),
                )
                sale_id = cur.lastrowid
            else:
                result = db.execute(
                    "UPDATE sales SET client_id=?, sale_date=?, total_cents=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (client_id, sale_date, total, sale_id),
                )
                if result.rowcount != 1:
                    raise ValueError("A venda selecionada não existe mais.")
                db.execute("DELETE FROM sale_items WHERE sale_id=?", (sale_id,))
            db.executemany(
                "INSERT INTO sale_items(sale_id, product_id, product_name, quantity, unit_price_cents, subtotal_cents) VALUES(?,?,?,?,?,?)",
                [
                    (
                        sale_id,
                        item["product_id"],
                        item["product_name"],
                        item["quantity"],
                        item["unit_price_cents"],
                        item["quantity"] * item["unit_price_cents"],
                    )
                    for item in normalized_items
                ],
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
            db.execute("DELETE FROM sales WHERE id=?", (sale_id,))

    def revenue_report(self, start: str, end: str, client_id: int | None = None):
        try:
            start_date = date.fromisoformat(start)
            end_date = date.fromisoformat(end)
        except (TypeError, ValueError) as exc:
            raise ValueError("Informe um período válido no formato AAAA-MM-DD.") from exc
        if start_date > end_date:
            raise ValueError("A data inicial não pode ser posterior à data final.")
        sql = """SELECT c.id client_id, c.name client_name, SUM(s.total_cents) total_cents
                 FROM sales s JOIN clients c ON c.id=s.client_id
                 WHERE s.sale_date BETWEEN ? AND ?"""
        args = [start, end]
        if client_id is not None:
            sql += " AND c.id=?"
            args.append(client_id)
        sql += " GROUP BY c.id, c.name ORDER BY c.name"
        return self._all(sql, args)

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

    def _all(self, sql, args=()):
        with self.connect() as db:
            return db.execute(sql, args).fetchall()

    def _one(self, sql, args=()):
        with self.connect() as db:
            return db.execute(sql, args).fetchone()
