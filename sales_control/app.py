from __future__ import annotations

import calendar
import ctypes
import os
import threading
import tkinter as tk
import webbrowser
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageDraw, ImageTk

from . import __version__
from .branding import app_icon_png_path
from .database import Database
from .date_input import DateField, display_date, iso_date
from .motion import MotionController
from .reports import money, product_label_pdf, product_pdf, revenue_pdf
from .theme import THEMES, ThemePreferences, get_theme, preferred_font
from .updater import (
    UpdateError,
    check_for_update,
    configured_repository,
    download_update,
    launch_installer,
    launch_rollback,
    rollback_available,
)

FONT_FAMILY = "Segoe UI"


def _apply_palette(theme_key: str):
    global NAVY, NAVY_LIGHT, BLUE, BLUE_HOVER, BLUE_PRESSED
    global CYAN, GREEN, GREEN_HOVER, RED, DANGER_BG, DANGER_HOVER
    global BG, PANEL, TEXT, MUTED, BORDER, FIELD, SOFT, SOFT_HOVER
    global HEADING, SELECTED, NAV_TEXT, NAV_MUTED, HERO_TEXT, PURPLE, SHADOW

    palette = get_theme(theme_key)
    NAVY = palette["navy"]
    NAVY_LIGHT = palette["navy_light"]
    BLUE = palette["accent"]
    BLUE_HOVER = palette["accent_hover"]
    BLUE_PRESSED = palette["accent_pressed"]
    CYAN = palette["cyan"]
    GREEN = palette["success"]
    GREEN_HOVER = palette["success_hover"]
    RED = palette["danger"]
    DANGER_BG = palette["danger_bg"]
    DANGER_HOVER = palette["danger_hover"]
    BG = palette["background"]
    PANEL = palette["panel"]
    TEXT = palette["text"]
    MUTED = palette["muted"]
    BORDER = palette["border"]
    FIELD = palette["field"]
    SOFT = palette["soft"]
    SOFT_HOVER = palette["soft_hover"]
    HEADING = palette["heading"]
    SELECTED = palette["selected"]
    NAV_TEXT = palette["nav_text"]
    NAV_MUTED = palette["nav_muted"]
    HERO_TEXT = palette["hero_text"]
    PURPLE = palette["purple"]
    SHADOW = palette["shadow"]


_apply_palette("light")


def _enable_per_monitor_dpi():
    if os.name != "nt":
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def parse_money(text):
    cleaned = str(text).strip().replace("R$", "").replace(" ", "")
    if not cleaned:
        raise ValueError("Informe um valor válido.")
    if "," in cleaned:
        if cleaned.count(",") != 1:
            raise ValueError("Informe um valor válido, como 19,90.")
        whole, fraction = cleaned.rsplit(",", 1)
        if len(fraction) > 2:
            raise ValueError("Use no máximo duas casas decimais.")
        cleaned = whole.replace(".", "") + "." + (fraction or "0")
    elif cleaned.count(".") == 1:
        whole, fraction = cleaned.rsplit(".", 1)
        if len(fraction) == 3 and fraction.isdigit():
            cleaned = whole + fraction
        elif len(fraction) > 2:
            raise ValueError("Use no máximo duas casas decimais.")
    elif cleaned.count(".") > 1:
        groups = cleaned.lstrip("+-").split(".")
        if not groups[0].isdigit() or any(
            len(group) != 3 or not group.isdigit() for group in groups[1:]
        ):
            raise ValueError("Informe um valor válido, como 1.234,56.")
        cleaned = cleaned.replace(".", "")
    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("Informe um valor válido.") from exc
    if not value.is_finite():
        raise ValueError("Informe um valor válido.")
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class UpdateOfferDialog(tk.Toplevel):
    def __init__(self, parent, info, on_download):
        super().__init__(parent)
        self.title("Atualização disponível")
        self.configure(bg=BG)
        self.geometry(f"{parent.px(620)}x{parent.px(510)}")
        self.minsize(parent.px(540), parent.px(430))
        self.transient(parent)
        self.grab_set()

        header = tk.Frame(self, bg=NAVY, height=parent.px(92))
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="NOVA ATUALIZAÇÃO", bg=NAVY, fg="white", font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=26, pady=(18, 2))
        tk.Label(header, text=info.title, bg=NAVY, fg=NAV_MUTED, font=(FONT_FAMILY, 9)).pack(anchor="w", padx=27)

        body = tk.Frame(self, bg=PANEL, padx=26, pady=22)
        body.pack(fill="both", expand=True, padx=18, pady=18)
        versions = tk.Frame(body, bg=SOFT, padx=16, pady=12)
        versions.pack(fill="x")
        tk.Label(versions, text=f"Versão instalada: {__version__}", bg=SOFT, fg=MUTED, font=(FONT_FAMILY, 10, "bold")).pack(side="left")
        tk.Label(versions, text=f"Nova versão: {info.version}", bg=SOFT, fg=GREEN, font=(FONT_FAMILY, 11, "bold")).pack(side="right")
        tk.Label(body, text="Descrição da atualização", bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 10, "bold")).pack(anchor="w", pady=(16, 6))
        notes = tk.Text(body, height=9, wrap="word", bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat", padx=12, pady=10, font=(FONT_FAMILY, 9))
        notes.pack(fill="both", expand=True)
        notes.insert("1.0", info.notes)
        notes.config(state="disabled")

        actions = tk.Frame(body, bg=PANEL)
        actions.pack(fill="x", pady=(16, 0))
        ttk.Button(actions, text="Agora não", command=self.destroy).pack(side="right")

        def accept():
            self.destroy()
            on_download(info)

        ttk.Button(actions, text="Baixar atualização", style="Accent.TButton", command=accept).pack(side="right", padx=(0, 10))


class DownloadDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Baixando atualização")
        self.configure(bg=PANEL)
        self.geometry(f"{parent.px(520)}x{parent.px(190)}")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", lambda: None)
        tk.Label(self, text="Baixando o instalador oficial", bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 14, "bold")).pack(anchor="w", padx=26, pady=(25, 4))
        self.status = tk.Label(self, text="Preparando download e validação...", bg=PANEL, fg=MUTED, font=("Segoe UI", 9))
        self.status.pack(anchor="w", padx=27)
        self.bar = ttk.Progressbar(self, maximum=100, mode="determinate")
        self.bar.pack(fill="x", padx=27, pady=(18, 6))
        tk.Label(self, text="A instalação só começará depois da sua confirmação.", bg=PANEL, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=27)

    def set_progress(self, downloaded, total):
        if total:
            percent = min(100, int(downloaded * 100 / total))
            self.bar["value"] = percent
            self.status.config(text=f"Baixando... {percent}%")
        else:
            self.status.config(text=f"Baixados {downloaded / (1024 * 1024):.1f} MB")


class ProductEditDialog(tk.Toplevel):
    def __init__(self, parent, name, price):
        super().__init__(parent)
        self.result = None
        self.title("Editar produto")
        self.configure(bg=BG)
        self.geometry(f"{parent.px(520)}x{parent.px(340)}")
        self.minsize(parent.px(480), parent.px(320))
        self.transient(parent)
        self.grab_set()

        body = tk.Frame(self, bg=PANEL, padx=parent.px(28), pady=parent.px(26), highlightthickness=1, highlightbackground=BORDER)
        body.pack(fill="both", expand=True, padx=parent.px(18), pady=parent.px(18))
        tk.Label(body, text="Editar produto", bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 16, "bold")).pack(anchor="w")
        tk.Label(body, text="Altere o nome e o preço no mesmo formulário.", bg=PANEL, fg=MUTED, font=(FONT_FAMILY, 9)).pack(anchor="w", pady=(parent.px(4), parent.px(18)))

        self.name = tk.StringVar(value=name)
        self.price = tk.StringVar(value=price)
        tk.Label(body, text="Nome do produto", bg=PANEL, fg=MUTED, font=(FONT_FAMILY, 9, "bold")).pack(anchor="w")
        name_entry = ttk.Entry(body, textvariable=self.name)
        name_entry.pack(fill="x", pady=(parent.px(5), parent.px(14)))
        tk.Label(body, text="Preço de venda (R$)", bg=PANEL, fg=MUTED, font=(FONT_FAMILY, 9, "bold")).pack(anchor="w")
        price_entry = ttk.Entry(body, textvariable=self.price)
        price_entry.pack(fill="x", pady=(parent.px(5), parent.px(20)))

        actions = tk.Frame(body, bg=PANEL)
        actions.pack(fill="x")
        ttk.Button(actions, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(actions, text="Salvar alterações", style="Accent.TButton", command=self._save).pack(side="right", padx=(0, parent.px(10)))
        self.bind("<Return>", lambda _event: self._save())
        self.bind("<Escape>", lambda _event: self.destroy())
        name_entry.focus_set()
        name_entry.selection_range(0, "end")

    def _save(self):
        try:
            name = self.name.get().strip()
            if not name:
                raise ValueError("Informe o nome do produto.")
            price_cents = parse_money(self.price.get())
            if price_cents < 0:
                raise ValueError("O preço não pode ser negativo.")
            self.result = (name, price_cents)
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Editar produto", str(exc), parent=self)


class App(tk.Tk):
    def __init__(self, db_path=None, maximize=True, dpi_scale_override=None):
        _enable_per_monitor_dpi()
        super().__init__()
        detected_dpi = float(dpi_scale_override * 96 if dpi_scale_override else self.winfo_fpixels("1i"))
        self.dpi_scale = max(1.0, min(3.0, detected_dpi / 96.0))
        self.tk.call("tk", "scaling", detected_dpi / 72.0)
        global FONT_FAMILY
        FONT_FAMILY = preferred_font(self)
        self.title("Vendas PRO - Controle de Vendas")
        self.geometry(f"{self.px(1600)}x{self.px(900)}")
        self.minsize(self.px(1080), self.px(680))
        base = Path(os.getenv("LOCALAPPDATA", Path.home())) / "ControleDeVendas"
        self.theme_preferences = ThemePreferences(base / "configuracoes.json")
        self.theme_key = self.theme_preferences.load()
        _apply_palette(self.theme_key)
        self.configure(bg=BG)
        self.db = Database(db_path or base / "controle_vendas.db")
        self.current_items = []
        self.editing_sale_id = None
        self.editing_client_id = None
        self.client_map = {}
        self.report_client_map = {"Todos os clientes": None}
        self.pages = {}
        self.nav_buttons = {}
        self.icons = {}
        self.current_page = "home"
        self._focus_job = None
        self._scan_animation_jobs = []
        self.motion = MotionController(self, self.px)
        self._style()
        self._create_icons()
        self._build_shell()
        self._build_home()
        self._build_sales()
        self._build_products()
        self._build_clients()
        self._build_reports()
        self._build_settings()
        self.refresh_all()
        self.show_page("home")
        self._startup_jobs = []
        if maximize:
            self._startup_jobs.append(self.after(80, self._maximize_window))
        self._startup_jobs.append(
            self.after(3000, lambda: self.check_updates(silent=True))
        )

    def destroy(self):
        self._cancel_barcode_focus()
        self._cancel_scan_animation()
        self.motion.cancel_all()
        for job in getattr(self, "_startup_jobs", ()):
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
        self._startup_jobs = []
        super().destroy()

    def _cancel_barcode_focus(self):
        job = getattr(self, "_focus_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
            self._focus_job = None

    def _schedule_barcode_focus(self):
        self._cancel_barcode_focus()

        def focus_if_visible():
            self._focus_job = None
            if self.current_page == "sales" and self.barcode_entry.winfo_exists():
                self.barcode_entry.focus_set()

        self._focus_job = self.after(100, focus_if_visible)

    def _cancel_scan_animation(self):
        for job in getattr(self, "_scan_animation_jobs", ()):
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
        self._scan_animation_jobs = []

    def _animate_scan_success(self, item_index, product_name, quantity):
        self._cancel_scan_animation()
        item_id = str(item_index)
        if self.items.exists(item_id):
            self.items.item(item_id, tags=("scan_success",))
            self.items.focus(item_id)
            self.items.see(item_id)
        self.scan_feedback.config(
            text=f"✓  {quantity}x {product_name} adicionado",
            fg=GREEN,
            font=(FONT_FAMILY, 9, "bold"),
        )

        def soften():
            if self.items.winfo_exists() and self.items.exists(item_id):
                self.items.item(item_id, tags=("scan_success_soft",))
            if self.scan_feedback.winfo_exists():
                self.scan_feedback.config(fg=GREEN_HOVER)

        def brighten():
            if self.items.winfo_exists() and self.items.exists(item_id):
                self.items.item(item_id, tags=("scan_success",))
            if self.scan_feedback.winfo_exists():
                self.scan_feedback.config(fg=GREEN)

        def finish():
            self._scan_animation_jobs = []
            if self.items.winfo_exists() and self.items.exists(item_id):
                self.items.item(item_id, tags=())
            if self.scan_feedback.winfo_exists():
                self.scan_feedback.config(
                    text="Pronto para a próxima bipagem",
                    fg=MUTED,
                    font=(FONT_FAMILY, 9),
                )

        self._scan_animation_jobs = [
            self.after(110, soften),
            self.after(230, brighten),
            self.after(850, finish),
        ]

    def px(self, value):
        return max(1, int(round(value * self.dpi_scale)))

    def _maximize_window(self):
        try:
            self.state("zoomed")
        except tk.TclError:
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            self.geometry(f"{screen_w}x{screen_h}+0+0")

    def _style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TButton", font=(FONT_FAMILY, 10), padding=(self.px(16), self.px(10)), background=SOFT, foreground=TEXT, bordercolor=BORDER, borderwidth=0, focusthickness=0)
        style.map("TButton", background=[("active", SOFT_HOVER), ("pressed", BORDER)], foreground=[("disabled", MUTED)])
        style.configure("Accent.TButton", background=BLUE, foreground="white", font=(FONT_FAMILY, 10, "bold"), padding=(self.px(20), self.px(11)), borderwidth=0)
        style.map("Accent.TButton", background=[("active", BLUE_HOVER), ("pressed", BLUE_PRESSED)], foreground=[("disabled", NAV_MUTED)])
        style.configure("Success.TButton", background=GREEN, foreground="white", font=(FONT_FAMILY, 10, "bold"), padding=(self.px(20), self.px(11)), borderwidth=0)
        style.map("Success.TButton", background=[("active", GREEN_HOVER)])
        style.configure("Danger.TButton", background=DANGER_BG, foreground=RED, font=(FONT_FAMILY, 10, "bold"), padding=(self.px(16), self.px(10)), borderwidth=0)
        style.map("Danger.TButton", background=[("active", DANGER_HOVER)])
        style.configure(
            "Calendar.TButton",
            background=SOFT,
            bordercolor=BORDER,
            borderwidth=0,
            padding=(self.px(10), self.px(9)),
        )
        style.map(
            "Calendar.TButton",
            background=[("active", SOFT_HOVER), ("pressed", SELECTED)],
        )
        style.configure("TEntry", padding=self.px(10), fieldbackground=FIELD, foreground=TEXT, insertcolor=TEXT, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER)
        style.configure("TCombobox", padding=self.px(9), fieldbackground=FIELD, foreground=TEXT, bordercolor=BORDER, arrowcolor=BLUE)
        style.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", TEXT)])
        style.configure("TSpinbox", padding=self.px(9), fieldbackground=FIELD, foreground=TEXT, arrowcolor=BLUE, bordercolor=BORDER)
        style.configure("Treeview", font=(FONT_FAMILY, 10), rowheight=self.px(42), background=PANEL, fieldbackground=PANEL, foreground=TEXT, bordercolor=BORDER, borderwidth=0)
        style.map("Treeview", background=[("selected", SELECTED)], foreground=[("selected", TEXT)])
        style.configure("Treeview.Heading", font=(FONT_FAMILY, 10, "bold"), background=HEADING, foreground=TEXT, padding=(self.px(12), self.px(12)), borderwidth=0)
        style.map("Treeview.Heading", background=[("active", SOFT_HOVER)])
        style.configure(
            "Inner.TNotebook",
            background=PANEL,
            borderwidth=0,
            tabmargins=(0, self.px(8), 0, self.px(8)),
        )
        style.configure(
            "Inner.TNotebook.Tab",
            font=(FONT_FAMILY, 10, "bold"),
            padding=(self.px(20), self.px(10)),
            background=SOFT,
            foreground=MUTED,
            borderwidth=0,
        )
        style.map(
            "Inner.TNotebook.Tab",
            background=[
                ("selected", BLUE),
                ("active", SOFT_HOVER),
                ("!selected", SOFT),
            ],
            foreground=[("selected", "white"), ("!selected", MUTED)],
            padding=[
                ("selected", (self.px(28), self.px(17))),
                ("!selected", (self.px(20), self.px(10))),
            ],
        )
        style.configure("Panel.TLabelframe", background=PANEL, bordercolor=BORDER, borderwidth=1, relief="solid")
        style.configure("Panel.TLabelframe.Label", background=PANEL, foreground=TEXT, font=(FONT_FAMILY, 10, "bold"))
        style.configure("Horizontal.TProgressbar", background=BLUE, troughcolor=SOFT, bordercolor=SOFT, lightcolor=BLUE, darkcolor=BLUE)

    def _icon_image(self, kind, size, color):
        display_size = self.px(size)
        render_size = display_size * 4
        scale = render_size / 32
        width = max(5, int(2.1 * scale))
        image = Image.new("RGBA", (render_size, render_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        def point(x, y):
            return int(x * scale), int(y * scale)

        if kind == "home":
            draw.polygon([point(3, 15), point(16, 4), point(29, 15)], outline=color, width=width)
            draw.line([point(7, 14), point(7, 28), point(25, 28), point(25, 14)], fill=color, width=width, joint="curve")
            draw.rectangle([*point(14, 20), *point(19, 28)], outline=color, width=width)
        elif kind == "sales":
            draw.line([point(3, 6), point(7, 6), point(10, 21), point(25, 21), point(29, 10), point(9, 10)], fill=color, width=width, joint="curve")
            draw.ellipse([*point(10, 24), *point(14, 28)], fill=color)
            draw.ellipse([*point(23, 24), *point(27, 28)], fill=color)
        elif kind == "products":
            draw.polygon([point(4, 10), point(16, 4), point(28, 10), point(16, 16)], outline=color, width=width)
            draw.line([point(4, 10), point(4, 24), point(16, 30), point(16, 16)], fill=color, width=width)
            draw.line([point(28, 10), point(28, 24), point(16, 30)], fill=color, width=width)
            draw.line([point(10, 7), point(22, 13), point(22, 18)], fill=color, width=width)
        elif kind == "reports":
            draw.line([point(5, 4), point(5, 28), point(29, 28)], fill=color, width=width)
            draw.rectangle([*point(9, 18), *point(13, 26)], fill=color)
            draw.rectangle([*point(17, 12), *point(21, 26)], fill=color)
            draw.rectangle([*point(25, 6), *point(29, 26)], fill=color)
        elif kind == "clients":
            draw.ellipse([*point(11, 3), *point(21, 13)], outline=color, width=width)
            draw.arc([*point(6, 13), *point(26, 31)], start=185, end=355, fill=color, width=width)
            draw.ellipse([*point(23, 8), *point(29, 14)], outline=color, width=width)
            draw.arc([*point(21, 14), *point(32, 27)], start=190, end=335, fill=color, width=width)
        elif kind == "backup":
            draw.arc([*point(5, 5), *point(27, 27)], start=40, end=315, fill=color, width=width)
            draw.polygon([point(4, 8), point(11, 7), point(7, 14)], fill=color)
            draw.line([point(10, 26), point(22, 26)], fill=color, width=width)
        elif kind == "update":
            draw.arc([*point(5, 5), *point(27, 27)], start=205, end=520, fill=color, width=width)
            draw.polygon([point(25, 3), point(29, 11), point(20, 10)], fill=color)
            draw.line([point(16, 8), point(16, 23)], fill=color, width=width)
            draw.polygon([point(10, 18), point(16, 25), point(22, 18)], fill=color)
        elif kind == "settings":
            draw.ellipse([*point(11, 11), *point(21, 21)], outline=color, width=width)
            draw.ellipse([*point(5, 5), *point(27, 27)], outline=color, width=width)
            for start, end in [((16, 1), (16, 6)), ((16, 26), (16, 31)), ((1, 16), (6, 16)), ((26, 16), (31, 16))]:
                draw.line([point(*start), point(*end)], fill=color, width=width)
        elif kind == "calendar":
            draw.rounded_rectangle(
                [*point(4, 6), *point(28, 29)],
                radius=max(2, int(2.5 * scale)),
                outline=color,
                width=width,
            )
            draw.line([point(4, 13), point(28, 13)], fill=color, width=width)
            draw.line([point(10, 3), point(10, 9)], fill=color, width=width)
            draw.line([point(22, 3), point(22, 9)], fill=color, width=width)
            for x in (10, 16, 22):
                for y in (18, 24):
                    radius = max(1, int(1.2 * scale))
                    center_x, center_y = point(x, y)
                    draw.ellipse(
                        [
                            center_x - radius,
                            center_y - radius,
                            center_x + radius,
                            center_y + radius,
                        ],
                        fill=color,
                    )
        image = image.resize((display_size, display_size), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(image)

    def _create_icons(self):
        for kind in ("home", "sales", "products", "clients", "reports", "settings", "backup", "update"):
            self.icons[f"nav_{kind}"] = self._icon_image(kind, 24, "white")
            self.icons[f"card_{kind}"] = self._icon_image(kind, 50, BLUE)
        with Image.open(app_icon_png_path()) as source:
            artwork = source.convert("RGBA")
            app_icons = [
                ImageTk.PhotoImage(
                    artwork.resize((size, size), Image.Resampling.LANCZOS)
                )
                for size in (16, 32, 48, 256)
            ]
        self.icons["app_sizes"] = app_icons
        self.icons["app"] = app_icons[-1]
        self.icons["calendar"] = self._icon_image("calendar", 20, BLUE)
        self.iconphoto(True, *app_icons)

    def _build_shell(self):
        sidebar = tk.Frame(self, bg=NAVY, width=self.px(255))
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        brand = tk.Frame(sidebar, bg=NAVY, height=self.px(105))
        brand.pack(fill="x")
        brand.pack_propagate(False)
        tk.Label(brand, text="VENDAS", bg=NAVY, fg="white", font=("Segoe UI", 22, "bold")).pack(anchor="w", padx=24, pady=(23, 0))
        tk.Label(brand, text="PRO  •  GESTÃO LOCAL", bg=NAVY, fg=NAV_MUTED, font=(FONT_FAMILY, 8, "bold")).pack(anchor="w", padx=26)
        tk.Frame(sidebar, bg=NAVY_LIGHT, height=1).pack(fill="x", padx=18, pady=(0, 17))

        nav_items = [
            ("home", "Início"),
            ("sales", "Vendas"),
            ("products", "Produtos"),
            ("clients", "Clientes"),
            ("reports", "Relatórios"),
            ("settings", "Configurações"),
        ]
        for key, label in nav_items:
            button = tk.Button(
                sidebar,
                text=label,
                image=self.icons[f"nav_{key}"],
                compound="left",
                anchor="w",
                padx=self.px(23),
                pady=self.px(11),
                bg=NAVY,
                fg=NAV_TEXT,
                activebackground=NAVY_LIGHT,
                activeforeground="white",
                relief="flat",
                borderwidth=0,
                font=("Segoe UI Semibold", 11),
                cursor="hand2",
                command=lambda page=key: self.show_page(page),
            )
            button.pack(fill="x", padx=self.px(10), pady=self.px(3))
            self.nav_buttons[key] = button

        tk.Frame(sidebar, bg=NAVY).pack(fill="both", expand=True)
        self.update_button = tk.Button(
            sidebar,
            text="Buscar atualização",
            image=self.icons["nav_update"],
            compound="left",
            anchor="w",
            padx=self.px(23),
            pady=self.px(10),
            bg=NAVY_LIGHT,
            fg="white",
            activebackground=BLUE,
            activeforeground="white",
            relief="flat",
            borderwidth=0,
            font=("Segoe UI Semibold", 9),
            cursor="hand2",
            command=self.check_updates,
        )
        self.update_button.pack(fill="x", padx=self.px(10), pady=(self.px(3), self.px(6)))
        tk.Button(
            sidebar,
            text="Fazer backup",
            image=self.icons["nav_backup"],
            compound="left",
            anchor="w",
            padx=self.px(23),
            pady=self.px(10),
            bg=NAVY_LIGHT,
            fg="white",
            activebackground=BLUE,
            activeforeground="white",
            relief="flat",
            borderwidth=0,
            font=("Segoe UI Semibold", 10),
            cursor="hand2",
            command=self.backup,
        ).pack(fill="x", padx=self.px(10), pady=(self.px(3), self.px(10)))
        tk.Label(sidebar, text=f"BANCO LOCAL • VERSÃO {__version__}", bg=NAVY, fg=NAV_MUTED, font=(FONT_FAMILY, 8)).pack(pady=(0, self.px(12)))

        main = tk.Frame(self, bg=BG)
        main.pack(side="left", fill="both", expand=True)
        header = tk.Frame(main, bg=PANEL, height=self.px(82), highlightthickness=1, highlightbackground=BORDER)
        header.pack(fill="x")
        header.pack_propagate(False)
        title_box = tk.Frame(header, bg=PANEL)
        title_box.pack(side="left", fill="y", padx=30)
        self.header_title = tk.Label(title_box, text="Início", bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 19, "bold"))
        self.header_title.pack(anchor="w", pady=(14, 0))
        self.header_subtitle = tk.Label(title_box, text="Visão geral da operação", bg=PANEL, fg=MUTED, font=("Segoe UI", 9))
        self.header_subtitle.pack(anchor="w")
        today_box = tk.Frame(header, bg=PANEL)
        today_box.pack(side="right", fill="y", padx=30)
        tk.Label(today_box, text="HOJE", bg=PANEL, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(anchor="e", pady=(18, 1))
        tk.Label(today_box, text=datetime.now().strftime("%d/%m/%Y"), bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 11, "bold")).pack(anchor="e")

        self.content = tk.Frame(main, bg=BG)
        self.content.pack(fill="both", expand=True, padx=self.px(26), pady=self.px(22))

    def _new_page(self, key):
        page = tk.Frame(self.content, bg=BG)
        page.place(x=0, y=0, relwidth=1.0, relheight=1.0)
        self.pages[key] = page
        return page

    def _panel(self, parent, **grid_options):
        frame = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        if grid_options:
            frame.grid(**grid_options)
        return frame

    def _build_home(self):
        page = self._new_page("home")
        page.grid_columnconfigure((0, 1, 2), weight=1, uniform="home")
        page.grid_rowconfigure(3, weight=1)

        hero = tk.Frame(page, bg=BLUE, height=self.px(125))
        hero.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 16))
        hero.grid_propagate(False)
        tk.Label(hero, text="Bem-vindo ao seu controle de vendas", bg=BLUE, fg="white", font=("Segoe UI", 21, "bold")).pack(anchor="w", padx=28, pady=(24, 3))
        tk.Label(hero, text="Cadastre, bipe e acompanhe o faturamento da empresa em um só lugar.", bg=BLUE, fg=HERO_TEXT, font=(FONT_FAMILY, 10)).pack(anchor="w", padx=30)

        cards = [
            ("sales", "Nova venda", "Inicie uma venda por bipagem", "sales"),
            ("products", "Cadastrar produto", "Crie produto e código automático", "products"),
            ("reports", "Ver faturamento", "Consulte valores por período", "reports"),
        ]
        for column, (key, title, description, page_key) in enumerate(cards):
            card = self._panel(page, row=1, column=column, sticky="nsew", padx=(0 if column == 0 else 7, 0 if column == 2 else 7), pady=(0, 16))
            card.configure(cursor="hand2")
            tk.Label(card, image=self.icons[f"card_{key}"], bg=PANEL).pack(side="left", padx=(22, 16), pady=19)
            text_box = tk.Frame(card, bg=PANEL)
            text_box.pack(side="left", fill="both", expand=True, pady=18)
            tk.Label(text_box, text=title, bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 12, "bold")).pack(anchor="w")
            tk.Label(text_box, text=description, bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 0))
            arrow = tk.Label(card, text="›", bg=PANEL, fg=BLUE, font=("Segoe UI", 24))
            arrow.pack(side="right", padx=20)
            for widget in (card, text_box, arrow, *card.winfo_children()):
                widget.bind("<Button-1>", lambda _event, target=page_key: self.show_page(target))

        stats = tk.Frame(page, bg=BG)
        stats.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0, 16))
        for i in range(4):
            stats.grid_columnconfigure(i, weight=1, uniform="stats")
        self.stat_labels = {}
        stat_specs = [
            ("revenue", "FATURAMENTO DO MÊS", GREEN),
            ("sales", "VENDAS NO MÊS", BLUE),
            ("products", "PRODUTOS ATIVOS", CYAN),
            ("clients", "CLIENTES", PURPLE),
        ]
        for column, (key, label, accent) in enumerate(stat_specs):
            card = tk.Frame(stats, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
            card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 7, 0 if column == 3 else 7))
            tk.Frame(card, bg=accent, width=self.px(5)).pack(side="left", fill="y")
            box = tk.Frame(card, bg=PANEL)
            box.pack(fill="both", expand=True, padx=17, pady=15)
            tk.Label(box, text=label, bg=PANEL, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(anchor="w")
            value = tk.Label(box, text="0", bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 18, "bold"))
            value.pack(anchor="w", pady=(3, 0))
            self.stat_labels[key] = value

        recent = self._panel(page, row=3, column=0, columnspan=3, sticky="nsew")
        recent.grid_rowconfigure(1, weight=1)
        recent.grid_columnconfigure(0, weight=1)
        recent_header = tk.Frame(recent, bg=PANEL)
        recent_header.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))
        tk.Label(recent_header, text="Vendas recentes", bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 12, "bold")).pack(side="left")
        tk.Button(recent_header, text="Ver histórico  ›", bg=PANEL, fg=BLUE, activebackground=PANEL, activeforeground=BLUE_HOVER, relief="flat", borderwidth=0, font=("Segoe UI Semibold", 9), cursor="hand2", command=lambda: self.show_page("sales", history=True)).pack(side="right")
        self.recent_tree = ttk.Treeview(recent, columns=("id", "date", "client", "items", "total"), show="headings", height=6)
        for column, title, width, _anchor in [
            ("id", "VENDA", self.px(90), "w"), ("date", "DATA", self.px(130), "w"), ("client", "CLIENTE", self.px(520), "w"), ("items", "ITENS", self.px(100), "center"), ("total", "VALOR", self.px(170), "e")
        ]:
            self.recent_tree.heading(column, text=title, anchor="center")
            self.recent_tree.column(column, width=width, anchor="center")
        self.recent_tree.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 18))

    def _module_title(self, parent, title, description):
        header = tk.Frame(parent, bg=BG)
        header.pack(fill="x", pady=(0, 14))
        tk.Label(header, text=title, bg=BG, fg=TEXT, font=(FONT_FAMILY, 17, "bold")).pack(anchor="w")
        tk.Label(header, text=description, bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 0))

    def _build_sales(self):
        page = self._new_page("sales")
        self._module_title(page, "Módulo de Vendas", "Bipe produtos rapidamente e consulte todas as vendas registradas.")
        panel = self._panel(page)
        panel.pack(fill="both", expand=True)
        self.sales_inner = ttk.Notebook(panel, style="Inner.TNotebook")
        self.sales_inner.pack(fill="both", expand=True, padx=18, pady=18)
        new = tk.Frame(self.sales_inner, bg=PANEL, padx=4, pady=8)
        history = tk.Frame(self.sales_inner, bg=PANEL, padx=4, pady=8)
        self.sales_new_tab = new
        self.sales_history_tab = history
        self.sales_inner.add(new, text="  Nova venda  ")
        self.sales_inner.add(history, text="  Histórico de vendas  ")

        form = tk.Frame(new, bg=PANEL)
        form.pack(fill="x")
        for column in range(5):
            form.grid_columnconfigure(column, weight=1 if column == 1 else 0)
        self._field_label(form, "Data da venda", 0, 0)
        self._field_label(form, "Cliente / usuário", 0, 1, padx=(14, 0))
        self._field_label(form, "Quantidade antes da bipagem", 0, 3, padx=(14, 0))
        self.sale_date = tk.StringVar(value=display_date(date.today()))
        self.sale_date_field = self._date_field(form, self.sale_date)
        self.sale_date_field.grid(row=1, column=0, sticky="w")
        self.sale_client = ttk.Combobox(form, state="readonly", width=42)
        self.sale_client.grid(row=1, column=1, padx=(14, 6), sticky="ew")
        ttk.Button(form, text="+ Novo cliente", command=self.add_client).grid(row=1, column=2)
        self.qty = tk.StringVar(value="1")
        ttk.Spinbox(form, from_=1, to=9999, textvariable=self.qty, width=12).grid(row=1, column=3, padx=(14, 0), sticky="w")

        scan = ttk.LabelFrame(new, text="  BIPAGEM DE PRODUTO  ", padding=14, style="Panel.TLabelframe")
        scan.pack(fill="x", pady=16)
        tk.Label(scan, text="Código de barras", bg=PANEL, fg=MUTED, font=("Segoe UI Semibold", 9)).pack(side="left")
        self.barcode = tk.StringVar()
        self.barcode_entry = ttk.Entry(scan, textvariable=self.barcode, font=("Consolas", 16))
        self.barcode_entry.pack(side="left", fill="x", expand=True, padx=12)
        self.barcode_entry.bind("<Return>", lambda _event: self.scan())
        self.scan_feedback = tk.Label(
            scan,
            text="Pronto para bipar",
            bg=PANEL,
            fg=MUTED,
            font=(FONT_FAMILY, 9),
            width=29,
            anchor="e",
        )
        self.scan_feedback.pack(side="left", padx=(0, self.px(12)))
        ttk.Button(scan, text="ADICIONAR ITEM", style="Accent.TButton", command=self.scan).pack(side="left")

        actions = tk.Frame(new, bg=PANEL)
        actions.pack(side="bottom", fill="x", pady=(14, 0))
        self.remove_item_button = ttk.Button(
            actions,
            text="REMOVER ITEM",
            style="Danger.TButton",
            command=self.remove_item,
        )
        self.remove_item_button.pack(side="left")
        self.clear_sale_button = ttk.Button(
            actions,
            text="LIMPAR VENDA",
            style="TButton",
            command=self.clear_sale,
        )
        self.clear_sale_button.pack(side="left", padx=8)
        self.finish_sale_button = ttk.Button(
            actions,
            text="FINALIZAR VENDA",
            style="Success.TButton",
            command=self.finish_sale,
        )
        self.finish_sale_button.pack(side="right")
        self.sale_total = tk.Label(actions, text="TOTAL: R$ 0,00", bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 18, "bold"))
        self.sale_total.pack(side="right", padx=24)

        table_box = tk.Frame(new, bg=PANEL)
        table_box.pack(fill="both", expand=True)
        self.items = ttk.Treeview(table_box, columns=("product", "qty", "unit", "subtotal"), show="headings", height=5)
        for column, title, width, _anchor in [
            ("product", "PRODUTO", self.px(620), "w"), ("qty", "QUANTIDADE", self.px(140), "center"), ("unit", "VALOR UNITÁRIO", self.px(180), "e"), ("subtotal", "SUBTOTAL", self.px(190), "e")
        ]:
            self.items.heading(column, text=title, anchor="center")
            self.items.column(column, width=width, anchor="center")
        self.items.tag_configure("scan_success", background=GREEN, foreground="white")
        self.items.tag_configure("scan_success_soft", background=SELECTED, foreground=TEXT)
        self.items.pack(fill="both", expand=True)

        history_header = tk.Frame(history, bg=PANEL)
        history_header.pack(fill="x", pady=(0, 12))
        tk.Label(history_header, text="Vendas registradas", bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 13, "bold")).pack(side="left")
        ttk.Button(history_header, text="Atualizar lista", command=self.refresh_sales).pack(side="right")
        self.sales_tree = ttk.Treeview(history, columns=("id", "date", "client", "items", "total"), show="headings", height=6)
        for column, title, width, _anchor in [
            ("id", "VENDA", self.px(100), "w"), ("date", "DATA", self.px(140), "w"), ("client", "CLIENTE", self.px(600), "w"), ("items", "ITENS", self.px(120), "center"), ("total", "VALOR", self.px(190), "e")
        ]:
            self.sales_tree.heading(column, text=title, anchor="center")
            self.sales_tree.column(column, width=width, anchor="center")
        self.sales_tree.pack(fill="both", expand=True)
        history_actions = tk.Frame(history, bg=PANEL)
        history_actions.pack(fill="x", pady=(14, 0))
        ttk.Button(history_actions, text="Abrir e editar venda", style="Accent.TButton", command=self.edit_sale).pack(side="left")
        ttk.Button(history_actions, text="Excluir venda", style="Danger.TButton", command=self.delete_sale).pack(side="left", padx=8)

    def _build_products(self):
        page = self._new_page("products")
        self._module_title(page, "Módulo de Produtos", "Cadastre produtos, pesquise e gere uma lista pronta para impressão.")
        panel = self._panel(page)
        panel.pack(fill="both", expand=True)

        form = tk.Frame(panel, bg=PANEL)
        form.pack(fill="x", padx=22, pady=(20, 15))
        form.grid_columnconfigure(0, weight=1)
        self._field_label(form, "Nome do produto", 0, 0)
        self._field_label(form, "Preço de venda (R$)", 0, 1, padx=(12, 0))
        self.prod_name = tk.StringVar()
        self.prod_price = tk.StringVar()
        ttk.Entry(form, textvariable=self.prod_name).grid(row=1, column=0, sticky="ew")
        ttk.Entry(form, textvariable=self.prod_price, width=20).grid(row=1, column=1, padx=(12, 8))
        ttk.Button(form, text="CADASTRAR E GERAR CÓDIGO", style="Accent.TButton", command=self.add_product).grid(row=1, column=2)

        separator = tk.Frame(panel, bg=BORDER, height=1)
        separator.pack(fill="x", padx=22)
        toolbar = tk.Frame(panel, bg=PANEL)
        toolbar.pack(fill="x", padx=22, pady=14)
        tk.Label(toolbar, text="Pesquisar produto", bg=PANEL, fg=MUTED, font=("Segoe UI Semibold", 9)).pack(side="left")
        self.search = tk.StringVar()
        search_entry = ttk.Entry(toolbar, textvariable=self.search, width=48)
        search_entry.pack(side="left", padx=10)
        search_entry.bind("<KeyRelease>", lambda _event: self.refresh_products())
        ttk.Button(toolbar, text="Gerar lista A4 (PDF)", command=self.product_report).pack(side="right")

        self.products = ttk.Treeview(
            panel,
            columns=("id", "name", "price", "barcode", "copy", "print"),
            show="headings",
            height=6,
        )
        for column, title, width, _anchor in [
            ("id", "ID", self.px(70), "center"),
            ("name", "PRODUTO", self.px(520), "center"),
            ("price", "PREÇO", self.px(160), "center"),
            ("barcode", "CÓDIGO DE BARRAS", self.px(270), "center"),
            ("copy", "", self.px(70), "center"),
            ("print", "", self.px(70), "center"),
        ]:
            self.products.heading(column, text=title, anchor="center")
            self.products.column(column, width=width, anchor="center")
        self.products.pack(fill="both", expand=True, padx=22, pady=(0, 10))
        self.products.bind("<ButtonRelease-1>", self._product_table_click)
        self.products.bind("<Double-1>", self._product_table_double_click)
        self.products.bind("<Motion>", self._product_table_motion)
        self.products.bind("<Leave>", lambda _event: self.products.configure(cursor=""))
        actions = tk.Frame(panel, bg=PANEL)
        actions.pack(fill="x", padx=22, pady=(0, 20))
        ttk.Button(actions, text="Editar produto", style="Accent.TButton", command=self.edit_product).pack(side="left")
        ttk.Button(actions, text="Excluir produto", style="Danger.TButton", command=self.delete_product).pack(side="left", padx=8)
        self.product_action_status = tk.Label(
            actions,
            text="",
            bg=PANEL,
            fg=GREEN,
            font=(FONT_FAMILY, 9, "bold"),
        )
        self.product_action_status.pack(side="left", padx=self.px(8))

    def _build_clients(self):
        page = self._new_page("clients")
        self._module_title(page, "Módulo de Clientes", "Cadastre, pesquise e edite clientes vinculados às vendas.")
        panel = self._panel(page)
        panel.pack(fill="both", expand=True)

        form = tk.Frame(panel, bg=PANEL)
        form.pack(fill="x", padx=self.px(22), pady=(self.px(20), self.px(15)))
        form.grid_columnconfigure(0, weight=2)
        form.grid_columnconfigure(1, weight=3)
        self._field_label(form, "Nome do cliente / usuário", 0, 0)
        self._field_label(form, "Observação", 0, 1, padx=(self.px(12), 0))
        self.client_name = tk.StringVar()
        self.client_notes = tk.StringVar()
        ttk.Entry(form, textvariable=self.client_name).grid(row=1, column=0, sticky="ew")
        ttk.Entry(form, textvariable=self.client_notes).grid(row=1, column=1, sticky="ew", padx=(self.px(12), self.px(8)))
        self.client_save_button = ttk.Button(form, text="CADASTRAR CLIENTE", style="Accent.TButton", command=self.save_client)
        self.client_save_button.grid(row=1, column=2)

        separator = tk.Frame(panel, bg=BORDER, height=1)
        separator.pack(fill="x", padx=self.px(22))
        toolbar = tk.Frame(panel, bg=PANEL)
        toolbar.pack(fill="x", padx=self.px(22), pady=self.px(14))
        tk.Label(toolbar, text="Pesquisar cliente", bg=PANEL, fg=MUTED, font=("Segoe UI Semibold", 9)).pack(side="left")
        self.client_search = tk.StringVar()
        client_search_entry = ttk.Entry(toolbar, textvariable=self.client_search, width=48)
        client_search_entry.pack(side="left", padx=self.px(10))
        client_search_entry.bind("<KeyRelease>", lambda _event: self.refresh_client_table())

        self.clients_tree = ttk.Treeview(panel, columns=("id", "name", "notes", "created"), show="headings", height=6)
        for column, title, width, _anchor in [
            ("id", "ID", self.px(80), "w"),
            ("name", "CLIENTE / USUÁRIO", self.px(520), "w"),
            ("notes", "OBSERVAÇÃO", self.px(560), "w"),
            ("created", "CADASTRADO EM", self.px(190), "w"),
        ]:
            self.clients_tree.heading(column, text=title, anchor="center")
            self.clients_tree.column(column, width=width, anchor="center")
        self.clients_tree.pack(fill="both", expand=True, padx=self.px(22), pady=(0, self.px(10)))
        self.clients_tree.bind("<Double-1>", lambda _event: self.begin_client_edit())

        actions = tk.Frame(panel, bg=PANEL)
        actions.pack(fill="x", padx=self.px(22), pady=(0, self.px(20)))
        ttk.Button(actions, text="Editar cliente", style="Accent.TButton", command=self.begin_client_edit).pack(side="left")
        ttk.Button(actions, text="Excluir cliente", style="Danger.TButton", command=self.delete_client).pack(side="left", padx=self.px(8))
        self.client_cancel_button = ttk.Button(actions, text="Cancelar edição", command=self.cancel_client_edit)

    def _build_reports(self):
        page = self._new_page("reports")
        self._module_title(page, "Relatórios", "Analise o faturamento bruto por período e por cliente.")
        panel = self._panel(page)
        panel.pack(fill="both", expand=True)

        filter_box = tk.Frame(panel, bg=SOFT, highlightthickness=1, highlightbackground=BORDER)
        filter_box.pack(fill="x", padx=22, pady=20)
        filter_box.grid_columnconfigure(2, weight=1)
        self.start = tk.StringVar(value=display_date(date.today().replace(day=1)))
        self.end = tk.StringVar(value=display_date(date.today()))
        self._field_label(filter_box, "Data inicial", 0, 0, bg=SOFT)
        self._field_label(filter_box, "Data final", 0, 1, padx=(12, 0), bg=SOFT)
        self._field_label(filter_box, "Cliente", 0, 2, padx=(12, 0), bg=SOFT)
        self.start_date_field = self._date_field(
            filter_box,
            self.start,
            background=SOFT,
        )
        self.start_date_field.grid(
            row=1,
            column=0,
            sticky="w",
            pady=(0, 15),
            padx=(15, 0),
        )
        self.end_date_field = self._date_field(
            filter_box,
            self.end,
            background=SOFT,
        )
        self.end_date_field.grid(
            row=1,
            column=1,
            sticky="w",
            padx=(12, 0),
            pady=(0, 15),
        )
        self.report_client = ttk.Combobox(filter_box, state="readonly", width=45)
        self.report_client.grid(row=1, column=2, sticky="ew", padx=(12, 10), pady=(0, 15))
        ttk.Button(filter_box, text="CONSULTAR", style="Accent.TButton", command=self.run_report).grid(row=1, column=3, padx=(0, 15), pady=(0, 15))

        self.report_tree = ttk.Treeview(panel, columns=("client", "products", "total"), show="headings", height=6)
        self.report_tree.heading("client", text="CLIENTE", anchor="center")
        self.report_tree.heading("products", text="PRODUTOS", anchor="center")
        self.report_tree.heading("total", text="VALOR COMPRADO", anchor="center")
        self.report_tree.column("client", width=self.px(700), anchor="center")
        self.report_tree.column("products", width=self.px(180), anchor="center")
        self.report_tree.column("total", width=self.px(260), anchor="center")
        self.report_tree.pack(fill="both", expand=True, padx=22)
        footer = tk.Frame(panel, bg=PANEL)
        footer.pack(fill="x", padx=22, pady=20)
        ttk.Button(footer, text="Gerar relatório A4 (PDF)", command=self.revenue_report_pdf).pack(side="right")
        self.report_total = tk.Label(footer, text="TOTAL BRUTO: R$ 0,00", bg=PANEL, fg=GREEN, font=("Segoe UI", 19, "bold"))
        self.report_total.pack(side="right", padx=24)

    def _build_settings(self):
        page = self._new_page("settings")
        self._module_title(page, "Configurações", "Aparência, atualizações, segurança e recuperação do aplicativo.")

        appearance = self._panel(page)
        appearance.pack(fill="x", pady=(0, self.px(16)))
        appearance_content = tk.Frame(appearance, bg=PANEL, padx=self.px(26), pady=self.px(24))
        appearance_content.pack(fill="x")
        tk.Label(appearance_content, text="APARÊNCIA", bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 13, "bold")).pack(anchor="w")
        tk.Label(
            appearance_content,
            text="Escolha o visual que combina melhor com o ambiente de trabalho. A preferência fica salva neste computador.",
            bg=PANEL,
            fg=MUTED,
            font=(FONT_FAMILY, 9),
        ).pack(anchor="w", pady=(self.px(5), self.px(16)))
        theme_options = tk.Frame(appearance_content, bg=PANEL)
        theme_options.pack(fill="x")
        theme_options.grid_columnconfigure((0, 1), weight=1, uniform="themes")
        self._theme_option(theme_options, "dark", 0)
        self._theme_option(theme_options, "light", 1)

        panel = self._panel(page)
        panel.pack(fill="x")

        content = tk.Frame(panel, bg=PANEL, padx=self.px(26), pady=self.px(24))
        content.pack(fill="x")
        tk.Label(content, text="ATUALIZAÇÕES DO APLICATIVO", bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 13, "bold")).pack(anchor="w")
        tk.Label(
            content,
            text=f"Versão instalada: {__version__}",
            bg=PANEL,
            fg=TEXT,
            font=("Segoe UI Semibold", 10),
        ).pack(anchor="w", pady=(12, 2))
        tk.Label(
            content,
            text=f"Fonte oficial: github.com/{configured_repository()}/releases",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w")
        tk.Label(
            content,
            text="O aplicativo baixa apenas o instalador publicado na Release e exige a validação SHA-256. Nenhuma senha ou token fica salvo no programa.",
            bg=PANEL,
            fg=MUTED,
            wraplength=self.px(900),
            justify="left",
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(10, 14))
        self.settings_update_status = tk.Label(content, text="Pronto para verificar.", bg=SOFT, fg=BLUE, padx=12, pady=9, font=(FONT_FAMILY, 9, "bold"))
        self.settings_update_status.pack(fill="x", pady=(0, 14))

        actions = tk.Frame(content, bg=PANEL)
        actions.pack(fill="x")
        self.settings_check_button = ttk.Button(actions, text="Verificar atualizações", style="Accent.TButton", command=self.check_updates)
        self.settings_check_button.pack(side="left")
        self.rollback_button = ttk.Button(actions, text="Restaurar versão anterior", command=self.restore_previous_version)
        self.rollback_button.pack(side="left", padx=10)
        self._refresh_update_settings()

        recovery = self._panel(page)
        recovery.pack(fill="x", pady=(16, 0))
        tk.Label(recovery, text="PROTEÇÃO DOS DADOS", bg=PANEL, fg=TEXT, font=(FONT_FAMILY, 12, "bold")).pack(anchor="w", padx=26, pady=(21, 6))
        tk.Label(
            recovery,
            text="Clientes, produtos e vendas ficam em uma pasta de dados separada da instalação. Antes de atualizar ou restaurar, o aplicativo também cria um backup do banco local.",
            bg=PANEL,
            fg=MUTED,
            wraplength=self.px(900),
            justify="left",
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=26, pady=(0, 22))

    def _theme_option(self, parent, key, column):
        theme = THEMES[key]
        selected = key == self.theme_key
        shadow = tk.Frame(parent, bg=SHADOW)
        shadow.grid(
            row=0,
            column=column,
            sticky="ew",
            padx=(0, self.px(10)) if column == 0 else (self.px(10), 0),
        )
        card = tk.Button(
            shadow,
            text=f"{'●  ' if selected else '○  '}{theme['name']}\n{theme['description']}",
            justify="left",
            anchor="w",
            bg=SELECTED if selected else SOFT,
            fg=TEXT,
            activebackground=SOFT_HOVER,
            activeforeground=TEXT,
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=BLUE if selected else BORDER,
            font=(FONT_FAMILY, 10, "bold"),
            padx=self.px(18),
            pady=self.px(15),
            cursor="hand2",
            command=lambda value=key: self.change_theme(value),
        )
        card.pack(fill="both", expand=True, padx=(0, self.px(2)), pady=(0, self.px(2)))

    def change_theme(self, key):
        if key == self.theme_key or key not in THEMES:
            return
        if getattr(self, "update_busy", False):
            return messagebox.showinfo("Aparência", "Aguarde a atualização em andamento terminar para trocar o tema.")

        draft = {
            "sale_date": self.sale_date.get() if hasattr(self, "sale_date") else display_date(date.today()),
            "sale_client": self.sale_client.get() if hasattr(self, "sale_client") else "",
            "quantity": self.qty.get() if hasattr(self, "qty") else "1",
            "barcode": self.barcode.get() if hasattr(self, "barcode") else "",
            "start": self.start.get() if hasattr(self, "start") else display_date(date.today().replace(day=1)),
            "end": self.end.get() if hasattr(self, "end") else display_date(date.today()),
            "report_client": self.report_client.get() if hasattr(self, "report_client") else "Todos os clientes",
        }
        current_page = self.current_page
        self.theme_preferences.save(key)
        self.theme_key = key
        _apply_palette(key)
        self.configure(bg=BG)

        self._cancel_barcode_focus()
        self._cancel_scan_animation()
        self.motion.cancel_all()
        for child in self.winfo_children():
            child.destroy()
        self.pages = {}
        self.nav_buttons = {}
        self.icons = {}
        self._style()
        self._create_icons()
        self._build_shell()
        self._build_home()
        self._build_sales()
        self._build_products()
        self._build_clients()
        self._build_reports()
        self._build_settings()
        self.refresh_all()

        self.sale_date.set(draft["sale_date"])
        if draft["sale_client"] in self.client_map:
            self.sale_client.set(draft["sale_client"])
        self.qty.set(draft["quantity"])
        self.barcode.set(draft["barcode"])
        self.start.set(draft["start"])
        self.end.set(draft["end"])
        if draft["report_client"] in self.report_client_map:
            self.report_client.set(draft["report_client"])
        self.refresh_items()
        self.show_page(current_page, animate=True)

    def _show_success(self, message):
        self.motion.show_toast(
            message,
            panel=PANEL,
            text_color=TEXT,
            muted=MUTED,
            border=BORDER,
        )

    def _refresh_update_settings(self):
        if hasattr(self, "rollback_button"):
            self.rollback_button.config(state="normal" if rollback_available() else "disabled")

    def _date_field(self, parent, variable, background=None):
        return DateField(
            parent,
            variable,
            icon=self.icons["calendar"],
            palette={
                "accent": BLUE,
                "accent_hover": BLUE_HOVER,
                "panel": PANEL,
                "text": TEXT,
                "muted": MUTED,
                "soft": SOFT,
                "soft_hover": SOFT_HOVER,
            },
            px=self.px,
            width=11,
            background=background,
        )

    def _field_label(self, parent, text, row, column, padx=(0, 0), bg=None):
        tk.Label(parent, text=text, bg=bg or PANEL, fg=MUTED, font=(FONT_FAMILY, 9, "bold")).grid(row=row, column=column, sticky="w", padx=padx, pady=(0, 5))

    def show_page(self, key, history=False, animate=None):
        titles = {
            "home": ("Início", "Visão geral da operação"),
            "sales": ("Vendas", "Registro e histórico de vendas"),
            "products": ("Produtos", "Cadastro e gestão de produtos"),
            "clients": ("Clientes", "Cadastro e gestão de clientes"),
            "reports": ("Relatórios", "Faturamento bruto da empresa"),
            "settings": ("Configurações", "Atualizações e recuperação"),
        }
        should_animate = key != self.current_page if animate is None else animate
        self._cancel_barcode_focus()
        self.motion.present_page(self.pages[key], animate=should_animate)
        self.current_page = key
        title, subtitle = titles[key]
        self.header_title.config(text=title)
        self.header_subtitle.config(text=subtitle)
        for page_key, button in self.nav_buttons.items():
            button.config(bg=BLUE if page_key == key else NAVY, fg="white" if page_key == key else NAV_TEXT)
        if key == "home":
            self.refresh_dashboard()
        elif key == "sales":
            self.refresh_sales()
            self.sales_inner.select(self.sales_history_tab if history else self.sales_new_tab)
            if not history:
                self._schedule_barcode_focus()
        elif key == "products":
            self.refresh_products()
        elif key == "clients":
            self.refresh_client_table()
        elif key == "reports":
            self.run_report(show_errors=False)
        elif key == "settings":
            self._refresh_update_settings()

    def refresh_all(self):
        self.refresh_clients()
        self.refresh_client_table()
        self.refresh_products()
        self.refresh_sales()
        self.run_report(show_errors=False)
        self.refresh_dashboard()

    def refresh_dashboard(self):
        today = date.today()
        last_day = calendar.monthrange(today.year, today.month)[1]
        stats = self.db.dashboard_stats(today.replace(day=1).isoformat(), today.replace(day=last_day).isoformat())
        self.stat_labels["revenue"].config(text=money(stats["revenue_cents"]))
        self.stat_labels["sales"].config(text=str(stats["sales"]))
        self.stat_labels["products"].config(text=str(stats["products"]))
        self.stat_labels["clients"].config(text=str(stats["clients"]))
        for item in self.recent_tree.get_children():
            self.recent_tree.delete(item)
        for sale in self.db.list_sales()[:7]:
            self.recent_tree.insert("", "end", values=(f"#{sale['id']}", display_date(sale["sale_date"]), sale["client_name"], sale["item_count"], money(sale["total_cents"])))

    def refresh_clients(self):
        rows = self.db.list_clients()
        self.client_map = {row["name"]: row["id"] for row in rows}
        values = list(self.client_map)
        self.sale_client["values"] = values
        if values and self.sale_client.get() not in values:
            self.sale_client.set(values[0])
        self.report_client_map = {"Todos os clientes": None, **self.client_map}
        self.report_client["values"] = list(self.report_client_map)
        if self.report_client.get() not in self.report_client_map:
            self.report_client.set("Todos os clientes")

    def refresh_client_table(self):
        if not hasattr(self, "clients_tree"):
            return
        for item in self.clients_tree.get_children():
            self.clients_tree.delete(item)
        search = self.client_search.get() if hasattr(self, "client_search") else ""
        for client in self.db.list_clients(search):
            created = display_date(str(client["created_at"])[:10])
            self.clients_tree.insert(
                "",
                "end",
                iid=str(client["id"]),
                values=(client["id"], client["name"], client["notes"], created),
            )

    def save_client(self):
        name = self.client_name.get().strip()
        if not name:
            return messagebox.showwarning("Cliente", "Informe o nome do cliente.")
        try:
            if self.editing_client_id is None:
                saved_client_id = self.db.add_client(name, self.client_notes.get())
                message = "Cliente cadastrado com sucesso."
            else:
                saved_client_id = self.editing_client_id
                self.db.update_client(
                    self.editing_client_id, name, self.client_notes.get()
                )
                message = "Cliente atualizado com sucesso."
            self.cancel_client_edit()
            self.refresh_clients()
            self.refresh_client_table()
            self.refresh_dashboard()
            self.motion.highlight_tree_row(
                self.clients_tree,
                saved_client_id,
                background=SOFT,
                text=TEXT,
            )
            self._show_success(message)
        except Exception as exc:
            messagebox.showerror("Clientes", f"Não foi possível salvar: {exc}")

    def begin_client_edit(self):
        row = self._selected(self.clients_tree)
        if not row:
            return messagebox.showwarning("Clientes", "Selecione um cliente.")
        self.editing_client_id = int(row[0])
        self.client_name.set(row[1])
        self.client_notes.set(row[2])
        self.client_save_button.config(text="SALVAR ALTERAÇÕES")
        if not self.client_cancel_button.winfo_manager():
            self.client_cancel_button.pack(side="left", padx=self.px(8))

    def cancel_client_edit(self):
        self.editing_client_id = None
        self.client_name.set("")
        self.client_notes.set("")
        self.client_save_button.config(text="CADASTRAR CLIENTE")
        if self.client_cancel_button.winfo_manager():
            self.client_cancel_button.pack_forget()

    def delete_client(self):
        row = self._selected(self.clients_tree)
        if not row:
            return messagebox.showwarning("Clientes", "Selecione um cliente.")
        if messagebox.askyesno(
            "Excluir cliente",
            f"Excluir {row[1]}? Se houver vendas vinculadas, o cliente será arquivado e o histórico será preservado.",
        ):
            self.db.delete_client(int(row[0]))
            self.cancel_client_edit()
            self.refresh_clients()
            self.refresh_client_table()
            self.refresh_dashboard()

    def add_client(self):
        name = simpledialog.askstring("Novo cliente", "Nome do cliente:", parent=self)
        if name:
            try:
                client_id = self.db.add_client(name)
                self.refresh_clients()
                self.refresh_client_table()
                self.sale_client.set(name)
                self.refresh_dashboard()
                self.motion.highlight_tree_row(
                    self.clients_tree,
                    client_id,
                    background=SOFT,
                    text=TEXT,
                )
                self._show_success(f"Cliente {name} cadastrado com sucesso.")
            except Exception as exc:
                messagebox.showerror("Cliente", f"Não foi possível cadastrar: {exc}")

    def add_product(self):
        try:
            if not self.prod_name.get().strip():
                raise ValueError("Informe o nome do produto.")
            product_id = self.db.add_product(self.prod_name.get(), parse_money(self.prod_price.get()))
            product = next(row for row in self.db.list_products() if row["id"] == product_id)
            self.prod_name.set("")
            self.prod_price.set("")
            self.refresh_products()
            self.refresh_dashboard()
            self.motion.highlight_tree_row(
                self.products,
                product_id,
                background=SOFT,
                text=TEXT,
            )
            self._show_success(
                f"Produto cadastrado • código {product['barcode']}"
            )
        except Exception as exc:
            messagebox.showerror("Produto", str(exc))

    def refresh_products(self):
        for item in self.products.get_children():
            self.products.delete(item)
        search = self.search.get() if hasattr(self, "search") else ""
        for product in self.db.list_products(search):
            self.products.insert(
                "",
                "end",
                iid=str(product["id"]),
                values=(
                    product["id"],
                    product["name"],
                    money(product["price_cents"]),
                    product["barcode"],
                    "⧉",
                    "⎙",
                ),
            )

    def _product_table_click(self, event):
        if self.products.identify_region(event.x, event.y) != "cell":
            return None
        column = self.products.identify_column(event.x)
        if column not in {"#5", "#6"}:
            return None
        item_id = self.products.identify_row(event.y)
        if not item_id:
            return None
        self.products.selection_set(item_id)
        self.products.focus(item_id)
        if column == "#5":
            self.copy_product_barcode(item_id=item_id, notify=False)
        else:
            self.print_product_label(item_id=item_id)
        return "break"

    def _product_table_double_click(self, event):
        if self.products.identify_column(event.x) in {"#5", "#6"}:
            return "break"
        item_id = self.products.identify_row(event.y)
        if item_id:
            self.products.selection_set(item_id)
            self.products.focus(item_id)
            self.edit_product()
        return None

    def _product_table_motion(self, event):
        is_action_icon = (
            self.products.identify_region(event.x, event.y) == "cell"
            and self.products.identify_column(event.x) in {"#5", "#6"}
            and bool(self.products.identify_row(event.y))
        )
        self.products.configure(cursor="hand2" if is_action_icon else "")

    def _selected(self, tree):
        selected = tree.selection()
        return tree.item(selected[0], "values") if selected else None

    def edit_product(self):
        row = self._selected(self.products)
        if not row:
            return messagebox.showwarning("Produto", "Selecione um produto.")
        dialog = ProductEditDialog(self, row[1], row[2].replace("R$ ", ""))
        self.wait_window(dialog)
        if dialog.result is None:
            return
        try:
            name, price_cents = dialog.result
            self.db.update_product(int(row[0]), name, price_cents)
            self.refresh_products()
            self.motion.highlight_tree_row(
                self.products,
                row[0],
                background=SOFT,
                text=TEXT,
            )
            self._show_success("Nome e preço do produto atualizados.")
        except Exception as exc:
            messagebox.showerror("Produto", str(exc))

    def copy_product_barcode(self, item_id=None, notify=True):
        if item_id and self.products.exists(str(item_id)):
            row = self.products.item(str(item_id), "values")
        else:
            row = self._selected(self.products)
        if not row:
            return messagebox.showwarning("Produto", "Selecione o produto cujo código deseja copiar.")
        code = str(row[3])
        self.clipboard_clear()
        self.clipboard_append(code)
        self.update_idletasks()
        if hasattr(self, "product_action_status"):
            self.product_action_status.config(text=f"Código {code} copiado")
        if notify:
            messagebox.showinfo("Código copiado", f"O código {code} foi copiado para a área de transferência.")

    def print_product_label(self, item_id=None):
        if item_id and self.products.exists(str(item_id)):
            row = self.products.item(str(item_id), "values")
        else:
            row = self._selected(self.products)
        if not row:
            return messagebox.showwarning("Etiqueta", "Selecione o produto cuja etiqueta deseja imprimir.")
        try:
            label_folder = self.db.path.parent / "etiquetas"
            label_path = label_folder / f"etiqueta_produto_{row[0]}_{row[3]}.pdf"
            product_label_pdf(label_path, {"name": row[1], "barcode": row[3]})
            if hasattr(self, "product_action_status"):
                self.product_action_status.config(text=f"Etiqueta de {row[1]} gerada")
            self.open_pdf_for_printing(
                label_path,
                document_title="Etiqueta térmica 40 x 25 mm",
                print_hint=(
                    "No navegador, pressione Ctrl+P. Selecione o papel 40 x 25 mm, "
                    "escala 100% (tamanho real) e margens desativadas."
                ),
            )
        except Exception as exc:
            messagebox.showerror("Etiqueta", str(exc))

    def delete_product(self):
        row = self._selected(self.products)
        if row and messagebox.askyesno("Excluir produto", f"Excluir {row[1]}? Produtos já vendidos serão apenas arquivados."):
            self.db.delete_product(int(row[0]))
            self.refresh_products()
            self.refresh_dashboard()

    def scan(self):
        try:
            product = self.db.product_by_barcode(self.barcode.get())
            quantity = int(self.qty.get())
            if not product:
                raise ValueError("Código não encontrado.")
            if quantity < 1:
                raise ValueError("A quantidade deve ser maior que zero.")
            existing = next((item for item in self.current_items if item["product_id"] == product["id"] and item["unit_price_cents"] == product["price_cents"]), None)
            if existing:
                existing["quantity"] += quantity
                item_index = self.current_items.index(existing)
            else:
                self.current_items.append({"product_id": product["id"], "product_name": product["name"], "quantity": quantity, "unit_price_cents": product["price_cents"]})
                item_index = len(self.current_items) - 1
            self.qty.set("1")
            self.barcode.set("")
            self.refresh_items()
            self._animate_scan_success(item_index, product["name"], quantity)
            self.barcode_entry.focus_set()
        except Exception as exc:
            messagebox.showerror("Bipagem", str(exc))
            self.barcode_entry.focus_set()

    def refresh_items(self):
        for item in self.items.get_children():
            self.items.delete(item)
        for index, item in enumerate(self.current_items):
            self.items.insert("", "end", iid=str(index), values=(item["product_name"], item["quantity"], money(item["unit_price_cents"]), money(item["quantity"] * item["unit_price_cents"])))
        total = sum(item["quantity"] * item["unit_price_cents"] for item in self.current_items)
        self.sale_total.config(text=f"TOTAL: {money(total)}")

    def remove_item(self):
        selected = self.items.selection()
        if selected:
            self._cancel_scan_animation()
            self.current_items.pop(int(selected[0]))
            self.refresh_items()
            self.scan_feedback.config(
                text="Item removido; pronto para bipar",
                fg=MUTED,
                font=(FONT_FAMILY, 9),
            )

    def clear_sale(self):
        self._cancel_scan_animation()
        self.current_items = []
        self.editing_sale_id = None
        self.sale_date_field.entry.set_date(date.today())
        self.refresh_items()
        self.scan_feedback.config(
            text="Pronto para bipar",
            fg=MUTED,
            font=(FONT_FAMILY, 9),
        )

    def finish_sale(self):
        try:
            client_id = self.client_map.get(self.sale_client.get())
            if client_id is None:
                raise ValueError("Selecione ou cadastre um cliente.")
            sale_date = iso_date(self.sale_date.get())
            sale_id = self.db.save_sale(client_id, sale_date, self.current_items, self.editing_sale_id)
            self.clear_sale()
            self.refresh_sales()
            self.run_report(show_errors=False)
            self.refresh_dashboard()
            self.motion.highlight_tree_row(
                self.sales_tree,
                sale_id,
                background=SOFT,
                text=TEXT,
            )
            self._show_success(f"Venda nº {sale_id} salva com sucesso.")
        except Exception as exc:
            messagebox.showerror("Venda", str(exc))

    def refresh_sales(self):
        for item in self.sales_tree.get_children():
            self.sales_tree.delete(item)
        for sale in self.db.list_sales():
            self.sales_tree.insert(
                "",
                "end",
                iid=str(sale["id"]),
                values=(
                    f"#{sale['id']}",
                    display_date(sale["sale_date"]),
                    sale["client_name"],
                    sale["item_count"],
                    money(sale["total_cents"]),
                ),
            )

    def edit_sale(self):
        row = self._selected(self.sales_tree)
        if not row:
            return messagebox.showwarning("Venda", "Selecione uma venda.")
        sale_id = int(str(row[0]).replace("#", ""))
        sale, items = self.db.get_sale(sale_id)
        self.editing_sale_id = sale["id"]
        self.sale_date_field.entry.set_date(sale["sale_date"])
        client_name = next(
            (
                name
                for name, client_id in self.client_map.items()
                if client_id == sale["client_id"]
            ),
            "",
        )
        if not client_name:
            archived_client = self.db.client_by_id(sale["client_id"])
            if archived_client:
                client_name = archived_client["name"]
                self.client_map[client_name] = archived_client["id"]
                self.sale_client["values"] = list(self.client_map)
        self.sale_client.set(client_name)
        self.current_items = [
            {
                "product_id": item["product_id"],
                "product_name": item["product_name"],
                "quantity": item["quantity"],
                "unit_price_cents": item["unit_price_cents"],
            }
            for item in items
        ]
        self.refresh_items()
        self.show_page("sales")
        messagebox.showinfo("Editar venda", "A venda foi carregada. Altere os dados e finalize para salvar.")

    def delete_sale(self):
        row = self._selected(self.sales_tree)
        if row:
            sale_id = int(str(row[0]).replace("#", ""))
            if messagebox.askyesno("Excluir venda", f"Excluir definitivamente a venda nº {sale_id}?"):
                self.db.delete_sale(sale_id)
                self.refresh_sales()
                self.run_report(show_errors=False)
                self.refresh_dashboard()

    def run_report(self, show_errors=True):
        try:
            client_id = self.report_client_map.get(self.report_client.get())
            start = iso_date(self.start.get())
            end = iso_date(self.end.get())
            self.report_rows = self.db.revenue_report(start, end, client_id)
            for item in self.report_tree.get_children():
                self.report_tree.delete(item)
            for row in self.report_rows:
                self.report_tree.insert(
                    "",
                    "end",
                    values=(
                        row["client_name"],
                        row["product_count"],
                        money(row["total_cents"]),
                    ),
                )
            total = sum(row["total_cents"] for row in self.report_rows)
            self.report_total.config(text=f"TOTAL BRUTO: {money(total)}")
            return True
        except Exception as exc:
            if show_errors:
                messagebox.showerror("Relatório", str(exc))
            return False

    def product_report(self):
        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")], initialfile="lista_de_produtos.pdf")
        if path:
            try:
                product_pdf(path, self.db.list_products())
                self.open_pdf_for_printing(path)
            except Exception as exc:
                messagebox.showerror("Relatório de produtos", str(exc))

    def revenue_report_pdf(self):
        if not self.run_report():
            return
        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")], initialfile="faturamento_bruto.pdf")
        if path:
            try:
                revenue_pdf(
                    path,
                    self.report_rows,
                    iso_date(self.start.get()),
                    iso_date(self.end.get()),
                )
                self.open_pdf_for_printing(path)
            except Exception as exc:
                messagebox.showerror("Relatório de faturamento", str(exc))

    def open_pdf_for_printing(
        self,
        path,
        document_title="Relatório A4",
        print_hint="No navegador, pressione Ctrl+P para imprimir.",
    ):
        pdf_path = Path(path).resolve()
        try:
            opened = webbrowser.open(pdf_path.as_uri(), new=2)
            if not opened and os.name == "nt":
                os.startfile(pdf_path)  # type: ignore[attr-defined]
            messagebox.showinfo(
                f"{document_title} pronto",
                f"O PDF foi salvo e aberto para impressão:\n{pdf_path}\n\n{print_hint}",
            )
        except Exception as exc:
            messagebox.showwarning(
                f"{document_title} salvo",
                f"O PDF foi salvo em:\n{pdf_path}\n\nNão foi possível abrir o navegador automaticamente: {exc}",
            )

    def check_updates(self, silent=False):
        if getattr(self, "update_busy", False):
            if not silent:
                messagebox.showinfo("Atualização", "A verificação já está em andamento.")
            return
        self.update_busy = True
        self.update_button.config(text="Verificando...", state="disabled")
        if hasattr(self, "settings_check_button"):
            self.settings_check_button.config(state="disabled")
            self.settings_update_status.config(text="Consultando a publicação oficial no GitHub...", fg=BLUE)

        def worker():
            try:
                info = check_for_update(__version__)
                self.after(0, lambda: self._update_check_finished(info, silent))
            except UpdateError as exc:
                self.after(0, lambda error=str(exc): self._update_check_failed(error, silent))
            except Exception:
                self.after(0, lambda: self._update_check_failed("Falha inesperada ao buscar atualização.", silent))

        threading.Thread(target=worker, daemon=True).start()

    def _reset_update_button(self):
        self.update_busy = False
        self.update_button.config(text="Buscar atualização", state="normal")
        if hasattr(self, "settings_check_button"):
            self.settings_check_button.config(state="normal")

    def _update_check_failed(self, error, silent):
        self._reset_update_button()
        dialog = getattr(self, "download_dialog", None)
        if dialog and dialog.winfo_exists():
            dialog.destroy()
        self.download_dialog = None
        if hasattr(self, "settings_update_status"):
            self.settings_update_status.config(text=error, fg=RED)
        if not silent:
            messagebox.showerror("Atualização", error)

    def _update_check_finished(self, info, silent):
        self._reset_update_button()
        if info is None:
            if hasattr(self, "settings_update_status"):
                self.settings_update_status.config(text=f"Versão {__version__}: aplicativo atualizado.", fg=GREEN)
            if not silent:
                messagebox.showinfo("Atualização", f"Você já está usando a versão mais recente ({__version__}).")
            return
        if hasattr(self, "settings_update_status"):
            self.settings_update_status.config(text=f"Nova versão disponível: {info.version}", fg=GREEN)
        UpdateOfferDialog(self, info, self._download_update)

    def _download_update(self, info):
        self.update_busy = True
        self.update_button.config(text="Baixando 0%", state="disabled")
        if hasattr(self, "settings_check_button"):
            self.settings_check_button.config(state="disabled")
        self.download_dialog = DownloadDialog(self)

        def progress(downloaded, total):
            def update_ui():
                if self.download_dialog and self.download_dialog.winfo_exists():
                    self.download_dialog.set_progress(downloaded, total)
                if total:
                    percent = min(100, int(downloaded * 100 / total))
                    self.update_button.config(text=f"Baixando {percent}%")

            self.after(0, update_ui)

        def worker():
            try:
                installer = download_update(info, progress)
                self.after(0, lambda: self._install_update(installer, info.version))
            except UpdateError as exc:
                self.after(0, lambda error=str(exc): self._update_check_failed(error, False))
            except Exception:
                self.after(0, lambda: self._update_check_failed("Não foi possível concluir o download.", False))

        threading.Thread(target=worker, daemon=True).start()

    def _install_update(self, installer, version):
        dialog = getattr(self, "download_dialog", None)
        if dialog and dialog.winfo_exists():
            dialog.destroy()
        self.download_dialog = None
        self._reset_update_button()
        if hasattr(self, "settings_update_status"):
            self.settings_update_status.config(text="Download concluído e SHA-256 validado.", fg=GREEN)
        if not messagebox.askyesno(
            "Autorizar instalação",
            f"A versão {version} foi baixada e passou na verificação SHA-256.\n\nDeseja fechar o aplicativo e instalar agora?",
        ):
            messagebox.showinfo("Atualização", "A instalação não foi iniciada. Você poderá verificar novamente quando desejar.")
            return
        try:
            backup = self.db.backup(self.db.path.parent / "backups")
            messagebox.showinfo(
                "Pronto para instalar",
                f"Um backup foi criado em:\n{backup}\n\nAo clicar em OK, o aplicativo fechará e a versão {version} será instalada.",
            )
            launch_installer(installer)
            self.destroy()
        except Exception as exc:
            self._update_check_failed(f"Não foi possível iniciar o instalador: {exc}", False)

    def restore_previous_version(self):
        if not rollback_available():
            return messagebox.showinfo("Recuperação", "Não há uma versão anterior disponível neste computador.")
        if not messagebox.askyesno(
            "Restaurar versão anterior",
            "Deseja restaurar a cópia anterior do aplicativo? Clientes, produtos e vendas serão preservados.",
        ):
            return
        try:
            backup = self.db.backup(self.db.path.parent / "backups")
            messagebox.showinfo("Pronto para restaurar", f"Backup dos dados criado em:\n{backup}\n\nAo clicar em OK, o aplicativo fechará e a versão anterior será restaurada.")
            launch_rollback()
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Recuperação", str(exc))

    def backup(self):
        folder = filedialog.askdirectory(title="Escolha a pasta do backup")
        if folder:
            try:
                target = self.db.backup(folder)
                messagebox.showinfo("Backup", f"Backup criado em:\n{target}")
            except Exception as exc:
                messagebox.showerror("Backup", f"Não foi possível criar o backup: {exc}")


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
