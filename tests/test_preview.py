from __future__ import annotations

import numpy as np

from autodraw.config import Settings
from autodraw.image_processing import LoadedImage
from autodraw.path_generation import FittedDrawing, extract_paths, fit_to_rect
from autodraw.preview import BACKGROUND, STROKE, render_paths, thumbnail


def _stroke_pixels(img) -> int:
    arr = np.asarray(img)
    return int(np.all(arr == STROKE, axis=2).sum())


def test_empty_preview_has_box_size() -> None:
    img = render_paths(None, None, (300, 200), "nada")
    assert img.size == (300, 200)


def test_preview_draws_fitted_strokes(sample_image: LoadedImage) -> None:
    area = (500, 300, 800, 400)
    fitted = fit_to_rect(extract_paths(sample_image, Settings()), area)
    img = render_paths(fitted, area, (430, 300))
    assert _stroke_pixels(img) > 50


def test_preview_shows_only_what_will_be_drawn() -> None:
    area = (0, 0, 100, 100)
    kept = np.array([[10, 10], [90, 10]], np.float32)
    fitted = FittedDrawing(paths=[kept], rect=area, scale=1.0)
    img = np.asarray(render_paths(fitted, area, (120, 120)))
    # só a linha horizontal perto do topo; a metade de baixo fica vazia
    assert np.all(img[70:105, 20:100] == BACKGROUND)


def test_thumbnail_fits_box(sample_image: LoadedImage) -> None:
    thumb = thumbnail(sample_image.pil, (120, 80))
    assert thumb.size == (120, 80)
