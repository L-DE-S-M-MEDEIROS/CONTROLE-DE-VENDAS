from __future__ import annotations

import time
import tkinter as tk
from collections.abc import Callable


def _smoothstep(progress: float) -> float:
    progress = max(0.0, min(1.0, progress))
    return progress**3 * (progress * (progress * 6.0 - 15.0) + 10.0)


class MotionController:
    """Short, neutral and cancellable motion for the desktop interface."""

    FRAME_MS = 5
    PAGE_DURATION = 0.18

    def __init__(self, root: tk.Misc, px: Callable[[float], int]):
        self.root = root
        self.px = px
        self._jobs: dict[str, set[str]] = {}
        self.page_widget: tk.Widget | None = None
        self.toast_widget: tk.Frame | None = None
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

    def _restore_page(self):
        page = self.page_widget
        self.page_widget = None
        if page is None:
            return
        try:
            if page.winfo_exists():
                page.place_configure(x=0)
                page.tkraise()
        except tk.TclError:
            pass

    def cancel_all(self):
        for group in tuple(self._jobs):
            self._cancel_group(group)
        self._restore_page()
        for group in tuple(self._tree_states):
            self._restore_tree_row(group, select=False)
        self._destroy(self.toast_widget)
        self.toast_widget = None

    def present_page(self, page: tk.Widget, *, animate: bool):
        """Raise a page once and move it smoothly without changing layout managers."""

        group = "page"
        self._cancel_group(group)
        self._restore_page()

        distance = self.px(14) if animate else 0
        page.place_configure(x=distance)
        page.tkraise()
        if not animate:
            return

        self.page_widget = page
        started: float | None = None

        def step():
            nonlocal started
            if self.page_widget is not page:
                return
            now = time.perf_counter()
            if started is None:
                started = now
            progress = min(1.0, (now - started) / self.PAGE_DURATION)
            offset = round(distance * (1.0 - _smoothstep(progress)))
            page.place_configure(x=offset)
            if progress < 1.0:
                self._schedule(group, self.FRAME_MS, step)
            else:
                self._restore_page()

        self._schedule(group, self.FRAME_MS, step)

    def show_toast(
        self,
        text: str,
        *,
        panel: str,
        text_color: str,
        muted: str,
        border: str,
    ):
        """Show a compact neutral message without blocking the current task."""

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
        tk.Label(
            toast,
            text="✓",
            bg=panel,
            fg=muted,
            width=2,
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left", fill="y", padx=(self.px(9), 0))
        copy = tk.Frame(toast, bg=panel)
        copy.pack(side="left", padx=(self.px(8), self.px(14)), pady=self.px(9))
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
            font=("Segoe UI Semibold", 9),
        ).pack(fill="x", pady=(self.px(1), 0))

        toast.update_idletasks()
        width = max(self.px(280), toast.winfo_reqwidth())
        target_x = -self.px(20)
        hidden_x = width + self.px(14)
        toast.place(relx=1.0, x=hidden_x, y=self.px(94), anchor="ne")
        toast.tkraise()
        self.toast_widget = toast

        def animate(start_x: int, end_x: int, duration: float, on_done=None):
            started = time.monotonic()

            def step():
                if self.toast_widget is not toast:
                    return
                progress = min(1.0, (time.monotonic() - started) / duration)
                eased = _smoothstep(progress)
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

            animate(target_x, hidden_x, 0.11, finish)

        animate(hidden_x, target_x, 0.13)
        self._schedule(group, 1700, close)

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

    def highlight_tree_row(
        self,
        tree,
        item_id,
        *,
        background: str,
        text: str,
    ):
        """Briefly apply a neutral highlight, then keep the saved row selected."""

        item_id = str(item_id)
        group = f"tree:{str(tree)}"
        self._cancel_group(group)
        self._restore_tree_row(group, select=False)
        if not tree.exists(item_id):
            return

        original_tags = tuple(tree.item(item_id, "tags"))
        self._tree_states[group] = (tree, item_id, original_tags)
        tree.tag_configure("motion_highlight", background=background, foreground=text)
        selected = tree.selection()
        if selected:
            tree.selection_remove(*selected)
        tree.item(item_id, tags=("motion_highlight",))
        tree.focus(item_id)
        tree.see(item_id)
        self._schedule(
            group,
            280,
            lambda: self._restore_tree_row(group, select=True),
        )
