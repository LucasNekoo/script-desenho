from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from autodraw import centerline as C
from autodraw.config import MODE_LINES, MODE_OUTLINE, Settings
from autodraw.image_processing import load_image
from autodraw.path_generation import extract_paths

SETTINGS = Settings(mode=MODE_LINES)


def _canvas(h: int = 240, w: int = 320) -> np.ndarray:
    return np.full((h, w), 255, np.uint8)


def _ink(paths) -> float:
    return sum(C._length(p) for p in paths)


def _cross(thickness: int) -> np.ndarray:
    im = _canvas()
    cv2.line(im, (40, 120), (280, 120), 0, thickness)
    cv2.line(im, (160, 20), (160, 220), 0, thickness)
    return im


# ----------------------------------------------------------------------
# Cada linha uma vez, com o mínimo de traços (caminhos de Euler)
# ----------------------------------------------------------------------

@pytest.mark.parametrize("thickness", [1, 3, 5, 8])
def test_thick_line_is_one_stroke_drawn_once(thickness: int) -> None:
    im = _canvas()
    cv2.line(im, (40, 120), (280, 120), 0, thickness)
    paths = C.line_art_paths(im, SETTINGS)
    assert len(paths) == 1
    assert 220 <= _ink(paths) <= 245


@pytest.mark.parametrize("thickness", [1, 3, 5])
def test_cross_needs_exactly_two_strokes(thickness: int) -> None:
    """4 pontas soltas = 4 nós ímpares = 2 traços; nenhum trecho repetido."""
    paths = C.line_art_paths(_cross(thickness), SETTINGS)
    assert len(paths) == 2
    assert 410 <= _ink(paths) <= 445


def test_tic_tac_toe_needs_four_strokes() -> None:
    im = _canvas()
    for k in (110, 210):
        cv2.line(im, (k, 20), (k, 220), 0, 3)
    for k in (80, 160):
        cv2.line(im, (40, k), (280, k), 0, 3)
    paths = C.line_art_paths(im, SETTINGS)
    assert len(paths) == 4
    assert 830 <= _ink(paths) <= 890


def test_figure_eight_is_a_single_stroke() -> None:
    """O cruzamento do "8" tem grau 4 (par): dá para desenhar sem levantar a caneta."""
    im = _canvas()
    cv2.circle(im, (160, 75), 50, 0, 3)
    cv2.circle(im, (160, 175), 50, 0, 3)
    paths = C.line_art_paths(im, SETTINGS)
    assert len(paths) == 1
    assert abs(_ink(paths) - 2 * np.pi * 50 * 2) < 0.1 * 2 * np.pi * 50 * 2


def test_isolated_circle_is_one_closed_loop() -> None:
    im = _canvas()
    cv2.circle(im, (160, 120), 80, 0, 3)
    paths = C.line_art_paths(im, SETTINGS)
    assert len(paths) == 1
    assert np.linalg.norm(paths[0][0] - paths[0][-1]) <= 2.0  # fecha


def test_lines_crossing_a_contour_keep_it_whole() -> None:
    """Mechas cruzando o contorno do cabelo não podem abrir buracos nele."""
    im = _canvas()
    cv2.ellipse(im, (160, 200), (130, 150), 0, 180, 360, 0, 4)
    for x in range(60, 270, 20):
        cv2.line(im, (x, 40), (x + 10, 180), 0, 2)
    skeleton = C.thin(im < C.auto_threshold(im))
    covered = np.zeros(im.shape, np.uint8)
    for p in C.line_art_paths(im, SETTINGS):
        cv2.polylines(covered, [p.astype(np.int32)], False, 1, 1)
    near = cv2.dilate(covered, np.ones((5, 5), np.uint8)) > 0
    assert (skeleton & ~near).sum() <= 0.01 * skeleton.sum()


# ----------------------------------------------------------------------
# Manchas, sujeira e limiar
# ----------------------------------------------------------------------

def test_filled_area_gets_its_outline_not_a_spine() -> None:
    im = _canvas()
    cv2.rectangle(im, (100, 60), (220, 180), 0, -1)
    paths = C.line_art_paths(im, SETTINGS)
    assert len(paths) == 1
    assert 440 <= _ink(paths) <= 500  # perímetro 4 × 120, e não o eixo do quadrado


def test_line_attached_to_blob_keeps_both() -> None:
    """Pupila preenchida com o contorno do olho: a mancha ganha contorno, a linha continua linha."""
    im = _canvas()
    cv2.circle(im, (160, 120), 70, 0, 3)
    cv2.circle(im, (160, 120), 25, 0, -1)
    lines, blobs = C.split_lines_and_blobs(C.remove_specks(im < 128, 12), C.LINE_MAX_HALF_WIDTH)
    assert blobs[120, 160] and not blobs[120, 90]
    assert lines[120, 90 - 1 : 90 + 2].any() or lines[50:53, 160].any()


def test_crossing_is_not_mistaken_for_a_blob() -> None:
    """No centro de um "+" a distância à borda passa da meia-espessura da linha."""
    _, blobs = C.split_lines_and_blobs(C.remove_specks(_cross(8) < 128, 12), C.LINE_MAX_HALF_WIDTH)
    assert not blobs.any()


def test_specks_and_blank_images_give_nothing() -> None:
    im = _canvas()
    assert C.line_art_paths(im, SETTINGS) == []
    im[50:52, 50:52] = 0
    im[100:102, 200:203] = 0
    assert C.line_art_paths(im, SETTINGS) == []


def test_short_isolated_scribble_is_dropped() -> None:
    im = _canvas()
    cv2.line(im, (100, 100), (104, 102), 0, 2)
    assert C.line_art_paths(im, SETTINGS) == []


def test_auto_threshold_keeps_light_gray_lines() -> None:
    """As linhas que a IA gera são todas cinza-claras: o limiar automático tem de pegá-las."""
    im = _canvas()
    cv2.line(im, (40, 120), (280, 120), 200, 2)
    cv2.line(im, (40, 60), (280, 60), 190, 2)
    assert C.auto_threshold(im) > 200
    assert len(C.line_art_paths(im, SETTINGS)) == 2


def test_auto_threshold_separates_ink_from_light_gray() -> None:
    """Limitação conhecida: com tinta preta na imagem, cinza-claro conta como fundo."""
    im = _canvas()
    cv2.line(im, (40, 120), (280, 120), 200, 2)
    cv2.line(im, (40, 60), (280, 60), 0, 2)
    assert C.auto_threshold(im) < 200
    assert len(C.line_art_paths(im, SETTINGS)) == 1


def test_explicit_threshold_wins() -> None:
    im = _canvas()
    cv2.line(im, (40, 120), (280, 120), 200, 2)
    assert C.line_art_paths(im, SETTINGS, threshold=170) == []
    assert C.line_art_paths(im, SETTINGS, threshold=220)


# ----------------------------------------------------------------------
# Afinamento
# ----------------------------------------------------------------------

def test_thinning_gives_one_pixel_lines_and_keeps_connectivity() -> None:
    im = _canvas()
    cv2.rectangle(im, (60, 60), (260, 180), 0, 7)
    skeleton = C.thin(im < 128)
    blocks = skeleton[:-1, :-1] & skeleton[1:, :-1] & skeleton[:-1, 1:] & skeleton[1:, 1:]
    assert not blocks.any()  # nenhum quadrado 2×2 cheio: largura de 1 px
    count, _ = cv2.connectedComponents(skeleton.astype(np.uint8), connectivity=8)
    assert count - 1 == 1


# ----------------------------------------------------------------------
# Integração com extract_paths
# ----------------------------------------------------------------------

def test_lines_mode_draws_line_art_with_far_less_ink_than_outline(tmp_path: Path) -> None:
    """O objetivo do modo: numa linha de 5 px, o Canny percorre ~4× mais."""
    im = _canvas(300, 500)
    pts = np.array([[40, 200], [140, 80], [260, 190], [380, 60], [470, 150]], np.int32)
    cv2.polylines(im, [pts], False, 0, 5, cv2.LINE_AA)
    path = tmp_path / "zigue.png"
    Image.fromarray(im).save(path)
    loaded = load_image(path)
    outline = extract_paths(loaded, Settings(mode=MODE_OUTLINE))
    lines = extract_paths(loaded, Settings(mode=MODE_LINES))
    assert lines.stroke_count == 1
    assert _ink(outline.paths) > 3 * _ink(lines.paths)


def test_invert_draws_light_lines_on_dark_background(tmp_path: Path) -> None:
    im = np.full((240, 320), 0, np.uint8)
    cv2.line(im, (40, 120), (280, 120), 255, 3)
    path = tmp_path / "negativo.png"
    Image.fromarray(im).save(path)
    drawing = extract_paths(load_image(path), Settings(mode=MODE_LINES, invert=True))
    assert drawing.stroke_count == 1


def test_fast_enough_on_a_noisy_image(tmp_path: Path) -> None:
    """Uma foto não é o alvo do modo, mas não pode travar a interface."""
    rng = np.random.default_rng(1)
    noisy = (rng.normal(128, 60, (900, 700))).clip(0, 255).astype(np.uint8)
    path = tmp_path / "ruido.png"
    Image.fromarray(noisy).save(path)
    loaded = load_image(path)
    start = time.perf_counter()
    extract_paths(loaded, Settings(mode=MODE_LINES))
    assert time.perf_counter() - start < 3.0
