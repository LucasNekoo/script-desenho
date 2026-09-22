from __future__ import annotations

import numpy as np
import pytest

from autodraw.config import MODE_HATCH, MODES, Settings
from autodraw.image_processing import LoadedImage
from autodraw.path_generation import Drawing, _limit, extract_paths, fit_rect, fit_to_rect, order_paths


def _travel(paths) -> float:
    """Distância percorrida com a caneta levantada."""
    cursor = np.zeros(2, dtype=np.float32)
    total = 0.0
    for p in paths:
        total += float(np.linalg.norm(p[0] - cursor))
        cursor = p[-1]
    return total


def _key(p: np.ndarray):
    """Identifica um traço independentemente do sentido."""
    a = tuple(map(tuple, np.round(p, 3)))
    return min(a, a[::-1])


# ----------------------------------------------------------------------
# fit_rect / fit_to_rect
# ----------------------------------------------------------------------

@pytest.mark.parametrize("src,area", [
    ((400, 200), (0, 0, 800, 800)),
    ((200, 400), (100, 50, 800, 300)),
    ((300, 300), (10, 10, 50, 500)),
])
def test_fit_rect_preserves_aspect_and_centers(src, area) -> None:
    x, y, w, h = fit_rect(*src, area)
    ax, ay, aw, ah = area
    assert abs(w / h - src[0] / src[1]) < 0.02
    assert ax <= x and ay <= y and x + w <= ax + aw and y + h <= ay + ah
    assert abs((x - ax) - (ax + aw - x - w)) <= 1
    assert abs((y - ay) - (ay + ah - y - h)) <= 1
    assert w == aw or h == ah  # ocupa todo um dos lados


def test_fit_rect_degenerate() -> None:
    assert fit_rect(0, 10, (5, 5, 100, 100)) == (5, 5, 0, 0)
    assert fit_rect(10, 10, (5, 5, 0, 100)) == (5, 5, 0, 0)


def test_fitted_points_never_leave_the_area(sample_image: LoadedImage) -> None:
    drawing = extract_paths(sample_image, Settings())
    rng = np.random.default_rng(0)
    for _ in range(20):
        area = (int(rng.integers(-500, 2000)), int(rng.integers(0, 1000)),
                int(rng.integers(30, 1500)), int(rng.integers(30, 900)))
        fitted = fit_to_rect(drawing, area, min_segment_px=4)
        ax, ay, aw, ah = area
        for p in fitted.paths:
            assert p[:, 0].min() >= ax and p[:, 0].max() <= ax + aw - 1
            assert p[:, 1].min() >= ay and p[:, 1].max() <= ay + ah - 1


def test_fit_to_rect_drops_tiny_strokes() -> None:
    drawing = Drawing(paths=[np.array([[0, 0], [1, 0]], np.float32),
                             np.array([[0, 10], [90, 10]], np.float32)],
                      width=100, height=100)
    fitted = fit_to_rect(drawing, (0, 0, 100, 100), min_segment_px=5)
    assert fitted.stroke_count == 1


# ----------------------------------------------------------------------
# order_paths / _limit
# ----------------------------------------------------------------------

def test_order_paths_is_a_permutation_and_reduces_travel() -> None:
    rng = np.random.default_rng(1)
    paths = [rng.uniform(0, 1000, size=(int(rng.integers(2, 6)), 2)).astype(np.float32)
             for _ in range(80)]
    ordered = order_paths(paths)
    assert sorted(map(_key, ordered)) == sorted(map(_key, paths))
    assert _travel(ordered) < _travel(paths)


def test_order_paths_reverses_when_end_is_closer() -> None:
    a = np.array([[0, 0], [10, 0]], np.float32)
    b = np.array([[100, 0], [11, 0]], np.float32)  # termina perto de onde `a` acaba
    c = np.array([[500, 500], [510, 500]], np.float32)
    ordered = order_paths([c, b, a])
    assert np.array_equal(ordered[0], a)
    assert np.array_equal(ordered[1], b[::-1])


def test_limit_keeps_longest() -> None:
    paths = [np.array([[0, 0], [n, 0]], np.float32) for n in (5, 50, 1, 20)]
    kept = _limit(paths, 2)
    assert sorted(float(p[1, 0]) for p in kept) == [20.0, 50.0]


# ----------------------------------------------------------------------
# extract_paths
# ----------------------------------------------------------------------

@pytest.mark.parametrize("mode", MODES)
def test_every_mode_produces_paths_inside_the_image(sample_image: LoadedImage, mode: str) -> None:
    drawing = extract_paths(sample_image, Settings(mode=mode))
    assert drawing.stroke_count > 0
    for p in drawing.paths:
        assert p.ndim == 2 and p.shape[1] == 2 and len(p) >= 2
        assert p[:, 0].min() >= -1 and p[:, 0].max() <= drawing.width + 1
        assert p[:, 1].min() >= -1 and p[:, 1].max() <= drawing.height + 1


def test_max_paths_is_respected(sample_image: LoadedImage) -> None:
    drawing = extract_paths(sample_image, Settings(mode=MODE_HATCH, detail=100, max_paths=15))
    assert drawing.stroke_count <= 15


def test_hatch_does_not_repeat_segments(sample_image: LoadedImage) -> None:
    """As faixas de tom são cumulativas; nenhuma linha pode ser desenhada duas vezes."""
    drawing = extract_paths(sample_image, Settings(mode=MODE_HATCH, color_tolerance=0))
    segments = [_key(p) for p in drawing.paths if len(p) == 2]
    assert len(segments) > 10
    assert len(segments) == len(set(segments))


def test_invert_changes_hatching(sample_image: LoadedImage) -> None:
    normal = extract_paths(sample_image, Settings(mode=MODE_HATCH))
    inverted = extract_paths(sample_image, Settings(mode=MODE_HATCH, invert=True))
    assert normal.stroke_count != inverted.stroke_count
