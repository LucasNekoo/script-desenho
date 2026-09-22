"""
Seleção da área de desenho.

Abre uma camada semitransparente sobre todos os monitores; o usuário arrasta o
mouse para definir o retângulo. Enter/soltar o botão confirma, Esc ou o botão
direito cancela.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional, Tuple

from .screen import Rect, virtual_screen

MIN_SIDE = 20  # px: abaixo disso a seleção é considerada acidental


class AreaSelector:
    """Camada de seleção. Uso: ``AreaSelector(root, on_done).start()``."""

    def __init__(self, master: tk.Misc,
                 on_done: Callable[[Optional[Rect]], None],
                 hint: str = "Arraste para marcar a área de desenho · Esc cancela") -> None:
        self.master = master
        self.on_done = on_done
        self.hint = hint
        self.win: Optional[tk.Toplevel] = None
        self.canvas: Optional[tk.Canvas] = None
        self.origin: Optional[Tuple[int, int]] = None
        self._rect_id: Optional[int] = None
        self._label_id: Optional[int] = None
        self._offset = (0, 0)
        self._finished = False

    # ------------------------------------------------------------------
    def start(self) -> None:
        vx, vy, vw, vh = virtual_screen(self.master)
        self._offset = (vx, vy)

        win = tk.Toplevel(self.master)
        win.overrideredirect(True)
        win.geometry(f"{vw}x{vh}+{vx}+{vy}")
        win.attributes("-topmost", True)
        try:
            win.attributes("-alpha", 0.35)
        except tk.TclError:
            pass
        win.configure(bg="black", cursor="crosshair")

        canvas = tk.Canvas(win, bg="black", highlightthickness=0, cursor="crosshair")
        canvas.pack(fill="both", expand=True)
        canvas.create_text(vw // 2, 40, text=self.hint, fill="white",
                           font=("Segoe UI", 16, "bold"))

        canvas.bind("<ButtonPress-1>", self._on_press)
        canvas.bind("<B1-Motion>", self._on_drag)
        canvas.bind("<ButtonRelease-1>", self._on_release)
        canvas.bind("<Button-3>", lambda _e: self._finish(None))
        win.bind("<Escape>", lambda _e: self._finish(None))
        win.bind("<Key-q>", lambda _e: self._finish(None))

        self.win, self.canvas = win, canvas
        win.focus_force()
        canvas.focus_set()
        win.grab_set()

    # ------------------------------------------------------------------
    def _on_press(self, event: tk.Event) -> None:
        self.origin = (event.x, event.y)
        if self.canvas is None:
            return
        if self._rect_id is not None:
            self.canvas.delete(self._rect_id)
        self._rect_id = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline="#4da3ff", width=2, dash=(6, 3))

    def _on_drag(self, event: tk.Event) -> None:
        if self.origin is None or self.canvas is None or self._rect_id is None:
            return
        x0, y0 = self.origin
        self.canvas.coords(self._rect_id, x0, y0, event.x, event.y)
        w, h = abs(event.x - x0), abs(event.y - y0)
        text = f"{w} × {h}"
        lx, ly = min(x0, event.x) + 6, min(y0, event.y) - 14
        if self._label_id is None:
            self._label_id = self.canvas.create_text(lx, ly, text=text, fill="white",
                                                     anchor="w", font=("Segoe UI", 12, "bold"))
        else:
            self.canvas.coords(self._label_id, lx, ly)
            self.canvas.itemconfigure(self._label_id, text=text)

    def _on_release(self, event: tk.Event) -> None:
        if self.origin is None:
            self._finish(None)
            return
        x0, y0 = self.origin
        x1, y1 = event.x, event.y
        x, y = min(x0, x1), min(y0, y1)
        w, h = abs(x1 - x0), abs(y1 - y0)
        if w < MIN_SIDE or h < MIN_SIDE:
            self._finish(None)
            return
        ox, oy = self._offset
        self._finish((x + ox, y + oy, w, h))

    # ------------------------------------------------------------------
    def _finish(self, rect: Optional[Rect]) -> None:
        if self._finished:
            return
        self._finished = True
        if self.win is not None:
            try:
                self.win.grab_release()
            except tk.TclError:
                pass
            self.win.destroy()
            self.win = None
        self.on_done(rect)
