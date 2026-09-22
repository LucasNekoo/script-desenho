from __future__ import annotations

import math
import threading

import numpy as np
import pytest

from autodraw.config import Settings
from autodraw.mouse import DrawingEngine, _step_count, estimate_duration

from .conftest import FakeBackend

pytestmark = pytest.mark.usefixtures("no_sleep")


def _paths():
    return [
        np.array([[100, 100], [300, 100], [300, 250]], np.float32),
        np.array([[400, 400], [420, 470]], np.float32),
        np.array([[50, 300], [60, 305], [200, 310]], np.float32),
    ]


def _pen_down_steps(backend: FakeBackend):
    """Distâncias entre posições consecutivas com o botão pressionado."""
    out = []
    for (x0, y0, _), (x1, y1, down) in zip(backend.moves, backend.moves[1:]):
        if down:
            out.append(math.hypot(x1 - x0, y1 - y0))
    return out


def test_draw_completes_and_balances_button() -> None:
    backend = FakeBackend()
    engine = DrawingEngine(Settings(naturalness=0), backend)
    result = engine.draw(_paths(), threading.Event())
    assert result.finished and not result.stopped and not result.error
    assert result.stroke == result.total_strokes == 3
    assert backend.downs == backend.ups == 3
    assert not backend.pressed


def test_moves_stay_near_the_path_bounding_box() -> None:
    backend = FakeBackend()
    DrawingEngine(Settings(naturalness=100), backend).draw(_paths(), threading.Event())
    pts = np.concatenate(_paths())
    lo, hi = pts.min(axis=0) - 2, pts.max(axis=0) + 2
    for x, y, down in backend.moves:
        if down:
            assert lo[0] <= x <= hi[0] and lo[1] <= y <= hi[1]


@pytest.mark.parametrize("speed", [0, 50, 100])
@pytest.mark.parametrize("smoothing", [0, 60, 100])
def test_pen_down_steps_never_exceed_step_px(speed: int, smoothing: int) -> None:
    settings = Settings(speed=speed, smoothing=smoothing, naturalness=0)
    backend = FakeBackend()
    DrawingEngine(settings, backend).draw(_paths(), threading.Event())
    steps = _pen_down_steps(backend)
    assert steps
    assert max(steps) <= settings.step_px + 1.5  # +1,5 px de arredondamento para inteiros


def test_stop_event_interrupts_and_releases_button() -> None:
    stop = threading.Event()
    backend = FakeBackend(on_move=lambda n: stop.set() if n == 20 else None)
    progress = []
    result = DrawingEngine(Settings(speed=0), backend).draw(_paths(), stop, progress.append)
    assert result.stopped and not result.finished
    assert result.stroke < result.total_strokes
    assert not backend.pressed
    assert backend.downs == backend.ups
    assert len(backend.moves) <= 21  # no máximo um passo depois do sinal


def test_failsafe_exception_reports_stop_at_current_stroke() -> None:
    class FailSafeException(Exception):
        pass

    full = FakeBackend()
    DrawingEngine(Settings(speed=0), full).draw(_paths(), threading.Event())
    trigger = int(len(full.moves) * 0.9)  # já dentro do último traço

    def explode(n: int) -> None:
        if n == trigger:
            raise FailSafeException("canto")

    backend = FakeBackend(on_move=explode)
    result = DrawingEngine(Settings(speed=0), backend).draw(_paths(), threading.Event())
    assert result.stopped
    assert "emergência" in result.error
    assert result.stroke == 2
    assert not backend.pressed


def test_stop_now_from_other_thread_is_idempotent() -> None:
    backend = FakeBackend()
    engine = DrawingEngine(Settings(), backend)
    engine._pen_down()
    threads = [threading.Thread(target=engine.stop_now) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert backend.downs == backend.ups == 1


@pytest.mark.parametrize("ease", [0.0, 0.5, 1.0])
@pytest.mark.parametrize("dist", [1.0, 9.9, 10.0, 10.1, 37.0, 500.0])
def test_step_count_bounds_largest_step(dist: float, ease: float) -> None:
    step_px = 10.0
    n = _step_count(dist, step_px, ease)
    largest = dist / n * (1.0 + 0.5 * ease)
    assert largest <= step_px + 1e-9


def test_estimate_duration() -> None:
    assert estimate_duration([], Settings()) == 0.0
    slow = estimate_duration(_paths(), Settings(speed=0))
    fast = estimate_duration(_paths(), Settings(speed=100))
    assert slow > fast > 0
