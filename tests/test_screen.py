from __future__ import annotations

import pytest

from autodraw import screen
from autodraw.screen import avoid_corners, contains

SCREEN = (0, 0, 1920, 1080)


def _corners(r):
    x, y, w, h = r
    return [(x, y), (x + w - 1, y), (x, y + h - 1), (x + w - 1, y + h - 1)]


def _inside(point, rect) -> bool:
    x, y, w, h = rect
    return x <= point[0] < x + w and y <= point[1] < y + h


def test_contains() -> None:
    assert contains(SCREEN, (100, 100, 200, 200))
    assert contains(SCREEN, SCREEN)
    assert not contains(SCREEN, (1800, 100, 200, 200))
    assert not contains(SCREEN, (-1, 0, 10, 10))


def test_area_away_from_corners_is_untouched() -> None:
    rect = (100, 100, 400, 300)
    assert avoid_corners(rect, SCREEN) == rect


def test_area_on_top_left_corner_is_pulled_inward() -> None:
    result = avoid_corners((0, 0, 300, 200), SCREEN, margin=2)
    assert result == (2, 2, 298, 198)
    assert not _inside((0, 0), result)


@pytest.mark.parametrize("rect", [
    SCREEN,
    (1500, 0, 420, 300),      # canto superior direito
    (0, 800, 300, 280),       # canto inferior esquerdo
    (1600, 900, 320, 180),    # canto inferior direito
])
def test_no_screen_corner_remains_inside(rect) -> None:
    result = avoid_corners(rect, SCREEN)
    assert contains(rect, result)
    for corner in _corners(SCREEN):
        assert not _inside(corner, result)


def test_secondary_monitor_offset() -> None:
    other = (1920, 0, 1280, 1024)
    result = avoid_corners((1920, 0, 100, 100), other)
    assert not _inside((1920, 0), result)


def test_wayland_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(screen.sys, "platform", "linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert screen.session_warning()
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    assert screen.session_warning() is None
    monkeypatch.setattr(screen.sys, "platform", "win32")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert screen.session_warning() is None
