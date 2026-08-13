from __future__ import annotations

import sys
import tempfile
from pathlib import Path


def bundled_smoke_test() -> int:
    """Import the packaged app and prove that label generation works."""
    try:
        from sales_control.app import App  # noqa: F401
        from sales_control.reports import product_label_pdf

        with tempfile.TemporaryDirectory(prefix="VendasPRO-Smoke-") as folder:
            output = Path(folder) / "etiqueta_teste.pdf"
            product_label_pdf(
                output,
                {"name": "TESTE DO EXECUTAVEL", "barcode": "2900000000018"},
            )
            if not output.exists() or output.stat().st_size < 1000:
                return 2
        return 0
    except Exception:
        return 1

if __name__ == "__main__":
    if "--smoke-test" in sys.argv:
        raise SystemExit(bundled_smoke_test())
    from sales_control.app import main

    main()
