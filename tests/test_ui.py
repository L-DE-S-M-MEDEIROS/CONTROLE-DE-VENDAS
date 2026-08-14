import os
import tempfile
import tkinter as tk
import unittest
from datetime import date
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from installer_launcher import InstallerWindow
from sales_control.app import (
    App,
    DownloadDialog,
    ProductEditDialog,
    UpdateOfferDialog,
    parse_money,
)
from sales_control.date_input import DATE_MASK, display_date, iso_date
from sales_control.theme import ThemePreferences, get_theme


class InterfaceTests(unittest.TestCase):
    def test_secondary_windows_are_centered_over_the_app_at_high_dpi(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"LOCALAPPDATA": folder}, clear=False
        ):
            app = App(
                db_path=Path(folder) / "centered_dialogs.db",
                maximize=False,
                dpi_scale_override=1.5,
            )
            app.geometry("1700x1000+60+30")
            app.update()
            dialogs = []
            try:
                dialogs.append(ProductEditDialog(app, "Produto", "19,90"))
                dialogs[-1].grab_release()
                dialogs.append(
                    UpdateOfferDialog(
                        app,
                        SimpleNamespace(
                            title="Atualização de teste",
                            version="9.9.9",
                            notes="Descrição da atualização.",
                        ),
                        lambda _info: None,
                    )
                )
                dialogs[-1].grab_release()
                dialogs.append(DownloadDialog(app))
                dialogs[-1].grab_release()
                for dialog in dialogs:
                    dialog.update_idletasks()
                    parent_center_x = app.winfo_rootx() + app.winfo_width() / 2
                    parent_center_y = app.winfo_rooty() + app.winfo_height() / 2
                    dialog_center_x = dialog.winfo_x() + dialog.winfo_width() / 2
                    dialog_center_y = dialog.winfo_y() + dialog.winfo_height() / 2
                    self.assertAlmostEqual(parent_center_x, dialog_center_x, delta=20)
                    self.assertAlmostEqual(parent_center_y, dialog_center_y, delta=30)
            finally:
                for dialog in dialogs:
                    if dialog.winfo_exists():
                        dialog.destroy()
                app.destroy()

    def test_cloud_settings_are_locked_to_the_company_account(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"LOCALAPPDATA": folder}, clear=False
        ):
            app = App(
                db_path=Path(folder) / "cloud_settings.db",
                maximize=False,
                dpi_scale_override=1.0,
            )
            app.withdraw()
            app.update()
            try:
                self.assertEqual("normal", str(app.cloud_connect_button["state"]))
                self.assertEqual("disabled", str(app.cloud_sync_button["state"]))
                self.assertIn("Conta não conectada", app.cloud_status["text"])
                self.assertEqual(
                    "Conta autorizada da empresa", app.cloud_account_label["text"]
                )
                self.assertNotIn("@", app.cloud_account_label["text"])
                self.assertEqual("", app.cloud_password.get())
            finally:
                app.destroy()

    def test_page_transitions_are_subtle_fast_and_cancellable(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"LOCALAPPDATA": folder}, clear=False
        ):
            app = App(
                db_path=Path(folder) / "motion_pages.db",
                maximize=False,
                dpi_scale_override=1.0,
            )
            app.geometry("1400x820")
            app.update()
            try:
                app.show_page("products")
                first_page = app.motion.page_widget
                self.assertIs(first_page, app.pages["products"])
                self.assertEqual("place", first_page.winfo_manager())
                self.assertEqual(5, app.motion.FRAME_MS)
                self.assertEqual("products", app.current_page)

                app.show_page("clients")
                self.assertEqual("clients", app.current_page)
                self.assertIs(app.motion.page_widget, app.pages["clients"])
                self.assertIsNot(first_page, app.motion.page_widget)

                app.show_page("sales")
                app.sales_inner.select(app.sales_history_tab)
                app.update()
                self.assertEqual(
                    str(app.sales_history_tab), app.sales_inner.select()
                )

                app.after(250, app.quit)
                app.mainloop()
                self.assertIsNone(app.motion.page_widget)
                self.assertEqual("place", app.pages["sales"].winfo_manager())
                self.assertEqual("0", app.pages["sales"].place_info()["x"])
            finally:
                app.destroy()

    def test_product_and_client_registration_have_animated_feedback(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"LOCALAPPDATA": folder}, clear=False
        ):
            app = App(
                db_path=Path(folder) / "motion_saves.db",
                maximize=False,
                dpi_scale_override=1.0,
            )
            app.withdraw()
            app.update()
            try:
                app.prod_name.set("Produto animado")
                app.prod_price.set("19,90")
                app.add_product()
                product_id = str(app.db.list_products()[0]["id"])
                self.assertEqual(
                    ("motion_highlight",),
                    tuple(app.products.item(product_id, "tags")),
                )
                self.assertIsNotNone(app.motion.toast_widget)
                toast_icon = app.motion.toast_widget.winfo_children()[0]
                self.assertEqual(
                    app.motion.toast_widget.cget("bg"), toast_icon.cget("bg")
                )

                app.client_name.set("Cliente animado")
                app.client_notes.set("Cadastro com confirmação visual")
                app.save_client()
                client_id = str(app.db.list_clients()[0]["id"])
                self.assertEqual(
                    ("motion_highlight",),
                    tuple(app.clients_tree.item(client_id, "tags")),
                )
                toast_labels = [
                    child.cget("text")
                    for container in app.motion.toast_widget.winfo_children()
                    for child in container.winfo_children()
                    if isinstance(child, tk.Label)
                ]
                self.assertTrue(
                    any("Cliente cadastrado" in text for text in toast_labels)
                )
            finally:
                app.destroy()

    def test_open_and_closed_app_use_the_same_high_resolution_brand_icon(self):
        root = Path(__file__).resolve().parent.parent
        png_path = root / "assets" / "app_icon.png"
        ico_path = root / "assets" / "app_icon.ico"
        with Image.open(png_path) as png:
            self.assertEqual((1024, 1024), png.size)
            self.assertEqual("RGBA", png.mode)
            self.assertEqual(0, png.getpixel((0, 0))[3])
            self.assertGreater(png.getpixel((512, 512))[3], 0)
        with Image.open(ico_path) as icon:
            self.assertTrue(
                {(16, 16), (32, 32), (48, 48), (128, 128), (256, 256)}
                <= icon.ico.sizes()
            )

        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"LOCALAPPDATA": folder}, clear=False
        ):
            app = App(
                db_path=Path(folder) / "branding.db",
                maximize=False,
                dpi_scale_override=1.0,
            )
            app.withdraw()
            try:
                app.update_idletasks()
                self.assertEqual(256, app.icons["app"].width())
                self.assertEqual(256, app.icons["app"].height())
            finally:
                app.destroy()

    def test_date_mask_keeps_slashes_and_calendar_selects_the_date(self):
        self.assertEqual("13/08/26", display_date("2026-08-13"))
        self.assertEqual("2026-08-13", iso_date("13/08/26"))
        with self.assertRaises(ValueError):
            iso_date("31/02/26")

        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"LOCALAPPDATA": folder}, clear=False
        ):
            app = App(
                db_path=Path(folder) / "date_mask.db",
                maximize=False,
                dpi_scale_override=1.0,
            )
            app.update()
            try:
                entry = app.sale_date_field.entry
                entry.selection_range(0, "end")
                entry._on_keypress(
                    SimpleNamespace(keysym="BackSpace", char="", state=0)
                )
                self.assertEqual(DATE_MASK, app.sale_date.get())

                for digit in "130826":
                    entry._on_keypress(
                        SimpleNamespace(keysym=digit, char=digit, state=0)
                    )
                self.assertEqual("13/08/26", app.sale_date.get())

                entry._on_keypress(
                    SimpleNamespace(keysym="BackSpace", char="", state=0)
                )
                self.assertEqual("13/08/2 ", app.sale_date.get())
                self.assertEqual("/", app.sale_date.get()[2])
                self.assertEqual("/", app.sale_date.get()[5])

                app.sale_date_field.open_calendar()
                popup = app.sale_date_field.popup
                self.assertTrue(popup.winfo_exists())
                popup.select(date(2027, 9, 2))
                self.assertEqual("02/09/27", app.sale_date.get())
                self.assertTrue(app.sale_date_field.calendar_button.cget("image"))
            finally:
                app.destroy()

    def test_report_filters_accept_the_visible_brazilian_date_format(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"LOCALAPPDATA": folder}, clear=False
        ):
            app = App(
                db_path=Path(folder) / "report_dates.db",
                maximize=False,
                dpi_scale_override=1.0,
            )
            app.withdraw()
            app.update()
            try:
                product = app.db.add_product("Produto", 1500)
                client = app.db.add_client("Cliente")
                app.db.save_sale(
                    client,
                    "2026-08-13",
                    [
                        {
                            "product_id": product,
                            "product_name": "Produto",
                            "quantity": 2,
                            "unit_price_cents": 1500,
                        }
                    ],
                )
                app.start_date_field.entry.set_date("01/08/26")
                app.end_date_field.entry.set_date("31/08/26")
                self.assertTrue(app.run_report())
                self.assertEqual(3000, app.report_rows[0]["total_cents"])
                self.assertEqual(2, app.report_rows[0]["product_count"])
                self.assertEqual(
                    ("client", "products", "total"),
                    app.report_tree["columns"],
                )
                report_values = app.report_tree.item(
                    app.report_tree.get_children()[0], "values"
                )
                self.assertEqual("2", str(report_values[1]))
            finally:
                app.destroy()

    def test_sales_footer_buttons_are_visible_and_keep_their_text(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"LOCALAPPDATA": folder}, clear=False
        ):
            app = App(
                db_path=Path(folder) / "sales_footer.db",
                maximize=False,
                dpi_scale_override=1.0,
            )
            app.geometry("1600x900")
            app.show_page("sales")
            app.update()
            try:
                tab_bottom = (
                    app.sales_new_tab.winfo_rooty()
                    + app.sales_new_tab.winfo_height()
                )
                expected = (
                    (app.remove_item_button, "REMOVER ITEM"),
                    (app.clear_sale_button, "LIMPAR VENDA"),
                    (app.finish_sale_button, "FINALIZAR VENDA"),
                )
                for button, text in expected:
                    self.assertEqual(text, button.cget("text"))
                    self.assertGreater(button.winfo_height(), 30)
                    self.assertLessEqual(
                        button.winfo_rooty() + button.winfo_height(),
                        tab_bottom,
                    )
            finally:
                app.destroy()

    def test_successful_scan_flashes_the_product_and_confirms_quantity(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"LOCALAPPDATA": folder}, clear=False
        ):
            app = App(
                db_path=Path(folder) / "scan_feedback.db",
                maximize=False,
                dpi_scale_override=1.0,
            )
            app.withdraw()
            app.update()
            try:
                product_id = app.db.add_product("Produto bipado", 2990)
                product = next(
                    row
                    for row in app.db.list_products()
                    if row["id"] == product_id
                )
                app.qty.set("3")
                app.barcode.set(product["barcode"])
                app.scan()

                self.assertEqual(3, app.current_items[0]["quantity"])
                self.assertIn("3x Produto bipado", app.scan_feedback.cget("text"))
                self.assertEqual(
                    ("scan_success",), tuple(app.items.item("0", "tags"))
                )
                self.assertEqual("1", app.qty.get())
                self.assertEqual("", app.barcode.get())
            finally:
                app.destroy()

    def test_money_input_accepts_brazilian_formats_without_float_rounding(self):
        self.assertEqual(123_456, parse_money("R$ 1.234,56"))
        self.assertEqual(123_400, parse_money("1.234"))
        self.assertEqual(1_050, parse_money("10.50"))
        self.assertEqual(29, parse_money("0,29"))
        with self.assertRaises(ValueError):
            parse_money("valor inválido")
        with self.assertRaises(ValueError):
            parse_money("12,345")

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

    def test_invalid_theme_preferences_fall_back_to_light(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "configuracoes.json"
            path.write_text("[]", encoding="utf-8")
            self.assertEqual("light", ThemePreferences(path).load())

    def test_installer_buttons_fit_at_high_dpi(self):
        window = InstallerWindow(dpi_scale_override=1.75)
        window.update()
        try:
            self.assertEqual(256, window.app_icon.width())
            self.assertEqual(256, window.app_icon.height())
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

    def test_product_row_has_clickable_copy_icon(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"LOCALAPPDATA": folder}, clear=False
        ):
            app = App(
                db_path=Path(folder) / "copy_icon.db",
                maximize=False,
                dpi_scale_override=1.0,
            )
            app.withdraw()
            app.update()
            try:
                product_id = app.db.add_product("Produto com ícone", 4590)
                app.refresh_products()
                item_id = str(product_id)
                values = app.products.item(item_id, "values")
                self.assertEqual(("copy", "print"), app.products["columns"][-2:])
                self.assertEqual("", app.products.heading("copy", "text"))
                self.assertEqual("", app.products.heading("print", "text"))
                self.assertEqual("⧉", values[4])
                self.assertEqual("⎙", values[5])

                with patch.object(
                    app.products, "identify_region", return_value="cell"
                ), patch.object(
                    app.products, "identify_column", return_value="#5"
                ), patch.object(
                    app.products, "identify_row", return_value=item_id
                ):
                    result = app._product_table_click(SimpleNamespace(x=10, y=10))

                self.assertEqual("break", result)
                self.assertEqual(str(values[3]), app.clipboard_get())
                self.assertIn(str(values[3]), app.product_action_status.cget("text"))
            finally:
                app.destroy()

    def test_product_row_print_icon_generates_the_correct_label(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"LOCALAPPDATA": folder}, clear=False
        ):
            app = App(
                db_path=Path(folder) / "print_icon.db",
                maximize=False,
                dpi_scale_override=1.0,
            )
            app.withdraw()
            app.update()
            try:
                product_id = app.db.add_product("Etiqueta individual", 7590)
                app.refresh_products()
                item_id = str(product_id)
                values = app.products.item(item_id, "values")

                with patch.object(
                    app.products, "identify_region", return_value="cell"
                ), patch.object(
                    app.products, "identify_column", return_value="#6"
                ), patch.object(
                    app.products, "identify_row", return_value=item_id
                ), patch("sales_control.app.product_label_pdf") as generator, patch.object(
                    app, "open_pdf_for_printing"
                ) as opener:
                    result = app._product_table_click(SimpleNamespace(x=10, y=10))

                self.assertEqual("break", result)
                generated_path, generated_product = generator.call_args.args
                self.assertEqual(values[1], generated_product["name"])
                self.assertEqual(values[3], generated_product["barcode"])
                self.assertEqual(generated_path, opener.call_args.args[0])
                self.assertEqual(
                    "Etiqueta térmica 40 x 25 mm",
                    opener.call_args.kwargs["document_title"],
                )
            finally:
                app.destroy()

    def test_sale_with_archived_client_can_still_be_opened_and_saved(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"LOCALAPPDATA": folder}, clear=False
        ):
            app = App(
                db_path=Path(folder) / "archived_client.db",
                maximize=False,
                dpi_scale_override=1.0,
            )
            app.withdraw()
            app.update()
            try:
                product = app.db.add_product("Produto", 1000)
                client = app.db.add_client("Cliente arquivado")
                sale = app.db.save_sale(
                    client,
                    "2026-08-13",
                    [
                        {
                            "product_id": product,
                            "product_name": "Produto",
                            "quantity": 1,
                            "unit_price_cents": 1000,
                        }
                    ],
                )
                app.db.delete_client(client)
                app.refresh_clients()
                app.refresh_sales()
                app.sales_tree.selection_set(app.sales_tree.get_children()[0])
                with patch("sales_control.app.messagebox.showinfo"):
                    app.edit_sale()
                self.assertEqual("Cliente arquivado", app.sale_client.get())
                with patch("sales_control.app.messagebox.showinfo"):
                    app.finish_sale()
                self.assertEqual(1000, app.db.get_sale(sale)[0]["total_cents"])
            finally:
                app.destroy()

    def test_revenue_pdf_is_not_requested_for_an_invalid_period(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"LOCALAPPDATA": folder}, clear=False
        ):
            app = App(
                db_path=Path(folder) / "invalid_period.db",
                maximize=False,
                dpi_scale_override=1.0,
            )
            app.withdraw()
            app.update()
            try:
                app.start.set("2026-08-31")
                app.end.set("2026-08-01")
                with patch("sales_control.app.messagebox.showerror") as error, patch(
                    "sales_control.app.filedialog.asksaveasfilename"
                ) as save_dialog:
                    app.revenue_report_pdf()
                error.assert_called_once()
                save_dialog.assert_not_called()
            finally:
                app.destroy()


if __name__ == "__main__":
    unittest.main()
