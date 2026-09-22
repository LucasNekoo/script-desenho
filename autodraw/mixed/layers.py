"""
Camadas do modo misto.

* Estrutura: silhueta e bordas estruturais, desenhadas primeiro.
* Tom: hachura com densidade proporcional à sombra, direção acompanhando a
  forma de cada região e cruzamento só nas sombras mais fortes.

As funções de contorno e de hachura dos outros modos são reaproveitadas.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from ..config import Settings
from ..path_generation import Path, _contours_to_paths, _hatch_mask
from .maps import ImageMaps

# Sombra (0-1) a partir da qual a região ganha a segunda direção de hachura.
CROSSHATCH_SHADOW = 0.75

# Sombra relativa: cada nível extra exige este tanto a mais de escurecimento.
RELATIVE_STEP = 0.10

# Variação sutil de cor (blush): traços curtos diagonais, a convenção do anime.
TINT_ANGLE = 60.0

# Abertura aplicada às máscaras de tom: some com as linhas do desenho original
# (line art de até ~4 px), que já viram contorno e não devem ganhar hachura.
TONE_OPENING = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

# Direções próximas são agrupadas para que regiões vizinhas compartilhem linhas.
ANGLE_STEP = 15.0
DEFAULT_ANGLE = 45.0
# Abaixo desta coerência a região não tem direção dominante (usa DEFAULT_ANGLE).
MIN_COHERENCE = 0.25

SILHOUETTE_BAND = 5  # px ao redor da silhueta onde bordas repetidas são descartadas


# ----------------------------------------------------------------------
# Estrutura
# ----------------------------------------------------------------------

def structure_layer(maps: ImageMaps, settings: Settings) -> List[Path]:
    """Silhueta primeiro, depois as bordas internas da mais longa para a mais curta."""
    silhouette, band = _silhouette(maps, settings)
    edges = maps.edges
    if band is not None:
        edges = edges.copy()
        edges[band > 0] = 0  # a silhueta já cobre essas bordas
    inner = _contours_to_paths(edges, settings)
    inner.sort(key=_length, reverse=True)
    return silhouette + inner


def _silhouette(maps: ImageMaps, settings: Settings) -> Tuple[List[Path], Optional[np.ndarray]]:
    if not maps.background.any():
        return [], None
    fg = (~maps.background).astype(np.uint8) * 255
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    h, w = fg.shape
    band = np.zeros_like(fg)
    paths: List[Path] = []
    for c in contours:
        if cv2.arcLength(c, True) < settings.min_contour_length * 2:
            continue
        cv2.drawContours(band, [c], -1, 255, thickness=SILHOUETTE_BAND)
        pts = c.reshape(-1, 2).astype(np.float32)
        paths.extend(p for p in _split_at_border(np.vstack([pts, pts[:1]]), w, h)
                     if _length(p) >= settings.min_contour_length)
    paths.sort(key=_length, reverse=True)
    return paths, band


def _split_at_border(pts: np.ndarray, w: int, h: int) -> List[Path]:
    """Remove os trechos que correm pela moldura da imagem (personagem cortado)."""
    on_border = ((pts[:, 0] <= 0) | (pts[:, 1] <= 0) | (pts[:, 0] >= w - 1) | (pts[:, 1] >= h - 1))
    if not on_border.any():
        return [pts]
    if len(pts) > 2 and np.array_equal(pts[0], pts[-1]):
        # Contorno fechado: recomeça num ponto da moldura para não partir um
        # trecho que atravessa o fim e o início do array.
        shift = int(np.argmax(on_border[:-1]))
        pts = np.roll(pts[:-1], -shift, axis=0)
        on_border = np.roll(on_border[:-1], -shift)
    out: List[Path] = []
    start = None
    for i, border in enumerate(on_border):
        if not border and start is None:
            start = i
        elif border and start is not None:
            if i - start >= 2:
                out.append(pts[start:i])
            start = None
    if start is not None and len(pts) - start >= 2:
        out.append(pts[start:])
    return out


# ----------------------------------------------------------------------
# Tom
# ----------------------------------------------------------------------

def tone_layer(maps: ImageMaps, settings: Settings) -> List[Tuple[int, Path]]:
    """Hachura adaptativa. Devolve (nível de sombra, segmento); nível maior = mais escuro."""
    n = settings.shadow_levels
    level = shadow_levels(maps, settings)
    clean = ~(maps.background | maps.light)

    # (prioridade, ângulo, espaçamento) -> componentes; as máscaras só são montadas na hora.
    groups: Dict[Tuple[int, float, int], List[Tuple[np.ndarray, int]]] = defaultdict(list)

    tint = (maps.tint & clean & (level <= 1)).astype(np.uint8)
    level[tint > 0] = 0
    count, comp, stats, _ = cv2.connectedComponentsWithStats(tint, connectivity=8)
    tint_spacing = int(round(hatch_spacing((n + 1) // 2, settings)))
    for i in range(1, count):
        if stats[i, cv2.CC_STAT_AREA] >= settings.min_region_area:
            groups[(1, TINT_ANGLE, tint_spacing)].append((comp, i))

    for lvl in range(1, n + 1):
        spacing = int(round(hatch_spacing(lvl, settings)))
        mask = cv2.morphologyEx((level == lvl).astype(np.uint8), cv2.MORPH_OPEN, TONE_OPENING)
        count, comp, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        cross = settings.crosshatch and _level_shadow(lvl, settings) >= CROSSHATCH_SHADOW
        for i in range(1, count):
            if stats[i, cv2.CC_STAT_AREA] < settings.min_region_area:
                continue
            angle = _region_angle(maps, comp, i, stats[i])
            groups[(lvl, angle, spacing)].append((comp, i))
            if cross:
                groups[(lvl, (angle + 90.0) % 180.0, spacing)].append((comp, i))

    out: List[Tuple[int, Path]] = []
    for (priority, angle, spacing), members in groups.items():
        mask = np.zeros(level.shape, np.uint8)
        for comp, i in members:
            mask[comp == i] = 255
        for seg in _hatch_mask(mask, spacing, angle, settings.min_contour_length):
            out.append((priority, seg))
    return out


def shadow_levels(maps: ImageMaps, settings: Settings) -> np.ndarray:
    """Nível de hachura por pixel: 0 = sem hachura, 1 = mais leve ... n = mais densa.

    Vale o maior entre a sombra absoluta (quão escuro é o pixel) e a relativa
    (quão mais escuro ele é que a parte clara da própria região).
    """
    n = settings.shadow_levels
    start = settings.shadow_threshold
    norm = np.clip((maps.shadow - start) / max(1e-6, 1.0 - start), 0.0, 1.0)
    level = np.ceil(norm * n).astype(np.int32)
    relative = np.ceil((maps.relief - settings.relative_shadow_min) / RELATIVE_STEP)
    level = np.maximum(level, np.clip(relative, 0, n).astype(np.int32))
    level[maps.background | maps.light] = 0    # fundo e brilhos ficam limpos
    return level


def hatch_spacing(level: int, settings: Settings) -> float:
    """Espaçamento geométrico: do mais esparso (nível 1) ao mais denso (nível n)."""
    dense, sparse = settings.mixed_spacing
    n = settings.shadow_levels
    t = (level - 1) / max(1, n - 1)
    return sparse * (dense / sparse) ** t


def _level_shadow(level: int, settings: Settings) -> float:
    start = settings.shadow_threshold
    return start + (level - 0.5) / settings.shadow_levels * (1.0 - start)


def _region_angle(maps: ImageMaps, comp: np.ndarray, index: int, stat: np.ndarray) -> float:
    """Direção da hachura pelo tensor de estrutura: as linhas seguem as isofotas.

    Numa faixa de sombra alongada as linhas correm ao longo da faixa; no
    cabelo, acompanham as mechas. Sem direção dominante, usa DEFAULT_ANGLE.
    """
    x, y, w, h = (int(v) for v in stat[:4])
    pad = 6
    H, W = comp.shape
    ys = slice(max(0, y - pad), min(H, y + h + pad))
    xs = slice(max(0, x - pad), min(W, x + w + pad))
    region = (comp[ys, xs] == index).astype(np.uint8)
    zone = cv2.dilate(region, np.ones((2 * pad + 1, 2 * pad + 1), np.uint8)) > 0
    gx = maps.grad_x[ys, xs][zone]
    gy = maps.grad_y[ys, xs][zone]
    jxx, jyy, jxy = float(gx @ gx), float(gy @ gy), float(gx @ gy)
    energy = jxx + jyy
    if energy < 1e-9:
        return DEFAULT_ANGLE
    coherence = math.sqrt((jxx - jyy) ** 2 + 4.0 * jxy ** 2) / energy
    if coherence < MIN_COHERENCE:
        return DEFAULT_ANGLE
    gradient = 0.5 * math.degrees(math.atan2(2.0 * jxy, jxx - jyy))
    return (round((gradient + 90.0) / ANGLE_STEP) * ANGLE_STEP) % 180.0


def _length(p: np.ndarray) -> float:
    return float(np.sum(np.linalg.norm(np.diff(p, axis=0), axis=1))) if len(p) > 1 else 0.0
