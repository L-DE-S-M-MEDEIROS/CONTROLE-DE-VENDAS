import os
import tempfile
import unittest
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch

from installer_launcher import InstallerWindow
from sales_control.app import App
from sales_control.theme import ThemePreferences, get_theme


class InterfaceTests(unittest.TestCase):
    def test_active_sales_tab_is_larger_and_uses_theme_accent(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"LOCALAPPDATA": folder}, clear=False
        ):
            app = App(
                db_path=Path(folder) / "tabs.db",
                maximize=False,
                dpi_scale_override=1.0,
            )
            app.withdraw()
            try:
                for theme_key in ("light", "dark"):
                    app.change_theme(theme_key)
                    app.update_idletasks()
                    style = ttk.Style(app)
                    selected_padding = style.lookup(
                        "Inner.TNotebook.Tab", "padding", ("selected",)
                    )
                    inactive_padding = style.lookup(
                        "Inner.TNotebook.Tab", "padding", ("!selected",)
                    )
                    if not isinstance(selected_padding, (tuple, list)):
                        selected_padding = app.tk.splitlist(selected_padding)
                    if not isinstance(inactive_padding, (tuple, list)):
                        inactive_padding = app.tk.splitlist(inactive_padding)
                    selected_padding = tuple(int(str(value)) for value in selected_padding)
                    inactive_padding = tuple(int(str(value)) for value in inactive_padding)

                    palette = get_theme(theme_key)
                    self.assertGreater(selected_padding[0], inactive_padding[0])
                    self.assertGreater(selected_padding[1], inactive_padding[1])
                    self.assertEqual(
                        palette["accent"],
                        style.lookup(
                            "Inner.TNotebook.Tab", "background", ("selected",)
                        ),
                    )
                    self.assertEqual(
                        palette["soft"],
                        style.lookup(
                            "Inner.TNotebook.Tab", "background", ("!selected",)
                        ),
                    )
            finally:
                app.destroy()

    def test_theme_persists_and_all_table_columns_are_centered(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"LOCALAPPDATA": folder}, clear=False
        ):
            app = App(
                db_path=Path(folder) / "interface.db",
                maximize=False,
                dpi_scale_override=1.0,
            )
            app.withdraw()
            app.update_idletasks()
            try:
                trees = (
                    app.recent_tree,
                    app.items,
                    app.sales_tree,
                    app.products,
                    app.clients_tree,
                    app.report_tree,
                )
                for tree in trees:
                    for column in tree["columns"]:
                        self.assertEqual("center", str(tree.column(column, "anchor")))
                        self.assertEqual("center", str(tree.heading(column, "anchor")))

                target = "dark" if app.theme_key == "light" else "light"
                app.change_theme(target)
                app.update()
                self.assertEqual(target, app.theme_key)
                self.assertEqual(
                    target,
                    ThemePreferences(Path(folder) / "ControleDeVendas" / "configuracoes.json").load(),
                )
            finally:
                app.destroy()

    def test_installer_buttons_fit_at_high_dpi(self):
        window = InstallerWindow(dpi_scale_override=1.75)
        window.update()
        try:
            self.assertEqual("INSTALAR", window.install_button.cget("text"))
            self.assertEqual("Cancelar", window.cancel_button.cget("text"))
            bottom = window.winfo_rooty() + window.winfo_height()
            for button in (window.install_button, window.cancel_button):
                self.assertGreater(button.winfo_width(), 80)
                self.assertGreater(button.winfo_height(), 30)
                self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), bottom)
        finally:
            window.destroy()

    def test_pdf_is_opened_in_default_browser(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"LOCALAPPDATA": folder}, clear=False
        ):
            app = App(
                db_path=Path(folder) / "pdf.db",
                maximize=False,
                dpi_scale_override=1.0,
            )
            app.withdraw()
            app.update()
            pdf = Path(folder) / "relatorio.pdf"
            pdf.write_bytes(b"%PDF-1.4")
            try:
                with patch("sales_control.app.webbrowser.open", return_value=True) as opener, patch(
                    "sales_control.app.messagebox.showinfo"
                ):
                    app.open_pdf_for_printing(pdf)
                opener.assert_called_once_with(pdf.resolve().as_uri(), new=2)
            finally:
                app.destroy()

    def test_selected_product_barcode_is_copied(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"LOCALAPPDATA": folder}, clear=False
        ):
            app = App(
                db_path=Path(folder) / "clipboard.db",
                maximize=False,
                dpi_scale_override=1.0,
            )
            app.withdraw()
            app.update()
            try:
                product_id = app.db.add_product("Produto para copiar", 2500)
                app.refresh_products()
                app.products.selection_set(str(product_id))
                expected = app.products.item(str(product_id), "values")[3]
                with patch("sales_control.app.messagebox.showinfo"):
                    app.copy_product_barcode()
                self.assertEqual(str(expected), app.clipboard_get())
            finally:
                app.destroy()


if __name__ == "__main__":
    unittest.main()
