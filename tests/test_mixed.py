from __future__ import annotations

import math
import time
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pytest
from PIL import Image, ImageDraw

from autodraw import mixed
from autodraw.config import MODE_MIXED, MODE_OUTLINE, Settings
from autodraw.image_processing import LoadedImage, load_image
from autodraw.mixed.layers import TINT_ANGLE, _split_at_border, structure_layer, tone_layer
from autodraw.mixed.maps import analyze
from autodraw.path_generation import extract_paths

WHITE = (255, 255, 255)
LINE = (20, 20, 20)


def _load(tmp_path: Path, img: Image.Image, name: str = "img.png") -> LoadedImage:
    path = tmp_path / name
    img.save(path)
    return load_image(path)


def _gray(v: int) -> Tuple[int, int, int]:
    return (v, v, v)


def _segments_in(tone, box) -> List[np.ndarray]:
    """Segmentos de hachura cujo ponto médio cai dentro de `box` (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = box
    out = []
    for _, seg in tone:
        mx, my = seg.mean(axis=0)
        if x0 <= mx <= x1 and y0 <= my <= y1:
            out.append(seg)
    return out


def _ink(segs) -> float:
    return sum(float(np.linalg.norm(s[-1] - s[0])) for s in segs)


def _directions(segs) -> set:
    return {round(math.degrees(math.atan2(*(s[-1] - s[0])[::-1])) % 180 / 15) * 15 % 180 for s in segs}


@pytest.fixture
def patches(tmp_path: Path) -> LoadedImage:
    """Três quadrados contornados: claro, médio e escuro, sobre fundo branco."""
    img = Image.new("RGB", (600, 260), WHITE)
    d = ImageDraw.Draw(img)
    for i, v in enumerate((150, 100, 35)):
        x = 30 + i * 190
        d.rectangle([x, 40, x + 160, 200], fill=_gray(v), outline=LINE, width=3)
    return _load(tmp_path, img)


BOXES = [(40, 50, 180, 190), (230, 50, 370, 190), (420, 50, 560, 190)]


def test_hatch_density_follows_darkness(patches: LoadedImage) -> None:
    settings = Settings(mode=MODE_MIXED, crosshatch=False)
    tone = tone_layer(analyze(patches, settings), settings)
    light, medium, dark = (_ink(_segments_in(tone, b)) for b in BOXES)
    assert 0 < light < medium < dark


def test_crosshatch_only_in_strong_shadows(patches: LoadedImage) -> None:
    settings = Settings(mode=MODE_MIXED, crosshatch=True)
    tone = tone_layer(analyze(patches, settings), settings)
    assert len(_directions(_segments_in(tone, BOXES[1]))) == 1
    assert len(_directions(_segments_in(tone, BOXES[2]))) == 2

    off = Settings(mode=MODE_MIXED, crosshatch=False)
    tone_off = tone_layer(analyze(patches, off), off)
    assert len(_directions(_segments_in(tone_off, BOXES[2]))) == 1


def test_background_and_highlights_stay_clean(tmp_path: Path) -> None:
    img = Image.new("RGB", (400, 300), WHITE)
    d = ImageDraw.Draw(img)
    d.rectangle([50, 50, 350, 250], fill=_gray(40), outline=LINE, width=3)
    d.ellipse([180, 130, 220, 170], fill=WHITE)  # brilho no meio da área escura
    loaded = _load(tmp_path, img)
    settings = Settings(mode=MODE_MIXED)
    tone = tone_layer(analyze(loaded, settings), settings)
    assert tone
    for _, seg in tone:
        # nenhum ponto da hachura no fundo nem no centro do brilho
        for t in np.linspace(0, 1, 20):
            x, y = seg[0] + (seg[-1] - seg[0]) * t
            assert 45 <= x <= 355 and 45 <= y <= 255
            assert math.hypot(x - 200, y - 150) > 12


def test_dark_background_is_not_hatched(tmp_path: Path) -> None:
    img = Image.new("RGB", (400, 300), _gray(15))
    ImageDraw.Draw(img).ellipse([120, 70, 280, 230], fill=_gray(235))
    loaded = _load(tmp_path, img)
    settings = Settings(mode=MODE_MIXED)
    assert tone_layer(analyze(loaded, settings), settings) == []


def test_blush_becomes_light_diagonal_strokes(tmp_path: Path) -> None:
    img = Image.new("RGB", (500, 400), WHITE)
    d = ImageDraw.Draw(img)
    d.ellipse([50, 30, 450, 370], fill=(252, 226, 210), outline=LINE, width=3)  # pele
    d.ellipse([110, 220, 200, 260], fill=(247, 196, 190))                        # blush
    loaded = _load(tmp_path, img)
    settings = Settings(mode=MODE_MIXED)
    maps = analyze(loaded, settings)
    assert maps.tint[240, 155] and not maps.tint[120, 250]

    tone = tone_layer(maps, settings)
    blush = _segments_in(tone, (105, 215, 205, 265))
    assert blush and _directions(blush) == {TINT_ANGLE}
    assert not _segments_in(tone, (220, 80, 420, 200))  # pele lisa continua limpa


def test_fold_on_white_cloth_is_hatched(tmp_path: Path) -> None:
    """Sombra relativa: a dobra é clara em termos absolutos, mas mais escura que o tecido."""
    img = Image.new("RGB", (400, 400), WHITE)
    d = ImageDraw.Draw(img)
    d.rectangle([40, 40, 360, 360], fill=(242, 242, 250), outline=LINE, width=3)
    d.polygon([(150, 60), (185, 60), (230, 340), (190, 340)], fill=(205, 205, 222))
    loaded = _load(tmp_path, img)
    settings = Settings(mode=MODE_MIXED)
    tone = tone_layer(analyze(loaded, settings), settings)
    assert _segments_in(tone, (160, 80, 215, 320))
    assert not _segments_in(tone, (260, 60, 350, 340))


def test_color_boundary_with_same_brightness_is_structure(tmp_path: Path) -> None:
    """Vermelho e verde de mesma luminosidade: só a análise de cor enxerga a divisa."""
    img = Image.new("RGB", (400, 300), (200, 100, 100))
    d = ImageDraw.Draw(img)
    d.rectangle([200, 0, 400, 300], fill=(80, 150, 130))
    d.rectangle([0, 0, 40, 40], fill=(0, 0, 0))            # preto e branco nos cantos
    d.rectangle([360, 260, 400, 300], fill=(255, 255, 255))  # impedem a normalização
    loaded = _load(tmp_path, img)

    def crosses_divide(paths) -> bool:
        return any(np.any((np.abs(p[:, 0] - 200) < 6) & (p[:, 1] > 80) & (p[:, 1] < 220)) for p in paths)

    assert not crosses_divide(extract_paths(loaded, Settings(mode=MODE_OUTLINE)).paths)
    settings = Settings(mode=MODE_MIXED)
    assert crosses_divide(structure_layer(analyze(loaded, settings), settings))


def test_hatch_follows_elongated_shape(tmp_path: Path) -> None:
    img = Image.new("RGB", (500, 500), WHITE)
    band = [(60, 120), (440, 340), (420, 380), (40, 160)]  # faixa a ~30°
    ImageDraw.Draw(img).polygon(band, fill=_gray(90), outline=LINE)
    loaded = _load(tmp_path, img)
    settings = Settings(mode=MODE_MIXED, crosshatch=False)
    tone = tone_layer(analyze(loaded, settings), settings)
    assert _directions([seg for _, seg in tone]) == {30.0}


def test_split_at_border_removes_frame_segments() -> None:
    """Contorno fechado de um personagem cortado pela moldura direita e inferior."""
    pts = np.array([[5, 5], [50, 5], [99, 5], [99, 50], [99, 99], [50, 99], [5, 99], [5, 50], [5, 5]],
                   np.float32)
    parts = _split_at_border(pts, 100, 100)
    assert len(parts) == 1  # o trecho que passa pelo início do array continua inteiro
    assert parts[0].tolist() == [[5, 50], [5, 5], [50, 5]]


def test_structure_is_drawn_before_tone(sample_image: LoadedImage, monkeypatch: pytest.MonkeyPatch) -> None:
    a = [np.array([[10, 10], [60, 10]], np.float32), np.array([[10, 50], [60, 50]], np.float32)]
    b = [np.array([[0, 0], [5, 0]], np.float32), np.array([[70, 70], [90, 70]], np.float32)]
    monkeypatch.setattr(mixed, "mixed_layers", lambda image, settings: [a, b])
    drawing = extract_paths(sample_image, Settings(mode=MODE_MIXED))
    first = {tuple(map(tuple, p)) for p in drawing.paths[:2]}
    expected = {tuple(map(tuple, p)) for p in a} | {tuple(map(tuple, p[::-1])) for p in a}
    assert first <= expected


def test_budget_keeps_structure_then_darkest_tone(patches: LoadedImage) -> None:
    settings = Settings(mode=MODE_MIXED)
    structure, tone = mixed.mixed_layers(patches, settings)
    budget = len(structure) + 5
    limited = mixed.mixed_layers(patches, Settings(mode=MODE_MIXED, max_paths=budget))
    assert len(limited[0]) == len(structure)
    assert len(limited[1]) == 5
    assert all(410 <= seg.mean(axis=0)[0] <= 570 for seg in limited[1])  # só o quadrado escuro


def test_deterministic_and_fast(tmp_path: Path) -> None:
    rng = np.random.default_rng(3)
    arr = rng.integers(0, 255, (900, 700, 3), dtype=np.uint8)
    loaded = _load(tmp_path, Image.fromarray(arr).resize((700, 900)))
    settings = Settings(mode=MODE_MIXED, detail=100, shading=100)
    start = time.perf_counter()
    first = extract_paths(loaded, settings)
    assert time.perf_counter() - start < 5.0
    assert first.stroke_count <= settings.max_paths
    assert extract_paths(loaded, settings).stroke_count == first.stroke_count
