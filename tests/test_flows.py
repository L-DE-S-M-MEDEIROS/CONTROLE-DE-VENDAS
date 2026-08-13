import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader
from reportlab.lib.units import mm

from sales_control.database import Database
from sales_control.reports import (
    _label_barcode,
    product_label_pdf,
    product_pdf,
    revenue_pdf,
)
from sales_control.updater import UpdateError, UpdateInfo, check_for_update, download_update


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = Database(self.root / "test.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_complete_flow(self):
        first = self.db.add_product("Produto A", 1250)
        second = self.db.add_product("Produto B", 700)
        products = self.db.list_products()
        self.assertEqual(2, len(products))
        self.assertEqual(2, len({product["barcode"] for product in products}))
        self.assertTrue(all(len(product["barcode"]) == 13 for product in products))
        self.db.update_product(first, "Produto A atualizado", 1490)
        updated = next(product for product in self.db.list_products() if product["id"] == first)
        self.assertEqual(("Produto A atualizado", 1490), (updated["name"], updated["price_cents"]))
        client = self.db.add_client("Cliente Teste")
        self.db.update_client(client, "Cliente Atualizado", "Cliente preferencial")
        self.assertEqual("Cliente Atualizado", self.db.list_clients()[0]["name"])
        items = [{"product_id": first, "product_name": "Produto A", "quantity": 3, "unit_price_cents": 1250}]
        sale = self.db.save_sale(client, "2026-08-10", items)
        self.assertEqual(3750, self.db.get_sale(sale)[0]["total_cents"])
        items.append({"product_id": second, "product_name": "Produto B", "quantity": 2, "unit_price_cents": 700})
        self.db.save_sale(client, "2026-08-11", items, sale)
        self.assertEqual(5150, self.db.get_sale(sale)[0]["total_cents"])
        rows = self.db.revenue_report("2026-08-01", "2026-08-31", client)
        self.assertEqual(5150, rows[0]["total_cents"])
        stats = self.db.dashboard_stats("2026-08-01", "2026-08-31")
        self.assertEqual((2, 1, 1, 5150), (stats["products"], stats["clients"], stats["sales"], stats["revenue_cents"]))
        product_pdf(self.root / "products.pdf", products)
        revenue_pdf(self.root / "revenue.pdf", rows, "2026-08-01", "2026-08-31", "Cliente Teste")
        self.assertGreater((self.root / "products.pdf").stat().st_size, 1000)
        self.assertGreater((self.root / "revenue.pdf").stat().st_size, 1000)
        self.assertTrue(self.db.backup(self.root / "backup").exists())
        self.db.delete_sale(sale)
        self.assertEqual([], self.db.list_sales())
        self.db.delete_client(client)
        self.assertEqual([], self.db.list_clients())

    def test_update_release_detection(self):
        release = {
            "tag_name": "v9.0.0",
            "name": "Versão 9",
            "body": "Novidades",
            "html_url": "https://github.com/empresa/controle-de-vendas/releases/tag/v9.0.0",
            "assets": [
                {"name": "ControleDeVendas-Setup.exe", "browser_download_url": "https://github.com/empresa/controle-de-vendas/releases/download/v9.0.0/ControleDeVendas-Setup.exe", "size": 123},
                {"name": "SHA256.txt", "browser_download_url": "https://github.com/empresa/controle-de-vendas/releases/download/v9.0.0/SHA256.txt", "size": 64},
            ],
        }
        with patch("sales_control.updater.GITHUB_REPOSITORY", "empresa/controle-de-vendas"), patch("sales_control.updater._request_json", return_value=release):
            info = check_for_update("1.2.0")
        self.assertEqual("9.0.0", info.version)
        self.assertEqual("ControleDeVendas-Setup.exe", info.installer_name)
        self.assertTrue(info.checksum_url)

    def test_semantic_version_and_mandatory_checksum(self):
        release = {
            "tag_name": "v1.10.0",
            "assets": [
                {"name": "ControleDeVendas-Setup.exe", "browser_download_url": "https://github.com/empresa/app/releases/download/v1.10.0/ControleDeVendas-Setup.exe", "size": 10},
                {"name": "SHA256.txt", "browser_download_url": "https://github.com/empresa/app/releases/download/v1.10.0/SHA256.txt"},
            ],
        }
        with patch("sales_control.updater.GITHUB_REPOSITORY", "empresa/app"), patch("sales_control.updater._request_json", return_value=release):
            self.assertEqual("1.10.0", check_for_update("1.9.0").version)
        release["assets"].pop()
        with patch("sales_control.updater.GITHUB_REPOSITORY", "empresa/app"), patch("sales_control.updater._request_json", return_value=release):
            with self.assertRaises(UpdateError):
                check_for_update("1.9.0")

    def test_verified_update_download(self):
        installer_source = self.root / "source-setup.exe"
        installer_source.write_bytes(b"instalador-seguro")
        checksum = self.root / "SHA256.txt"
        checksum.write_text(hashlib.sha256(installer_source.read_bytes()).hexdigest() + "  ControleDeVendas-Setup.exe", encoding="ascii")
        info = UpdateInfo("2.0.0", "Versão 2", "Teste", installer_source.as_uri(), "ControleDeVendas-Setup.exe", installer_source.stat().st_size, checksum.as_uri(), "https://github.com/empresa/app/releases/tag/v2.0.0")
        downloaded = download_update(info)
        self.assertEqual(installer_source.read_bytes(), downloaded.read_bytes())
        downloaded.unlink(missing_ok=True)

    def test_tampered_update_is_rejected(self):
        installer_source = self.root / "tampered.exe"
        installer_source.write_bytes(b"arquivo-adulterado")
        checksum = self.root / "SHA256.txt"
        checksum.write_text("0" * 64 + "  ControleDeVendas-Setup.exe", encoding="ascii")
        info = UpdateInfo("2.0.0", "Versão 2", "Teste", installer_source.as_uri(), "ControleDeVendas-Setup.exe", installer_source.stat().st_size, checksum.as_uri(), "https://github.com/empresa/app/releases/tag/v2.0.0")
        with self.assertRaises(UpdateError):
            download_update(info)

    def test_archived_client_keeps_sale_history(self):
        product = self.db.add_product("Produto", 1000)
        client = self.db.add_client("Cliente com histórico")
        self.db.save_sale(client, "2026-08-12", [{"product_id": product, "product_name": "Produto", "quantity": 1, "unit_price_cents": 1000}])
        self.db.delete_client(client)
        self.assertEqual([], self.db.list_clients())
        self.assertEqual("Cliente com histórico", self.db.list_sales()[0]["client_name"])

    def test_thermal_product_label_is_exactly_40_by_25_mm(self):
        product_id = self.db.add_product("2P ML Yuri", 2590)
        product = next(
            row for row in self.db.list_products() if row["id"] == product_id
        )
        path = product_label_pdf(self.root / "etiqueta.pdf", product)
        reader = PdfReader(path)
        self.assertEqual(1, len(reader.pages))
        page = reader.pages[0]
        self.assertAlmostEqual(40 * mm, float(page.mediabox.width), places=2)
        self.assertAlmostEqual(25 * mm, float(page.mediabox.height), places=2)
        extracted = page.extract_text()
        self.assertIn("2P ML YURI", extracted)
        self.assertIn(product["barcode"], extracted)

        barcode = _label_barcode(product["barcode"])
        barcode.validate()
        encoded = barcode.encode()
        self.assertEqual(106, encoded[-1])
        expected_checksum = (
            encoded[0]
            + sum(position * value for position, value in enumerate(encoded[1:-2], 1))
        ) % 103
        self.assertEqual(expected_checksum, encoded[-2])
        self.assertTrue(barcode.decompose())


if __name__ == "__main__":
    unittest.main()
