from __future__ import annotations

import calendar
import re
import tkinter as tk
from datetime import date
from tkinter import ttk

DATE_MASK = "  /  /  "
DATE_POSITIONS = (0, 1, 3, 4, 6, 7)
MONTH_NAMES = (
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
)
WEEKDAY_NAMES = ("SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM")


def parse_date(value: str | date) -> date:
    """Parse the UI format dd/mm/yy or the internal ISO format."""
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    iso_match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    display_match = re.fullmatch(r"(\d{2})/(\d{2})/(\d{2})", text)
    try:
        if iso_match:
            year, month, day = (int(part) for part in iso_match.groups())
            return date(year, month, day)
        if display_match:
            day, month, short_year = (int(part) for part in display_match.groups())
            return date(2000 + short_year, month, day)
    except ValueError as exc:
        raise ValueError("Informe uma data válida no formato dd/mm/aa.") from exc
    raise ValueError("Informe a data completa no formato dd/mm/aa.")


def display_date(value: str | date) -> str:
    return parse_date(value).strftime("%d/%m/%y")


def iso_date(value: str | date) -> str:
    return parse_date(value).isoformat()


class MaskedDateEntry(ttk.Entry):
    """Fixed-position date entry that never removes its slash separators."""

    def __init__(self, parent, variable: tk.StringVar, **kwargs):
        self.variable = variable
        initial = variable.get()
        super().__init__(parent, textvariable=variable, **kwargs)
        self.set_date(initial)
        self.bind("<KeyPress>", self._on_keypress)
        self.bind("<Control-a>", self._select_all)
        self.bind("<Control-A>", self._select_all)
        self.bind("<<Paste>>", self._paste)
        self.bind("<<Cut>>", self._cut)
        self.bind("<<Clear>>", self._cut)

    def set_date(self, value: str | date | None):
        if value in (None, "", DATE_MASK):
            self.variable.set(DATE_MASK)
        else:
            self.variable.set(display_date(value))
        self.icursor(0)

    def get_iso(self) -> str:
        return iso_date(self.variable.get())

    def clear_date(self):
        self.variable.set(DATE_MASK)
        self.icursor(0)

    def _masked_characters(self) -> list[str]:
        value = list(self.variable.get().ljust(len(DATE_MASK))[: len(DATE_MASK)])
        value[2] = "/"
        value[5] = "/"
        for index in DATE_POSITIONS:
            if not value[index].isdigit():
                value[index] = " "
        return value

    def _selection(self):
        try:
            return int(self.index("sel.first")), int(self.index("sel.last"))
        except tk.TclError:
            return None

    def _clear_range(self, start: int, end: int):
        value = self._masked_characters()
        for index in DATE_POSITIONS:
            if start <= index < end:
                value[index] = " "
        self.variable.set("".join(value))
        self.selection_clear()

    def _select_all(self, _event=None):
        self.selection_range(0, "end")
        self.icursor("end")
        return "break"

    def _paste(self, _event=None):
        try:
            text = self.clipboard_get().strip()
        except tk.TclError:
            return "break"
        try:
            self.set_date(text)
        except ValueError:
            digits = "".join(character for character in text if character.isdigit())[:6]
            value = list(DATE_MASK)
            for index, digit in zip(DATE_POSITIONS, digits, strict=False):
                value[index] = digit
            self.variable.set("".join(value))
            self.icursor("end" if len(digits) >= 6 else DATE_POSITIONS[len(digits)])
        return "break"

    def _cut(self, _event=None):
        selection = self._selection()
        if selection:
            start, end = selection
            self._clear_range(start, end)
            self.icursor(start)
        return "break"

    def _on_keypress(self, event):
        if event.state & 0x4 and event.keysym.lower() in {"a", "c", "v", "x"}:
            return None
        if event.keysym in {"Tab", "ISO_Left_Tab", "Return", "Escape"}:
            return None
        if event.keysym in {"Left", "Right", "Home", "End"}:
            return None

        selection = self._selection()
        cursor = int(self.index("insert"))
        if event.char.isdigit():
            if selection:
                cursor = selection[0]
                self._clear_range(*selection)
            position = next((index for index in DATE_POSITIONS if index >= cursor), None)
            if position is None:
                return "break"
            value = self._masked_characters()
            value[position] = event.char
            self.variable.set("".join(value))
            following = next(
                (index for index in DATE_POSITIONS if index > position),
                len(DATE_MASK),
            )
            self.icursor(following)
            return "break"

        if event.keysym == "BackSpace":
            if selection:
                self._clear_range(*selection)
                self.icursor(selection[0])
            else:
                position = next(
                    (index for index in reversed(DATE_POSITIONS) if index < cursor),
                    None,
                )
                if position is not None:
                    value = self._masked_characters()
                    value[position] = " "
                    self.variable.set("".join(value))
                    self.icursor(position)
            return "break"

        if event.keysym == "Delete":
            if selection:
                self._clear_range(*selection)
                self.icursor(selection[0])
            else:
                position = next(
                    (index for index in DATE_POSITIONS if index >= cursor),
                    None,
                )
                if position is not None:
                    value = self._masked_characters()
                    value[position] = " "
                    self.variable.set("".join(value))
                    self.icursor(position)
            return "break"

        return "break" if event.char else None


class CalendarPopup(tk.Toplevel):
    def __init__(self, field, initial_value, on_select, palette, px):
        super().__init__(field.winfo_toplevel())
        self.field = field
        self.on_select = on_select
        self.palette = palette
        self.px = px
        try:
            selected = parse_date(initial_value)
        except ValueError:
            selected = date.today()
        self.selected = selected
        self.year = selected.year
        self.month = selected.month

        self.title("Selecionar data")
        self.configure(bg=palette["panel"])
        self.resizable(False, False)
        self.transient(field.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _event: self.close())
        self.bind("<FocusOut>", self._close_if_focus_left)

        header = tk.Frame(self, bg=palette["soft"], padx=px(10), pady=px(9))
        header.pack(fill="x")
        tk.Button(
            header,
            text="‹",
            command=lambda: self._change_month(-1),
            bg=palette["soft"],
            fg=palette["text"],
            activebackground=palette["soft_hover"],
            activeforeground=palette["text"],
            relief="flat",
            borderwidth=0,
            font=("Segoe UI", 16, "bold"),
            cursor="hand2",
            width=2,
        ).pack(side="left")
        self.month_title = tk.Label(
            header,
            bg=palette["soft"],
            fg=palette["text"],
            font=("Segoe UI", 11, "bold"),
            width=20,
        )
        self.month_title.pack(side="left", padx=px(4))
        tk.Button(
            header,
            text="›",
            command=lambda: self._change_month(1),
            bg=palette["soft"],
            fg=palette["text"],
            activebackground=palette["soft_hover"],
            activeforeground=palette["text"],
            relief="flat",
            borderwidth=0,
            font=("Segoe UI", 16, "bold"),
            cursor="hand2",
            width=2,
        ).pack(side="right")

        self.days = tk.Frame(self, bg=palette["panel"], padx=px(10), pady=px(10))
        self.days.pack(fill="both", expand=True)
        self._render_month()
        self.update_idletasks()
        self._position_near_field()
        self.grab_set()
        self.focus_force()

    def _position_near_field(self):
        x = self.field.winfo_rootx()
        y = self.field.winfo_rooty() + self.field.winfo_height() + self.px(4)
        width = self.winfo_reqwidth()
        height = self.winfo_reqheight()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = max(0, min(x, screen_width - width - self.px(8)))
        if y + height > screen_height:
            y = max(0, self.field.winfo_rooty() - height - self.px(4))
        self.geometry(f"+{x}+{y}")

    def _render_month(self):
        for child in self.days.winfo_children():
            child.destroy()
        self.month_title.config(text=f"{MONTH_NAMES[self.month - 1]} de {self.year}")
        for column, label in enumerate(WEEKDAY_NAMES):
            tk.Label(
                self.days,
                text=label,
                bg=self.palette["panel"],
                fg=self.palette["muted"],
                font=("Segoe UI", 8, "bold"),
                width=4,
            ).grid(row=0, column=column, padx=self.px(2), pady=(0, self.px(5)))

        weeks = calendar.Calendar(firstweekday=calendar.MONDAY).monthdayscalendar(
            self.year, self.month
        )
        today = date.today()
        for row, week in enumerate(weeks, start=1):
            for column, day_number in enumerate(week):
                if not day_number:
                    tk.Label(
                        self.days,
                        text="",
                        bg=self.palette["panel"],
                        width=4,
                        height=2,
                    ).grid(row=row, column=column, padx=self.px(2), pady=self.px(2))
                    continue
                current = date(self.year, self.month, day_number)
                selected = current == self.selected
                is_today = current == today
                button = tk.Button(
                    self.days,
                    text=str(day_number),
                    command=lambda chosen=current: self.select(chosen),
                    bg=self.palette["accent"] if selected else self.palette["panel"],
                    fg="white" if selected else self.palette["text"],
                    activebackground=self.palette["accent_hover"],
                    activeforeground="white",
                    relief="solid" if is_today and not selected else "flat",
                    borderwidth=1 if is_today and not selected else 0,
                    highlightthickness=0,
                    font=("Segoe UI", 9, "bold" if selected else "normal"),
                    cursor="hand2",
                    width=4,
                    height=2,
                )
                button.grid(row=row, column=column, padx=self.px(2), pady=self.px(2))

    def _change_month(self, amount):
        zero_based = self.year * 12 + self.month - 1 + amount
        self.year, month_index = divmod(zero_based, 12)
        self.month = month_index + 1
        self._render_month()

    def select(self, chosen: date):
        self.on_select(chosen)
        self.close()

    def _close_if_focus_left(self, _event=None):
        self.after(50, self._check_focus)

    def _check_focus(self):
        try:
            focused = self.focus_get()
            if focused is None or focused.winfo_toplevel() is not self:
                self.close()
        except tk.TclError:
            pass

    def close(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass
        if self.winfo_exists():
            self.destroy()


class DateField(tk.Frame):
    def __init__(
        self,
        parent,
        variable,
        icon,
        palette,
        px,
        width=12,
        background=None,
        **kwargs,
    ):
        super().__init__(parent, bg=background or palette["panel"], **kwargs)
        self.variable = variable
        self.palette = palette
        self.px = px
        self.popup = None
        self.entry = MaskedDateEntry(self, variable, width=width, justify="center")
        self.entry.pack(side="left")
        self.calendar_button = ttk.Button(
            self,
            image=icon,
            style="Calendar.TButton",
            command=self.open_calendar,
            takefocus=False,
        )
        self.calendar_button.pack(side="left", padx=(px(4), 0))

    def open_calendar(self):
        if self.popup and self.popup.winfo_exists():
            self.popup.focus_force()
            return
        self.popup = CalendarPopup(
            self,
            self.variable.get(),
            self.entry.set_date,
            self.palette,
            self.px,
        )
