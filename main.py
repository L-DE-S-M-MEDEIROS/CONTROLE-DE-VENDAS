from __future__ import annotations

import sys
import tempfile
from pathlib import Path


def bundled_smoke_test() -> int:
    """Exercise critical packaged features without touching the user's data."""
    try:
        from sales_control.app import App  # noqa: F401
        from sales_control.database import Database
        from sales_control.reports import product_label_pdf
        from sales_control.updater import configured_repository

        with tempfile.TemporaryDirectory(prefix="VendasPRO-Smoke-") as folder:
            root = Path(folder)
            database = Database(root / "teste.db")
            product_id = database.add_product("TESTE DO EXECUTÁVEL", 1990)
            product = next(
                row
                for row in database.list_products()
                if row["id"] == product_id
            )
            client_id = database.add_client("CLIENTE DE TESTE")
            database.save_sale(
                client_id,
                "2026-01-01",
                [
                    {
                        "product_id": product_id,
                        "product_name": product["name"],
                        "quantity": 2,
                        "unit_price_cents": product["price_cents"],
                    }
                ],
            )
            if database.revenue_report("2026-01-01", "2026-01-31")[0][
                "total_cents"
            ] != 3980:
                return 2
            if not database.backup(root / "backups").is_file():
                return 3

            output = root / "etiqueta_teste.pdf"
            product_label_pdf(
                output,
                product,
            )
            if not output.exists() or output.stat().st_size < 1000:
                return 4
            if "/" not in configured_repository():
                return 5
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    if "--smoke-test" in sys.argv:
        raise SystemExit(bundled_smoke_test())
    from sales_control.app import main

    main()
