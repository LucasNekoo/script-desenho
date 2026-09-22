"""
Utilitários de tela.

Trata o problema mais comum de automação no Windows: escala de DPI. Sem
declarar consciência de DPI, o Windows mente sobre o tamanho da tela e o
cursor vai parar em coordenadas erradas.
"""

from __future__ import annotations

import os
import sys
from typing import Optional, Tuple

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


def avoid_corners(rect: Rect, screen: Rect, margin: int = 2) -> Rect:
    """Recua `rect` para longe dos cantos de `screen`.

    pyautogui e pydirectinput abortam (failsafe) quando o cursor para num
    canto do monitor principal. Uma área que inclua um canto faria o próprio
    desenho disparar a parada de emergência.
    """
    x, y, w, h = rect
    sx, sy, sw, sh = screen
    left, top, right, bottom = x, y, x + w, y + h  # right/bottom exclusivos
    x_min, y_min = sx, sy
    x_max, y_max = sx + sw - 1, sy + sh - 1

    for cx, cy in ((x_min, y_min), (x_max, y_min), (x_min, y_max), (x_max, y_max)):
        if not (left <= cx < right and top <= cy < bottom):
            continue
        if cx == x_min:
            left = max(left, cx + margin)
        else:
            right = min(right, cx - margin + 1)
        if cy == y_min:
            top = max(top, cy + margin)
        else:
            bottom = min(bottom, cy - margin + 1)

    return left, top, max(0, right - left), max(0, bottom - top)


def session_warning() -> Optional[str]:
    """Aviso quando a sessão gráfica impede o controle do mouse."""
    if sys.platform.startswith("linux") and os.environ.get("XDG_SESSION_TYPE") == "wayland":
        return ("Sessão Wayland detectada: pyautogui e pynput só enxergam janelas XWayland. "
                "O cursor pode não se mover no jogo e o Esc global pode não funcionar. "
                "Para resultados confiáveis, entre numa sessão X11.")
    return None
