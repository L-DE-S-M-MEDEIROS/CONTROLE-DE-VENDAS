from __future__ import annotations

import calendar
import ctypes
import os
import threading
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageDraw, ImageTk

from . import __version__
from .database import Database
from .reports import money, product_pdf, revenue_pdf
from .updater import (
    UpdateError,
    check_for_update,
    configured_repository,
    download_update,
    launch_installer,
    launch_rollback,
    rollback_available,
)


NAVY = "#10243E"
NAVY_LIGHT = "#193653"
BLUE = "#1769AA"
BLUE_HOVER = "#2080C8"
CYAN = "#26A7D8"
GREEN = "#169B62"
RED = "#C84646"
BG = "#EDF2F7"
PANEL = "#FFFFFF"
TEXT = "#1D2A38"
MUTED = "#68798A"
BORDER = "#D7E0E9"


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
    cleaned = text.strip().replace("R$", "").replace(" ", "")
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    return int(round(float(cleaned) * 100))


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
        tk.Label(header, text=info.title, bg=NAVY, fg="#9CC8E8", font=("Segoe UI", 9)).pack(anchor="w", padx=27)

        body = tk.Frame(self, bg=PANEL, padx=26, pady=22)
        body.pack(fill="both", expand=True, padx=18, pady=18)
        versions = tk.Frame(body, bg="#F1F6FA", padx=16, pady=12)
        versions.pack(fill="x")
        tk.Label(versions, text=f"Versão instalada: {__version__}", bg="#F1F6FA", fg=MUTED, font=("Segoe UI Semibold", 10)).pack(side="left")
        tk.Label(versions, text=f"Nova versão: {info.version}", bg="#F1F6FA", fg=GREEN, font=("Segoe UI", 11, "bold")).pack(side="right")
        tk.Label(body, text="Descrição da atualização", bg=PANEL, fg=NAVY, font=("Segoe UI Semibold", 10)).pack(anchor="w", pady=(16, 6))
        notes = tk.Text(body, height=9, wrap="word", bg="#F8FAFC", fg=TEXT, relief="flat", padx=12, pady=10, font=("Segoe UI", 9))
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
        tk.Label(self, text="Baixando o instalador oficial", bg=PANEL, fg=NAVY, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=26, pady=(25, 4))
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


class App(tk.Tk):
    def __init__(self, db_path=None, maximize=True, dpi_scale_override=None):
        _enable_per_monitor_dpi()
        super().__init__()
        detected_dpi = float(dpi_scale_override * 96 if dpi_scale_override else self.winfo_fpixels("1i"))
        self.dpi_scale = max(1.0, min(3.0, detected_dpi / 96.0))
        self.tk.call("tk", "scaling", detected_dpi / 72.0)
        self.title("Vendas PRO - Controle de Vendas")
        self.configure(bg=BG)
        self.geometry(f"{self.px(1600)}x{self.px(900)}")
        self.minsize(self.px(1080), self.px(680))
        base = Path(os.getenv("LOCALAPPDATA", Path.home())) / "ControleDeVendas"
        self.db = Database(db_path or base / "controle_vendas.db")
        self.current_items = []
        self.editing_sale_id = None
        self.editing_client_id = None
        self.client_map = {}
        self.report_client_map = {"Todos os clientes": None}
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
        self.show_page("home")
        if maximize:
            self.after(80, self._maximize_window)
        self.after(3000, lambda: self.check_updates(silent=True))

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
        style.configure("TButton", font=("Segoe UI", 10), padding=(self.px(14), self.px(9)), background="#E5ECF3", foreground=TEXT, borderwidth=0)
        style.map("TButton", background=[("active", "#D8E3ED")])
        style.configure("Accent.TButton", background=BLUE, foreground="white", font=("Segoe UI", 10, "bold"), padding=(self.px(18), self.px(10)))
        style.map("Accent.TButton", background=[("active", BLUE_HOVER), ("pressed", "#12598F")])
        style.configure("Success.TButton", background=GREEN, foreground="white", font=("Segoe UI", 10, "bold"), padding=(self.px(18), self.px(10)))
        style.map("Success.TButton", background=[("active", "#117D4F")])
        style.configure("Danger.TButton", background="#FBE8E8", foreground=RED, padding=(self.px(14), self.px(9)))
        style.map("Danger.TButton", background=[("active", "#F5D4D4")])
        style.configure("TEntry", padding=self.px(9), fieldbackground="white", bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER)
        style.configure("TCombobox", padding=self.px(8), fieldbackground="white", bordercolor=BORDER, arrowcolor=BLUE)
        style.configure("TSpinbox", padding=self.px(8), fieldbackground="white", bordercolor=BORDER, arrowcolor=BLUE)
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=self.px(38), background="white", fieldbackground="white", foreground=TEXT, bordercolor=BORDER, borderwidth=0)
        style.map("Treeview", background=[("selected", "#D9ECFB")], foreground=[("selected", TEXT)])
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 10), background="#E8EFF6", foreground=NAVY, padding=(self.px(10), self.px(10)), borderwidth=0)
        style.map("Treeview.Heading", background=[("active", "#DDE8F2")])
        style.configure("Inner.TNotebook", background=PANEL, borderwidth=0, tabmargins=(0, 0, 0, self.px(8)))
        style.configure("Inner.TNotebook.Tab", font=("Segoe UI Semibold", 10), padding=(self.px(22), self.px(12)), background="#E8EFF6", foreground=MUTED, borderwidth=0)
        style.map("Inner.TNotebook.Tab", background=[("selected", BLUE)], foreground=[("selected", "white")])
        style.configure("Panel.TLabelframe", background=PANEL, bordercolor=BORDER, borderwidth=1, relief="solid")
        style.configure("Panel.TLabelframe.Label", background=PANEL, foreground=NAVY, font=("Segoe UI Semibold", 10))

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
        image = image.resize((display_size, display_size), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(image)

    def _create_icons(self):
        for kind in ("home", "sales", "products", "clients", "reports", "settings", "backup", "update"):
            self.icons[f"nav_{kind}"] = self._icon_image(kind, 24, "white")
            self.icons[f"card_{kind}"] = self._icon_image(kind, 50, BLUE)
        app_icon = self._icon_image("reports", 64, BLUE)
        self.icons["app"] = app_icon
        self.iconphoto(True, app_icon)

    def _build_shell(self):
        sidebar = tk.Frame(self, bg=NAVY, width=self.px(255))
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        brand = tk.Frame(sidebar, bg=NAVY, height=self.px(105))
        brand.pack(fill="x")
        brand.pack_propagate(False)
        tk.Label(brand, text="VENDAS", bg=NAVY, fg="white", font=("Segoe UI", 22, "bold")).pack(anchor="w", padx=24, pady=(23, 0))
        tk.Label(brand, text="PRO  •  GESTÃO LOCAL", bg=NAVY, fg="#85BCE3", font=("Segoe UI Semibold", 8)).pack(anchor="w", padx=26)
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
                fg="#DCE8F3",
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
        tk.Label(sidebar, text=f"BANCO LOCAL • VERSÃO {__version__}", bg=NAVY, fg="#6F8DA7", font=("Segoe UI", 8)).pack(pady=(0, self.px(12)))

        main = tk.Frame(self, bg=BG)
        main.pack(side="left", fill="both", expand=True)
        header = tk.Frame(main, bg=PANEL, height=self.px(82), highlightthickness=1, highlightbackground=BORDER)
        header.pack(fill="x")
        header.pack_propagate(False)
        title_box = tk.Frame(header, bg=PANEL)
        title_box.pack(side="left", fill="y", padx=30)
        self.header_title = tk.Label(title_box, text="Início", bg=PANEL, fg=NAVY, font=("Segoe UI", 19, "bold"))
        self.header_title.pack(anchor="w", pady=(14, 0))
        self.header_subtitle = tk.Label(title_box, text="Visão geral da operação", bg=PANEL, fg=MUTED, font=("Segoe UI", 9))
        self.header_subtitle.pack(anchor="w")
        today_box = tk.Frame(header, bg=PANEL)
        today_box.pack(side="right", fill="y", padx=30)
        tk.Label(today_box, text="HOJE", bg=PANEL, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(anchor="e", pady=(18, 1))
        tk.Label(today_box, text=datetime.now().strftime("%d/%m/%Y"), bg=PANEL, fg=NAVY, font=("Segoe UI Semibold", 11)).pack(anchor="e")

        self.content = tk.Frame(main, bg=BG)
        self.content.pack(fill="both", expand=True, padx=self.px(26), pady=self.px(22))
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

    def _new_page(self, key):
        page = tk.Frame(self.content, bg=BG)
        page.grid(row=0, column=0, sticky="nsew")
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
        tk.Label(hero, text="Cadastre, bipe e acompanhe o faturamento da empresa em um só lugar.", bg=BLUE, fg="#D9EEFC", font=("Segoe UI", 10)).pack(anchor="w", padx=30)

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
            tk.Label(text_box, text=title, bg=PANEL, fg=NAVY, font=("Segoe UI Semibold", 12)).pack(anchor="w")
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
            ("clients", "CLIENTES", "#7A62C7"),
        ]
        for column, (key, label, accent) in enumerate(stat_specs):
            card = tk.Frame(stats, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
            card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 7, 0 if column == 3 else 7))
            tk.Frame(card, bg=accent, width=self.px(5)).pack(side="left", fill="y")
            box = tk.Frame(card, bg=PANEL)
            box.pack(fill="both", expand=True, padx=17, pady=15)
            tk.Label(box, text=label, bg=PANEL, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(anchor="w")
            value = tk.Label(box, text="0", bg=PANEL, fg=NAVY, font=("Segoe UI", 18, "bold"))
            value.pack(anchor="w", pady=(3, 0))
            self.stat_labels[key] = value

        recent = self._panel(page, row=3, column=0, columnspan=3, sticky="nsew")
        recent.grid_rowconfigure(1, weight=1)
        recent.grid_columnconfigure(0, weight=1)
        recent_header = tk.Frame(recent, bg=PANEL)
        recent_header.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))
        tk.Label(recent_header, text="Vendas recentes", bg=PANEL, fg=NAVY, font=("Segoe UI Semibold", 12)).pack(side="left")
        tk.Button(recent_header, text="Ver histórico  ›", bg=PANEL, fg=BLUE, activebackground=PANEL, activeforeground=BLUE_HOVER, relief="flat", borderwidth=0, font=("Segoe UI Semibold", 9), cursor="hand2", command=lambda: self.show_page("sales", history=True)).pack(side="right")
        self.recent_tree = ttk.Treeview(recent, columns=("id", "date", "client", "items", "total"), show="headings", height=6)
        for column, title, width, anchor in [
            ("id", "VENDA", self.px(90), "w"), ("date", "DATA", self.px(130), "w"), ("client", "CLIENTE", self.px(520), "w"), ("items", "ITENS", self.px(100), "center"), ("total", "VALOR", self.px(170), "e")
        ]:
            self.recent_tree.heading(column, text=title)
            self.recent_tree.column(column, width=width, anchor=anchor)
        self.recent_tree.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 18))

    def _module_title(self, parent, title, description):
        header = tk.Frame(parent, bg=BG)
        header.pack(fill="x", pady=(0, 14))
        tk.Label(header, text=title, bg=BG, fg=NAVY, font=("Segoe UI", 17, "bold")).pack(anchor="w")
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
        self.sale_date = tk.StringVar(value=date.today().isoformat())
        ttk.Entry(form, textvariable=self.sale_date, width=16).grid(row=1, column=0, sticky="w")
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
        ttk.Button(scan, text="ADICIONAR ITEM", style="Accent.TButton", command=self.scan).pack(side="left")

        table_box = tk.Frame(new, bg=PANEL)
        table_box.pack(fill="both", expand=True)
        self.items = ttk.Treeview(table_box, columns=("product", "qty", "unit", "subtotal"), show="headings", height=5)
        for column, title, width, anchor in [
            ("product", "PRODUTO", self.px(620), "w"), ("qty", "QUANTIDADE", self.px(140), "center"), ("unit", "VALOR UNITÁRIO", self.px(180), "e"), ("subtotal", "SUBTOTAL", self.px(190), "e")
        ]:
            self.items.heading(column, text=title)
            self.items.column(column, width=width, anchor=anchor)
        self.items.pack(fill="both", expand=True)

        actions = tk.Frame(new, bg=PANEL)
        actions.pack(fill="x", pady=(14, 0))
        ttk.Button(actions, text="Remover item", style="Danger.TButton", command=self.remove_item).pack(side="left")
        ttk.Button(actions, text="Limpar venda", command=self.clear_sale).pack(side="left", padx=8)
        ttk.Button(actions, text="FINALIZAR VENDA", style="Success.TButton", command=self.finish_sale).pack(side="right")
        self.sale_total = tk.Label(actions, text="TOTAL: R$ 0,00", bg=PANEL, fg=NAVY, font=("Segoe UI", 18, "bold"))
        self.sale_total.pack(side="right", padx=24)

        history_header = tk.Frame(history, bg=PANEL)
        history_header.pack(fill="x", pady=(0, 12))
        tk.Label(history_header, text="Vendas registradas", bg=PANEL, fg=NAVY, font=("Segoe UI Semibold", 13)).pack(side="left")
        ttk.Button(history_header, text="Atualizar lista", command=self.refresh_sales).pack(side="right")
        self.sales_tree = ttk.Treeview(history, columns=("id", "date", "client", "items", "total"), show="headings", height=6)
        for column, title, width, anchor in [
            ("id", "VENDA", self.px(100), "w"), ("date", "DATA", self.px(140), "w"), ("client", "CLIENTE", self.px(600), "w"), ("items", "ITENS", self.px(120), "center"), ("total", "VALOR", self.px(190), "e")
        ]:
            self.sales_tree.heading(column, text=title)
            self.sales_tree.column(column, width=width, anchor=anchor)
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

        self.products = ttk.Treeview(panel, columns=("id", "name", "price", "barcode"), show="headings", height=6)
        for column, title, width, anchor in [
            ("id", "ID", self.px(80), "w"), ("name", "PRODUTO", self.px(650), "w"), ("price", "PREÇO", self.px(180), "e"), ("barcode", "CÓDIGO DE BARRAS", self.px(260), "w")
        ]:
            self.products.heading(column, text=title)
            self.products.column(column, width=width, anchor=anchor)
        self.products.pack(fill="both", expand=True, padx=22, pady=(0, 10))
        actions = tk.Frame(panel, bg=PANEL)
        actions.pack(fill="x", padx=22, pady=(0, 20))
        ttk.Button(actions, text="Editar produto", style="Accent.TButton", command=self.edit_product).pack(side="left")
        ttk.Button(actions, text="Excluir produto", style="Danger.TButton", command=self.delete_product).pack(side="left", padx=8)

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
        for column, title, width, anchor in [
            ("id", "ID", self.px(80), "w"),
            ("name", "CLIENTE / USUÁRIO", self.px(520), "w"),
            ("notes", "OBSERVAÇÃO", self.px(560), "w"),
            ("created", "CADASTRADO EM", self.px(190), "w"),
        ]:
            self.clients_tree.heading(column, text=title)
            self.clients_tree.column(column, width=width, anchor=anchor)
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

        filter_box = tk.Frame(panel, bg="#F7FAFC", highlightthickness=1, highlightbackground=BORDER)
        filter_box.pack(fill="x", padx=22, pady=20)
        filter_box.grid_columnconfigure(2, weight=1)
        self.start = tk.StringVar(value=date.today().replace(day=1).isoformat())
        self.end = tk.StringVar(value=date.today().isoformat())
        self._field_label(filter_box, "Data inicial", 0, 0, bg="#F7FAFC")
        self._field_label(filter_box, "Data final", 0, 1, padx=(12, 0), bg="#F7FAFC")
        self._field_label(filter_box, "Cliente", 0, 2, padx=(12, 0), bg="#F7FAFC")
        ttk.Entry(filter_box, textvariable=self.start, width=18).grid(row=1, column=0, sticky="w", pady=(0, 15), padx=(15, 0))
        ttk.Entry(filter_box, textvariable=self.end, width=18).grid(row=1, column=1, sticky="w", padx=(12, 0), pady=(0, 15))
        self.report_client = ttk.Combobox(filter_box, state="readonly", width=45)
        self.report_client.grid(row=1, column=2, sticky="ew", padx=(12, 10), pady=(0, 15))
        ttk.Button(filter_box, text="CONSULTAR", style="Accent.TButton", command=self.run_report).grid(row=1, column=3, padx=(0, 15), pady=(0, 15))

        self.report_tree = ttk.Treeview(panel, columns=("client", "total"), show="headings", height=6)
        self.report_tree.heading("client", text="CLIENTE")
        self.report_tree.heading("total", text="VALOR COMPRADO")
        self.report_tree.column("client", width=self.px(850))
        self.report_tree.column("total", width=self.px(260), anchor="e")
        self.report_tree.pack(fill="both", expand=True, padx=22)
        footer = tk.Frame(panel, bg=PANEL)
        footer.pack(fill="x", padx=22, pady=20)
        ttk.Button(footer, text="Gerar relatório A4 (PDF)", command=self.revenue_report_pdf).pack(side="right")
        self.report_total = tk.Label(footer, text="TOTAL BRUTO: R$ 0,00", bg=PANEL, fg=GREEN, font=("Segoe UI", 19, "bold"))
        self.report_total.pack(side="right", padx=24)

    def _build_settings(self):
        page = self._new_page("settings")
        self._module_title(page, "Configurações", "Atualizações, segurança e recuperação do aplicativo.")
        panel = self._panel(page)
        panel.pack(fill="x")

        content = tk.Frame(panel, bg=PANEL, padx=self.px(26), pady=self.px(24))
        content.pack(fill="x")
        tk.Label(content, text="ATUALIZAÇÕES DO APLICATIVO", bg=PANEL, fg=NAVY, font=("Segoe UI", 13, "bold")).pack(anchor="w")
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
        self.settings_update_status = tk.Label(content, text="Pronto para verificar.", bg="#F1F6FA", fg=BLUE, padx=12, pady=9, font=("Segoe UI Semibold", 9))
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
        tk.Label(recovery, text="PROTEÇÃO DOS DADOS", bg=PANEL, fg=NAVY, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=26, pady=(21, 6))
        tk.Label(
            recovery,
            text="Clientes, produtos e vendas ficam em uma pasta de dados separada da instalação. Antes de atualizar ou restaurar, o aplicativo também cria um backup do banco local.",
            bg=PANEL,
            fg=MUTED,
            wraplength=self.px(900),
            justify="left",
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=26, pady=(0, 22))

    def _refresh_update_settings(self):
        if hasattr(self, "rollback_button"):
            self.rollback_button.config(state="normal" if rollback_available() else "disabled")

    def _field_label(self, parent, text, row, column, padx=(0, 0), bg=PANEL):
        tk.Label(parent, text=text, bg=bg, fg=MUTED, font=("Segoe UI Semibold", 9)).grid(row=row, column=column, sticky="w", padx=padx, pady=(0, 5))

    def show_page(self, key, history=False):
        titles = {
            "home": ("Início", "Visão geral da operação"),
            "sales": ("Vendas", "Registro e histórico de vendas"),
            "products": ("Produtos", "Cadastro e gestão de produtos"),
            "clients": ("Clientes", "Cadastro e gestão de clientes"),
            "reports": ("Relatórios", "Faturamento bruto da empresa"),
            "settings": ("Configurações", "Atualizações e recuperação"),
        }
        self.pages[key].tkraise()
        title, subtitle = titles[key]
        self.header_title.config(text=title)
        self.header_subtitle.config(text=subtitle)
        for page_key, button in self.nav_buttons.items():
            button.config(bg=BLUE if page_key == key else NAVY, fg="white" if page_key == key else "#DCE8F3")
        if key == "home":
            self.refresh_dashboard()
        elif key == "sales":
            self.refresh_sales()
            self.sales_inner.select(self.sales_history_tab if history else self.sales_new_tab)
            if not history:
                self.after(100, self.barcode_entry.focus_set)
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
            self.recent_tree.insert("", "end", values=(f"#{sale['id']}", sale["sale_date"], sale["client_name"], sale["item_count"], money(sale["total_cents"])))

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
            created = str(client["created_at"])[:10]
            self.clients_tree.insert("", "end", values=(client["id"], client["name"], client["notes"], created))

    def save_client(self):
        name = self.client_name.get().strip()
        if not name:
            return messagebox.showwarning("Cliente", "Informe o nome do cliente.")
        try:
            if self.editing_client_id is None:
                self.db.add_client(name, self.client_notes.get())
                message = "Cliente cadastrado com sucesso."
            else:
                self.db.update_client(self.editing_client_id, name, self.client_notes.get())
                message = "Cliente atualizado com sucesso."
            self.cancel_client_edit()
            self.refresh_clients()
            self.refresh_client_table()
            self.refresh_dashboard()
            messagebox.showinfo("Clientes", message)
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
                self.db.add_client(name)
                self.refresh_clients()
                self.refresh_client_table()
                self.sale_client.set(name)
                self.refresh_dashboard()
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
            messagebox.showinfo("Produto cadastrado", f"Código gerado automaticamente:\n{product['barcode']}")
        except Exception as exc:
            messagebox.showerror("Produto", str(exc))

    def refresh_products(self):
        for item in self.products.get_children():
            self.products.delete(item)
        search = self.search.get() if hasattr(self, "search") else ""
        for product in self.db.list_products(search):
            self.products.insert("", "end", values=(product["id"], product["name"], money(product["price_cents"]), product["barcode"]))

    def _selected(self, tree):
        selected = tree.selection()
        return tree.item(selected[0], "values") if selected else None

    def edit_product(self):
        row = self._selected(self.products)
        if not row:
            return messagebox.showwarning("Produto", "Selecione um produto.")
        name = simpledialog.askstring("Editar produto", "Nome:", initialvalue=row[1], parent=self)
        if name is None:
            return
        price = simpledialog.askstring("Editar produto", "Preço (R$):", initialvalue=row[2].replace("R$ ", ""), parent=self)
        if price is not None:
            try:
                self.db.update_product(int(row[0]), name, parse_money(price))
                self.refresh_products()
            except Exception as exc:
                messagebox.showerror("Produto", str(exc))

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
            else:
                self.current_items.append({"product_id": product["id"], "product_name": product["name"], "quantity": quantity, "unit_price_cents": product["price_cents"]})
            self.qty.set("1")
            self.barcode.set("")
            self.refresh_items()
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
            self.current_items.pop(int(selected[0]))
            self.refresh_items()

    def clear_sale(self):
        self.current_items = []
        self.editing_sale_id = None
        self.sale_date.set(date.today().isoformat())
        self.refresh_items()

    def finish_sale(self):
        try:
            client_id = self.client_map.get(self.sale_client.get())
            if not client_id:
                raise ValueError("Selecione ou cadastre um cliente.")
            date.fromisoformat(self.sale_date.get())
            sale_id = self.db.save_sale(client_id, self.sale_date.get(), self.current_items, self.editing_sale_id)
            messagebox.showinfo("Venda", f"Venda nº {sale_id} salva com sucesso.")
            self.clear_sale()
            self.refresh_sales()
            self.run_report(show_errors=False)
            self.refresh_dashboard()
        except Exception as exc:
            messagebox.showerror("Venda", str(exc))

    def refresh_sales(self):
        for item in self.sales_tree.get_children():
            self.sales_tree.delete(item)
        for sale in self.db.list_sales():
            self.sales_tree.insert("", "end", values=(f"#{sale['id']}", sale["sale_date"], sale["client_name"], sale["item_count"], money(sale["total_cents"])))

    def edit_sale(self):
        row = self._selected(self.sales_tree)
        if not row:
            return messagebox.showwarning("Venda", "Selecione uma venda.")
        sale_id = int(str(row[0]).replace("#", ""))
        sale, items = self.db.get_sale(sale_id)
        self.editing_sale_id = sale["id"]
        self.sale_date.set(sale["sale_date"])
        self.sale_client.set(next((name for name, client_id in self.client_map.items() if client_id == sale["client_id"]), ""))
        self.current_items = [dict(product_id=item["product_id"], product_name=item["product_name"], quantity=item["quantity"], unit_price_cents=item["unit_price_cents"]) for item in items]
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
            date.fromisoformat(self.start.get())
            date.fromisoformat(self.end.get())
            client_id = self.report_client_map.get(self.report_client.get())
            self.report_rows = self.db.revenue_report(self.start.get(), self.end.get(), client_id)
            for item in self.report_tree.get_children():
                self.report_tree.delete(item)
            for row in self.report_rows:
                self.report_tree.insert("", "end", values=(row["client_name"], money(row["total_cents"])))
            total = sum(row["total_cents"] for row in self.report_rows)
            self.report_total.config(text=f"TOTAL BRUTO: {money(total)}")
        except Exception as exc:
            if show_errors:
                messagebox.showerror("Relatório", str(exc))

    def product_report(self):
        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")], initialfile="lista_de_produtos.pdf")
        if path:
            product_pdf(path, self.db.list_products())
            messagebox.showinfo("PDF", f"Relatório salvo em:\n{path}")

    def revenue_report_pdf(self):
        self.run_report()
        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")], initialfile="faturamento_bruto.pdf")
        if path:
            revenue_pdf(path, self.report_rows, self.start.get(), self.end.get(), self.report_client.get())
            messagebox.showinfo("PDF", f"Relatório salvo em:\n{path}")

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
            target = self.db.backup(folder)
            messagebox.showinfo("Backup", f"Backup criado em:\n{target}")


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
