from __future__ import annotations

import json
from pathlib import Path

import pytest

from autodraw.config import BACKENDS, MODE_HATCH, MODE_OUTLINE, MODES, Settings


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "cfg.json"
    original = Settings(mode=MODE_HATCH, detail=10, speed=90, invert=True, backend="pyautogui")
    original.save(path)
    assert Settings.load(path) == original


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    assert Settings.load(tmp_path / "nao_existe.json") == Settings()


@pytest.mark.parametrize("content", ["{corrompido", "[1, 2, 3]", "42", "null", '"texto"'])
def test_unusable_file_gives_defaults(tmp_path: Path, content: str) -> None:
    path = tmp_path / "cfg.json"
    path.write_text(content, encoding="utf-8")
    assert Settings.load(path) == Settings()


def test_invalid_fields_fall_back_individually() -> None:
    s = Settings.from_dict({
        "mode": "modo_que_nao_existe",
        "backend": "xdotool",
        "invert": "sim",
        "detail": 80,
        "speed": True,        # bool não vale como número
        "precision": "alto",
        "smoothing": float("nan"),
        "max_paths": float("inf"),
        "min_segment_px": -3,
        "campo_desconhecido": 1,
    })
    d = Settings()
    assert s.mode == d.mode
    assert s.backend == d.backend
    assert s.invert == d.invert
    assert s.detail == 80
    assert s.speed == d.speed
    assert s.precision == d.precision
    assert s.smoothing == d.smoothing
    assert s.max_paths == d.max_paths
    assert s.min_segment_px == d.min_segment_px


def test_user_scale_values_are_clamped_and_rounded() -> None:
    s = Settings.from_dict({"detail": 250, "speed": -40, "naturalness": 33.6})
    assert (s.detail, s.speed, s.naturalness) == (100, 0, 34)


def test_all_modes_and_backends_accepted() -> None:
    for mode in MODES:
        assert Settings.from_dict({"mode": mode}).mode == mode
    for backend in BACKENDS:
        assert Settings.from_dict({"backend": backend}).backend == backend


def test_saved_file_is_readable_json(tmp_path: Path) -> None:
    path = tmp_path / "cfg.json"
    Settings(mode=MODE_OUTLINE).save(path)
    assert json.loads(path.read_text(encoding="utf-8"))["mode"] == MODE_OUTLINE


@pytest.mark.parametrize("value", range(0, 101, 5))
def test_derived_values_stay_in_valid_ranges(value: int) -> None:
    s = Settings(detail=value, precision=value, color_tolerance=value, speed=value,
                 smoothing=value, naturalness=value)
    assert s.blur_kernel % 2 == 1
    assert 0 < s.canny_low < s.canny_high <= 255
    assert 2 <= s.levels <= 6
    assert s.hatch_spacing >= 2
    assert s.epsilon > 0
    assert s.step_px > 0 and s.step_delay >= 0
    assert s.pen_delay >= 0.010
    assert 0.0 <= s.smoothing_factor <= 1.0


def test_more_speed_means_bigger_steps_and_shorter_pauses() -> None:
    slow, fast = Settings(speed=10), Settings(speed=90)
    assert fast.step_px > slow.step_px
    assert fast.step_delay < slow.step_delay
    assert fast.pen_delay < slow.pen_delay
