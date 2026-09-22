"""
Tecla de parada global (Esc), ativa mesmo quando o jogo está em foco.

Depende de `pynput`. Se a biblioteca não estiver instalada, o programa continua
funcionando — a parada fica disponível pelo botão da interface e pelo failsafe
(levar o cursor ao canto superior esquerdo da tela).
"""

from __future__ import annotations

from typing import Callable, Optional


class EscapeListener:
    """Escuta a tecla Esc em segundo plano enquanto o desenho roda."""

    def __init__(self, on_escape: Callable[[], None]) -> None:
        self.on_escape = on_escape
        self._listener = None

    @property
    def available(self) -> bool:
        try:
            import pynput  # noqa: F401
        except Exception:
            return False
        return True

    def start(self) -> bool:
        if self._listener is not None:
            return True
        try:
            from pynput import keyboard
        except Exception:
            return False

        def on_press(key) -> None:
            if key == keyboard.Key.esc:
                self.on_escape()

        try:
            self._listener = keyboard.Listener(on_press=on_press)
            self._listener.daemon = True
            self._listener.start()
            return True
        except Exception:
            self._listener = None
            return False

    def stop(self) -> None:
        listener = self._listener
        self._listener = None
        if listener is not None:
            try:
                listener.stop()
            except Exception:
                pass
