"""
Controle do mouse e execução do desenho.

Contém duas camadas:

* :class:`MouseBackend` — abstrai a biblioteca de entrada (pydirectinput ou
  pyautogui), importada só quando necessária.
* :class:`DrawingEngine` — percorre as trajetórias, interpola o movimento e
  respeita o evento de parada a cada passo.
"""

from __future__ import annotations

import math
import random
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

from .config import Settings


class InputBackendError(Exception):
    """Nenhuma biblioteca de controle de mouse pôde ser carregada."""


# ----------------------------------------------------------------------
# Backend de entrada
# ----------------------------------------------------------------------

class MouseBackend:
    """Fachada fina sobre pydirectinput / pyautogui.

    pydirectinput é preferido no Windows porque usa `SendInput`, aceito por
    jogos que ignoram `SetCursorPos`. Fora do Windows, pyautogui é o caminho.
    """

    def __init__(self, preference: str = "auto") -> None:
        self.name = ""
        self._lib = None
        self._load(preference)

    def _load(self, preference: str) -> None:
        errors: List[str] = []

        def try_directinput() -> bool:
            if sys.platform != "win32":
                errors.append("pydirectinput só funciona no Windows")
                return False
            try:
                import pydirectinput as lib
            except ImportError as exc:
                errors.append(f"pydirectinput: {exc}")
                return False
            lib.PAUSE = 0.0
            lib.FAILSAFE = True
            self._lib, self.name = lib, "pydirectinput"
            return True

        def try_pyautogui() -> bool:
            try:
                import pyautogui as lib
            except Exception as exc:  # pyautogui pode falhar sem display
                errors.append(f"pyautogui: {exc}")
                return False
            lib.PAUSE = 0.0
            lib.FAILSAFE = True
            lib.MINIMUM_DURATION = 0.0
            lib.MINIMUM_SLEEP = 0.0
            self._lib, self.name = lib, "pyautogui"
            return True

        if preference == "pydirectinput":
            ok = try_directinput()
        elif preference == "pyautogui":
            ok = try_pyautogui()
        else:
            ok = try_directinput() or try_pyautogui()

        if not ok:
            raise InputBackendError(
                "Não foi possível iniciar o controle do mouse. "
                "Instale as dependências (pip install -r requirements.txt). "
                "Detalhes: " + "; ".join(errors)
            )

    # -- operações -----------------------------------------------------
    def move_to(self, x: int, y: int) -> None:
        self._lib.moveTo(int(x), int(y))

    def mouse_down(self) -> None:
        self._lib.mouseDown(button="left")

    def mouse_up(self) -> None:
        self._lib.mouseUp(button="left")

    def position(self) -> Tuple[int, int]:
        pos = self._lib.position()
        return int(pos[0]), int(pos[1])


# ----------------------------------------------------------------------
# Progresso e execução
# ----------------------------------------------------------------------

@dataclass
class Progress:
    """Instantâneo do andamento, enviado à interface."""

    stroke: int
    total_strokes: int
    elapsed: float
    finished: bool = False
    stopped: bool = False
    error: str = ""

    @property
    def fraction(self) -> float:
        if self.total_strokes <= 0:
            return 0.0
        return min(1.0, self.stroke / self.total_strokes)


ProgressCallback = Callable[[Progress], None]


class DrawingEngine:
    """Reproduz as trajetórias com o mouse.

    O método :meth:`draw` roda em uma thread de trabalho; a interface só recebe
    atualizações pelo callback. `stop_event` é verificado antes de cada passo,
    então a parada é imediata (no máximo um passo de atraso) e sempre solta o
    botão do mouse.
    """

    def __init__(self, settings: Settings, backend: Optional[MouseBackend] = None) -> None:
        self.settings = settings
        self.backend = backend or MouseBackend(settings.backend)
        self._button_down = False

    # -- API principal --------------------------------------------------
    def draw(self, paths: Sequence[np.ndarray], stop_event: threading.Event,
             on_progress: Optional[ProgressCallback] = None) -> Progress:
        total = len(paths)
        start = time.perf_counter()
        s = self.settings

        def emit(stroke: int, finished: bool = False, stopped: bool = False, error: str = "") -> Progress:
            p = Progress(stroke=stroke, total_strokes=total,
                         elapsed=time.perf_counter() - start,
                         finished=finished, stopped=stopped, error=error)
            if on_progress:
                on_progress(p)
            return p

        try:
            for i, path in enumerate(paths):
                if stop_event.is_set():
                    return emit(i, stopped=True)
                if len(path) < 2:
                    continue

                # Deslocamento com a "caneta" levantada até o início do traço.
                self._glide(path[0], s.travel_step_px, 0.0, stop_event, jitter=0.0)
                if stop_event.is_set():
                    return emit(i, stopped=True)

                self._pen_down()
                time.sleep(s.pen_delay)

                for point in path[1:]:
                    if stop_event.is_set():
                        self._pen_up()
                        return emit(i, stopped=True)
                    self._glide(point, s.step_px, s.step_delay, stop_event,
                                jitter=s.jitter_px, ease=s.smoothing_factor)

                self._pen_up()
                time.sleep(s.pen_delay)

                emit(i + 1)

            return emit(total, finished=True)

        except Exception as exc:  # inclui o failsafe do pyautogui
            self._pen_up()
            name = type(exc).__name__
            if "FailSafe" in name:
                return emit(0, stopped=True, error="Parada de emergência: cursor no canto da tela.")
            return emit(0, error=f"{name}: {exc}")
        finally:
            self._pen_up()

    def stop_now(self) -> None:
        """Solta o botão imediatamente (chamado pela interface ao abortar)."""
        self._pen_up()

    # -- internos --------------------------------------------------------
    def _pen_down(self) -> None:
        if not self._button_down:
            self.backend.mouse_down()
            self._button_down = True

    def _pen_up(self) -> None:
        if self._button_down:
            try:
                self.backend.mouse_up()
            finally:
                self._button_down = False

    def _glide(self, target: np.ndarray, step_px: float, delay: float,
               stop_event: threading.Event, jitter: float = 0.0,
               ease: float = 0.0) -> None:
        """Move o cursor até `target` em passos curtos e regulares.

        `ease` aplica aceleração/desaceleração suave (smoothstep) e `jitter`
        adiciona um desvio sub-pixel para o traço não parecer robótico.
        """
        tx, ty = float(target[0]), float(target[1])
        cx, cy = self.backend.position()
        dist = math.hypot(tx - cx, ty - cy)

        if dist <= step_px:
            self.backend.move_to(round(tx), round(ty))
            if delay:
                time.sleep(delay)
            return

        steps = max(1, int(dist / max(1.0, step_px)))
        for k in range(1, steps + 1):
            if stop_event.is_set():
                return
            t = k / steps
            if ease > 0:
                smooth = t * t * (3.0 - 2.0 * t)
                t = t + (smooth - t) * ease
            x = cx + (tx - cx) * t
            y = cy + (ty - cy) * t
            if jitter > 0 and k < steps:
                x += random.uniform(-jitter, jitter)
                y += random.uniform(-jitter, jitter)
            self.backend.move_to(round(x), round(y))
            if delay:
                time.sleep(delay)


def estimate_duration(paths: Sequence[np.ndarray], settings: Settings) -> float:
    """Estimativa grosseira do tempo de execução, em segundos."""
    if not paths:
        return 0.0
    step = max(1.0, settings.step_px)
    travel_step = max(1.0, settings.travel_step_px)
    per_step = settings.step_delay + 0.0012  # custo médio de uma chamada de API

    total = 0.0
    cursor = None
    for p in paths:
        if cursor is not None:
            total += (float(np.linalg.norm(p[0] - cursor)) / travel_step) * per_step
        if len(p) > 1:
            length = float(np.sum(np.linalg.norm(np.diff(p, axis=0), axis=1)))
            total += (length / step) * per_step
        total += 2 * settings.pen_delay
        cursor = p[-1]
    return total
