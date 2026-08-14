from __future__ import annotations

import time
import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable
from tkinter import ttk


def _ease_out_cubic(progress: float) -> float:
    progress = max(0.0, min(1.0, progress))
    return 1.0 - (1.0 - progress) ** 3


class MotionController:
    """Small, cancellable Tk animations shared by the application screens."""

    FRAME_MS = 16

    def __init__(self, root: tk.Misc, px: Callable[[float], int]):
        self.root = root
        self.px = px
        self._jobs: dict[str, set[str]] = {}
        self.page_overlay: tk.Frame | None = None
        self.toast_widget: tk.Frame | None = None
        self.tab_indicator: tk.Frame | None = None
        self._tree_states: dict[str, tuple[tk.Widget, str, tuple[str, ...]]] = {}

    def _schedule(self, group: str, delay: int, callback: Callable[[], None]):
        holder: dict[str, str] = {}

        def run():
            job = holder.get("job")
            if job:
                self._jobs.get(group, set()).discard(job)
            try:
                callback()
            except tk.TclError:
                return

        job = self.root.after(delay, run)
        holder["job"] = job
        self._jobs.setdefault(group, set()).add(job)
        return job

    def _cancel_group(self, group: str):
        for job in self._jobs.pop(group, set()):
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass

    @staticmethod
    def _destroy(widget: tk.Widget | None):
        if widget is None:
            return
        try:
            if widget.winfo_exists():
                widget.destroy()
        except tk.TclError:
            pass

    def cancel_all(self):
        for group in tuple(self._jobs):
            self._cancel_group(group)
        for group in tuple(self._tree_states):
            self._restore_tree_row(group, select=False)
        self._destroy(self.page_overlay)
        self._destroy(self.toast_widget)
        self._destroy(self.tab_indicator)
        self.page_overlay = None
        self.toast_widget = None
        self.tab_indicator = None

    def reveal_page(self, parent: tk.Widget, background: str, accent: str):
        """Reveal the already-selected page from left to right."""

        group = "page"
        self._cancel_group(group)
        self._destroy(self.page_overlay)

        overlay = tk.Frame(parent, bg=background, borderwidth=0)
        tk.Frame(overlay, bg=accent, width=self.px(5)).pack(side="left", fill="y")
        overlay.place(relx=0.0, rely=0.0, relwidth=1.0, relheight=1.0)
        overlay.tkraise()
        self.page_overlay = overlay
        started = time.monotonic()
        duration = 0.22

        def step():
            if self.page_overlay is not overlay:
                return
            progress = min(1.0, (time.monotonic() - started) / duration)
            eased = _ease_out_cubic(progress)
            overlay.place_configure(
                relx=eased,
                relwidth=max(0.001, 1.0 - eased),
            )
            if progress < 1.0:
                self._schedule(group, self.FRAME_MS, step)
            else:
                self._destroy(overlay)
                if self.page_overlay is overlay:
                    self.page_overlay = None

        self._schedule(group, self.FRAME_MS, step)

    def show_toast(
        self,
        text: str,
        *,
        panel: str,
        text_color: str,
        muted: str,
        accent: str,
        border: str,
    ):
        """Show a short, non-blocking success message sliding from the right."""

        group = "toast"
        self._cancel_group(group)
        self._destroy(self.toast_widget)

        toast = tk.Frame(
            self.root,
            bg=panel,
            highlightthickness=1,
            highlightbackground=border,
            borderwidth=0,
        )
        tk.Frame(toast, bg=accent, width=self.px(5)).pack(side="left", fill="y")
        icon = tk.Label(
            toast,
            text="✓",
            bg=accent,
            fg="white",
            width=2,
            font=("Segoe UI", 12, "bold"),
        )
        icon.pack(side="left", fill="y")
        copy = tk.Frame(toast, bg=panel)
        copy.pack(side="left", padx=self.px(14), pady=self.px(11))
        tk.Label(
            copy,
            text="ALTERAÇÃO SALVA",
            bg=panel,
            fg=muted,
            anchor="w",
            font=("Segoe UI Semibold", 8),
        ).pack(fill="x")
        tk.Label(
            copy,
            text=text,
            bg=panel,
            fg=text_color,
            anchor="w",
            justify="left",
            wraplength=self.px(380),
            font=("Segoe UI Semibold", 10),
        ).pack(fill="x", pady=(self.px(2), 0))

        toast.update_idletasks()
        width = max(self.px(300), toast.winfo_reqwidth())
        target_x = -self.px(22)
        hidden_x = width + self.px(18)
        toast.place(relx=1.0, x=hidden_x, y=self.px(96), anchor="ne")
        toast.tkraise()
        self.toast_widget = toast

        def animate(start_x: int, end_x: int, duration: float, on_done=None):
            started = time.monotonic()

            def step():
                if self.toast_widget is not toast:
                    return
                progress = min(1.0, (time.monotonic() - started) / duration)
                eased = _ease_out_cubic(progress)
                current_x = round(start_x + (end_x - start_x) * eased)
                toast.place_configure(x=current_x)
                if progress < 1.0:
                    self._schedule(group, self.FRAME_MS, step)
                elif on_done:
                    on_done()

            step()

        def close():
            def finish():
                self._destroy(toast)
                if self.toast_widget is toast:
                    self.toast_widget = None

            animate(target_x, hidden_x, 0.18, finish)

        animate(hidden_x, target_x, 0.2)
        self._schedule(group, 2400, close)

    def _restore_tree_row(self, group: str, select: bool):
        state = self._tree_states.pop(group, None)
        if state is None:
            return
        tree, item_id, original_tags = state
        try:
            if tree.winfo_exists() and tree.exists(item_id):
                tree.item(item_id, tags=original_tags)
                if select:
                    tree.selection_set(item_id)
                    tree.focus(item_id)
                    tree.see(item_id)
        except tk.TclError:
            pass

    def pulse_tree_row(
        self,
        tree,
        item_id,
        *,
        success: str,
        soft: str,
        text: str,
    ):
        """Pulse a saved row twice, then leave it selected and visible."""

        item_id = str(item_id)
        group = f"tree:{str(tree)}"
        self._cancel_group(group)
        self._restore_tree_row(group, select=False)
        if not tree.exists(item_id):
            return

        original_tags = tuple(tree.item(item_id, "tags"))
        self._tree_states[group] = (tree, item_id, original_tags)
        tree.tag_configure("motion_success", background=success, foreground="white")
        tree.tag_configure("motion_soft", background=soft, foreground=text)
        tree.selection_remove(*tree.selection())
        tree.item(item_id, tags=("motion_success",))
        tree.focus(item_id)
        tree.see(item_id)

        def set_tag(tag: str):
            if tree.exists(item_id):
                tree.item(item_id, tags=(tag,))

        self._schedule(group, 105, lambda: set_tag("motion_soft"))
        self._schedule(group, 215, lambda: set_tag("motion_success"))
        self._schedule(group, 760, lambda: self._restore_tree_row(group, select=True))

    def underline_tab(self, notebook, *, accent: str):
        """Animate a compact underline below the newly selected notebook tab."""

        group = "tab"
        self._cancel_group(group)
        self._destroy(self.tab_indicator)
        try:
            selected = notebook.select()
            if not selected:
                return
            x, y, width, height = notebook.bbox(selected)
        except tk.TclError:
            return
        if width <= 0:
            try:
                selected_index = notebook.index(selected)
                style = ttk.Style(notebook)
                tab_font = tkfont.Font(
                    root=notebook,
                    font=style.lookup("Inner.TNotebook.Tab", "font"),
                )
                x = 0
                for index in range(selected_index):
                    label = notebook.tab(index, "text")
                    x += tab_font.measure(label) + self.px(40)
                label = notebook.tab(selected_index, "text")
                width = tab_font.measure(label) + self.px(56)
                height = tab_font.metrics("linespace") + self.px(34)
                y = self.px(8)
            except tk.TclError:
                return

        indicator = tk.Frame(notebook, bg=accent, borderwidth=0)
        indicator.place(
            x=x,
            y=y + height - self.px(3),
            width=self.px(8),
            height=self.px(3),
        )
        indicator.tkraise()
        self.tab_indicator = indicator
        started = time.monotonic()
        duration = 0.19

        def step():
            if self.tab_indicator is not indicator:
                return
            progress = min(1.0, (time.monotonic() - started) / duration)
            current_width = max(self.px(8), round(width * _ease_out_cubic(progress)))
            indicator.place_configure(width=current_width)
            if progress < 1.0:
                self._schedule(group, self.FRAME_MS, step)
            else:
                self._schedule(group, 180, finish)

        def finish():
            self._destroy(indicator)
            if self.tab_indicator is indicator:
                self.tab_indicator = None

        self._schedule(group, self.FRAME_MS, step)
