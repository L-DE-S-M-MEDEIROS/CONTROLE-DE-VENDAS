from __future__ import annotations

import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
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
                CREATE INDEX IF NOT EXISTS ix_sales_date ON sales(sale_date);
                CREATE INDEX IF NOT EXISTS ix_sales_client ON sales(client_id);
                CREATE INDEX IF NOT EXISTS ix_products_barcode ON products(barcode);
            """)

    def generate_barcode(self) -> str:
        with self.connect() as db:
            row = db.execute("SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM products").fetchone()
            serial = int(row["next_id"])
            while True:
                body = f"290{serial:09d}"[-12:]
                checksum = (10 - sum((3 if i % 2 else 1) * int(n) for i, n in enumerate(body)) % 10) % 10
                code = body + str(checksum)
                if not db.execute("SELECT 1 FROM products WHERE barcode=?", (code,)).fetchone():
                    return code
                serial += 1

    def add_product(self, name: str, price_cents: int) -> int:
        barcode = self.generate_barcode()
        with self.connect() as db:
            cur = db.execute("INSERT INTO products(name, price_cents, barcode) VALUES(?,?,?)", (name.strip(), price_cents, barcode))
            return cur.lastrowid

    def update_product(self, product_id: int, name: str, price_cents: int):
        with self.connect() as db:
            db.execute("UPDATE products SET name=?, price_cents=? WHERE id=?", (name.strip(), price_cents, product_id))

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
        with self.connect() as db:
            cur = db.execute("INSERT INTO clients(name, notes) VALUES(?,?)", (name.strip(), notes.strip()))
            return cur.lastrowid

    def update_client(self, client_id: int, name: str, notes: str = ""):
        with self.connect() as db:
            db.execute(
                "UPDATE clients SET name=?, notes=? WHERE id=?",
                (name.strip(), notes.strip(), client_id),
            )

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

    def save_sale(self, client_id: int, sale_date: str, items: list[dict], sale_id: int | None = None) -> int:
        if not items:
            raise ValueError("A venda precisa ter ao menos um item.")
        total = sum(i["quantity"] * i["unit_price_cents"] for i in items)
        with self.connect() as db:
            if sale_id is None:
                cur = db.execute("INSERT INTO sales(client_id, sale_date, total_cents) VALUES(?,?,?)", (client_id, sale_date, total))
                sale_id = cur.lastrowid
            else:
                db.execute("UPDATE sales SET client_id=?, sale_date=?, total_cents=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (client_id, sale_date, total, sale_id))
                db.execute("DELETE FROM sale_items WHERE sale_id=?", (sale_id,))
            db.executemany("INSERT INTO sale_items(sale_id, product_id, product_name, quantity, unit_price_cents, subtotal_cents) VALUES(?,?,?,?,?,?)", [
                (sale_id, i["product_id"], i["product_name"], i["quantity"], i["unit_price_cents"], i["quantity"] * i["unit_price_cents"]) for i in items
            ])
        return int(sale_id)

    def list_sales(self, start: str | None = None, end: str | None = None, client_id: int | None = None):
        sql = """SELECT s.id, s.sale_date, c.name client_name, s.total_cents,
                 COALESCE(SUM(si.quantity),0) item_count FROM sales s JOIN clients c ON c.id=s.client_id
                 LEFT JOIN sale_items si ON si.sale_id=s.id WHERE 1=1"""
        args = []
        if start: sql += " AND s.sale_date>=?"; args.append(start)
        if end: sql += " AND s.sale_date<=?"; args.append(end)
        if client_id: sql += " AND s.client_id=?"; args.append(client_id)
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
        sql = """SELECT c.id client_id, c.name client_name, SUM(s.total_cents) total_cents
                 FROM sales s JOIN clients c ON c.id=s.client_id
                 WHERE s.sale_date BETWEEN ? AND ?"""
        args = [start, end]
        if client_id: sql += " AND c.id=?"; args.append(client_id)
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
        target = destination / f"controle_vendas_backup_{datetime.now():%Y%m%d_%H%M%S}.db"
        source = sqlite3.connect(self.path)
        dest = sqlite3.connect(target)
        try:
            source.backup(dest)
        finally:
            dest.close()
            source.close()
        return target

    def _all(self, sql, args=()):
        with self.connect() as db: return db.execute(sql, args).fetchall()

    def _one(self, sql, args=()):
        with self.connect() as db: return db.execute(sql, args).fetchone()
