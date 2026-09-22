"""
Contagem regressiva antes do desenho.

Mostra um número grande sobre todas as janelas, sem bloquear o laço do Tk
(usa `after`), e pode ser cancelada com Esc ou pelo programa.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional


class CountdownWindow:
    """Contagem visual de N segundos.

    `on_finish` é chamado ao chegar a zero; `on_cancel`, se o usuário abortar.
    """

    def __init__(self, master: tk.Misc, seconds: int,
                 on_finish: Callable[[], None],
                 on_cancel: Optional[Callable[[], None]] = None,
                 message: str = "Posicione a janela do jogo") -> None:
        self.master = master
        self.remaining = seconds
        self.on_finish = on_finish
        self.on_cancel = on_cancel
        self.message = message
        self.win: Optional[tk.Toplevel] = None
        self._after_id: Optional[str] = None
        self._done = False

    def start(self) -> None:
        win = tk.Toplevel(self.master)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        try:
            win.attributes("-alpha", 0.88)
        except tk.TclError:
            pass
        win.configure(bg="#101418")

        w, h = 320, 220
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        win.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 3}")

        self.number = tk.Label(win, text=str(self.remaining), fg="#7fd4ff", bg="#101418",
                               font=("Segoe UI", 96, "bold"))
        self.number.pack(pady=(18, 0))
        tk.Label(win, text=self.message, fg="#e6edf3", bg="#101418",
                 font=("Segoe UI", 11)).pack()
        tk.Label(win, text="Esc cancela", fg="#8b98a5", bg="#101418",
                 font=("Segoe UI", 9)).pack(pady=(6, 0))

        win.bind("<Escape>", lambda _e: self.cancel())
        win.focus_force()
        self.win = win
        self._tick()

    def _tick(self) -> None:
        if self._done or self.win is None:
            return
        if self.remaining <= 0:
            self._close()
            self._done = True
            self.on_finish()
            return
        self.number.configure(text=str(self.remaining))
        self.remaining -= 1
        self._after_id = self.win.after(1000, self._tick)

    def cancel(self) -> None:
        if self._done:
            return
        self._done = True
        self._close()
        if self.on_cancel:
            self.on_cancel()

    def _close(self) -> None:
        if self.win is not None:
            if self._after_id:
                try:
                    self.win.after_cancel(self._after_id)
                except tk.TclError:
                    pass
            self.win.destroy()
            self.win = None
