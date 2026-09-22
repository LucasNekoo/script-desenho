"""
Utilitários de tela.

Trata o problema mais comum de automação no Windows: escala de DPI. Sem
declarar consciência de DPI, o Windows mente sobre o tamanho da tela e o
cursor vai parar em coordenadas erradas.
"""

from __future__ import annotations

import sys
from typing import Tuple

Rect = Tuple[int, int, int, int]  # (x, y, largura, altura)


def enable_dpi_awareness() -> None:
    """Declara o processo como consciente de DPI (Windows). Silencioso fora dele."""
    if sys.platform != "win32":
        return
    import ctypes

    try:  # Windows 8.1+
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_DPI_AWARE
        return
    except (AttributeError, OSError):
        pass
    try:  # Vista+
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


def virtual_screen(tk_widget=None) -> Rect:
    """Retângulo que cobre todos os monitores.

    No Windows usa as métricas do sistema; em outras plataformas cai para o
    tamanho da tela informado pelo Tk.
    """
    if sys.platform == "win32":
        import ctypes

        try:
            gsm = ctypes.windll.user32.GetSystemMetrics
            x = gsm(76)   # SM_XVIRTUALSCREEN
            y = gsm(77)   # SM_YVIRTUALSCREEN
            w = gsm(78)   # SM_CXVIRTUALSCREEN
            h = gsm(79)   # SM_CYVIRTUALSCREEN
            if w > 0 and h > 0:
                return x, y, w, h
        except (AttributeError, OSError):
            pass

    if tk_widget is not None:
        return 0, 0, tk_widget.winfo_screenwidth(), tk_widget.winfo_screenheight()
    return 0, 0, 1280, 720


def primary_screen(tk_widget=None) -> Rect:
    """Retângulo do monitor principal."""
    if sys.platform == "win32":
        import ctypes

        try:
            gsm = ctypes.windll.user32.GetSystemMetrics
            w, h = gsm(0), gsm(1)  # SM_CXSCREEN, SM_CYSCREEN
            if w > 0 and h > 0:
                return 0, 0, w, h
        except (AttributeError, OSError):
            pass
    if tk_widget is not None:
        return 0, 0, tk_widget.winfo_screenwidth(), tk_widget.winfo_screenheight()
    return 0, 0, 1280, 720


def contains(outer: Rect, inner: Rect) -> bool:
    """Diz se `inner` cabe inteiramente dentro de `outer`."""
    ox, oy, ow, oh = outer
    ix, iy, iw, ih = inner
    return (ix >= ox and iy >= oy
            and ix + iw <= ox + ow and iy + ih <= oy + oh)


def clamp_rect(rect: Rect, bounds: Rect) -> Rect:
    """Garante que `rect` não escape de `bounds`."""
    x, y, w, h = rect
    bx, by, bw, bh = bounds
    x = max(bx, min(x, bx + bw - 1))
    y = max(by, min(y, by + bh - 1))
    w = max(1, min(w, bx + bw - x))
    h = max(1, min(h, by + bh - y))
    return x, y, w, h
