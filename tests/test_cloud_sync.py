import json
import tempfile
import unittest
from pathlib import Path

from sales_control.cloud_sync import (
    CloudConflictError,
    CloudError,
    CloudSyncManager,
    SessionStore,
    SupabaseClient,
)
from sales_control.database import Database


class _SuccessfulCloudClient:
    connected_email = "vendasldesmmedeiros@gmail.com"
    has_session = True

    def save_product(self, _payload):
        return 1

    def save_client(self, _payload):
        return 1

    def save_sale(self, _sale, _items):
        return 1

    def delete_sale(self, _cloud_id, _expected_revision):
        return 2

    def fetch_snapshot(self):
        return {"products": [], "clients": [], "sales": [], "sale_items": []}


class CloudSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = Database(self.root / "data.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_the_company_email_can_start_login(self):
        client = SupabaseClient(self.root / "session.dat")
        with self.assertRaisesRegex(CloudError, "Somente o e-mail autorizado"):
            client.login("outra-conta@example.com", "senha")

    def test_session_token_is_protected_on_disk(self):
        path = self.root / "session.dat"
        store = SessionStore(path)
        session = {
            "access_token": "access-secret",
            "refresh_token": "refresh-secret",
            "expires_at": 9999999999,
            "user": {"email": "vendasldesmmedeiros@gmail.com"},
        }
        store.save(session)
        self.assertNotIn(b"refresh-secret", path.read_bytes())
        self.assertEqual(session, store.load())
        store.clear()
        self.assertFalse(path.exists())

    def test_pending_changes_upload_in_dependency_order(self):
        product = self.db.add_product("Produto", 100)
        client = self.db.add_client("Cliente")
        self.db.save_sale(
            client,
            "2026-08-14",
            [
                {
                    "product_id": product,
                    "product_name": "Produto",
                    "quantity": 1,
                    "unit_price_cents": 100,
                }
            ],
        )
        manager = CloudSyncManager(self.db, self.root / "session.dat")
        manager.client = _SuccessfulCloudClient()
        result = manager.sync_once()
        self.assertEqual(3, result["uploaded"])
        self.assertEqual(0, self.db.pending_sync_count())

    def test_first_sync_rebases_a_matching_legacy_record(self):
        self.db.add_product("Produto legado", 100)
        product = self.db.list_products()[0]
        snapshot = {
            "products": [
                {
                    "id": product["cloud_id"],
                    "name": product["name"],
                    "price_cents": product["price_cents"],
                    "barcode": product["barcode"],
                    "active": True,
                    "created_at": product["created_at"],
                    "updated_at": product["updated_at"],
                    "deleted_at": None,
                    "revision": 4,
                }
            ],
            "clients": [],
            "sales": [],
            "sale_items": [],
        }
        self.db.rebase_initial_sync_changes(snapshot)
        payload = json.loads(self.db.pending_sync_changes()[0]["payload_json"])
        self.assertEqual(4, payload["expected_revision"])

    def test_simultaneous_edit_is_preserved_as_a_conflict(self):
        product_id = self.db.add_product("Minha alteração", 100)
        local_product = self.db.list_products()[0]

        class ConflictClient(_SuccessfulCloudClient):
            def save_product(self, _payload):
                raise CloudConflictError("conflito")

            def fetch_snapshot(self_inner):
                return {
                    "products": [
                        {
                            "id": local_product["cloud_id"],
                            "name": "Alteração da outra máquina",
                            "price_cents": 200,
                            "barcode": local_product["barcode"],
                            "active": True,
                            "created_at": local_product["created_at"],
                            "updated_at": "2026-08-14T13:00:00+00:00",
                            "deleted_at": None,
                            "revision": 2,
                        }
                    ],
                    "clients": [],
                    "sales": [],
                    "sale_items": [],
                }

        manager = CloudSyncManager(self.db, self.root / "session.dat")
        manager.client = ConflictClient()
        with self.assertRaises(CloudConflictError):
            manager.sync_once()
        self.assertEqual(1, self.db.unresolved_conflict_count())
        product = next(row for row in self.db.list_products() if row["id"] == product_id)
        self.assertEqual("Minha alteração", product["name"])
        self.db.resolve_conflicts(keep_local=True)
        pending = self.db.pending_sync_changes()[0]
        self.assertEqual(2, json.loads(pending["payload_json"])["expected_revision"])
        self.assertEqual(0, self.db.unresolved_conflict_count())


if __name__ == "__main__":
    unittest.main()
