"""
Conversão da imagem em trajetórias (polilinhas) e otimização da ordem de traçado.

Um *traço* é um `numpy.ndarray` de forma (N, 2) com coordenadas (x, y).
Enquanto estão aqui, as coordenadas vivem no espaço da imagem de trabalho;
:func:`fit_to_rect` as converte para pixels de tela dentro da área escolhida.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

from .centerline import line_art_paths
from .config import MODE_HATCH, MODE_LEVELS, MODE_LINES, MODE_MIXED, Settings
from .image_processing import LoadedImage, edge_mask, prepare_gray, prepare_lines, tone_masks

Path = np.ndarray


@dataclass
class Drawing:
    """Conjunto de traços em coordenadas da imagem de trabalho."""

    paths: List[Path]
    width: int
    height: int

    @property
    def point_count(self) -> int:
        return int(sum(len(p) for p in self.paths))

    @property
    def stroke_count(self) -> int:
        return len(self.paths)


# ----------------------------------------------------------------------
# Extração
# ----------------------------------------------------------------------

def extract_paths(image: LoadedImage, settings: Settings) -> Drawing:
    """Gera as trajetórias de acordo com o modo escolhido.

    Um modo pode devolver várias camadas; elas são desenhadas em sequência
    (cada uma com sua própria otimização de percurso) e, se houver traços
    demais, as primeiras camadas têm prioridade.
    """
    gray = prepare_gray(image, settings)
    h, w = gray.shape

    if settings.mode == MODE_MIXED:
        from .mixed import mixed_layers  # import tardio: o modo misto reutiliza este módulo
        layers = mixed_layers(image, settings)
    elif settings.mode == MODE_LINES:
        layers = [line_art_paths(prepare_lines(image, settings), settings)]
    elif settings.mode == MODE_LEVELS:
        layers = [_level_paths(gray, settings)]
    elif settings.mode == MODE_HATCH:
        layers = [_hatch_paths(gray, settings)]
    else:  # contornos
        layers = [_outline_paths(gray, settings)]

    paths: List[Path] = []
    budget = settings.max_paths
    for layer in layers:
        layer = _limit(_simplify(layer, settings), budget)
        budget -= len(layer)
        paths.extend(order_paths(layer, start=paths[-1][-1] if paths else None))

    return Drawing(paths=paths, width=w, height=h)


def _contours_to_paths(mask: np.ndarray, settings: Settings) -> List[Path]:
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    out: List[Path] = []
    min_pts = settings.min_contour_points
    min_len = settings.min_contour_length
    for c in contours:
        pts = c.reshape(-1, 2).astype(np.float32)
        if len(pts) < min_pts:
            continue
        if cv2.arcLength(c, False) < min_len:
            continue
        out.append(pts)
    return out


def _outline_paths(gray: np.ndarray, settings: Settings) -> List[Path]:
    return _contours_to_paths(edge_mask(gray, settings), settings)


def _level_paths(gray: np.ndarray, settings: Settings) -> List[Path]:
    paths: List[Path] = []
    for mask in tone_masks(gray, settings):
        contours, _ = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
        for c in contours:
            pts = c.reshape(-1, 2).astype(np.float32)
            if len(pts) < settings.min_contour_points:
                continue
            if cv2.arcLength(c, True) < settings.min_contour_length:
                continue
            paths.append(np.vstack([pts, pts[:1]]))  # fecha o contorno
    return paths


def _hatch_paths(gray: np.ndarray, settings: Settings) -> List[Path]:
    """Contorno das faixas de tom + hachuras cruzadas nas regiões escuras."""
    paths: List[Path] = _outline_paths(gray, settings)
    masks = tone_masks(gray, settings)
    spacing = max(2, settings.hatch_spacing)
    # As máscaras são cumulativas: um pixel escuro está em todas elas. As faixas
    # alternam +45°/-45° e, dentro da mesma direção, cada faixa desloca suas
    # linhas; assim as regiões escuras recebem hachura cruzada e mais densa em
    # vez de repetir as mesmas linhas.
    per_angle = max(1, (len(masks) + 1) // 2)
    for i, mask in enumerate(masks):
        angle = 45.0 if i % 2 == 0 else -45.0
        offset = ((i // 2) * spacing) // per_angle
        paths.extend(_hatch_mask(mask, spacing, angle, settings.min_contour_length, offset))
    return paths


def _hatch_mask(mask: np.ndarray, spacing: int, angle: float, min_len: float,
                offset: int = 0) -> List[Path]:
    """Corta a máscara com linhas paralelas e devolve os segmentos internos."""
    h, w = mask.shape
    diag = int(np.hypot(h, w)) + 2
    m = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle, 1.0)
    m[0, 2] += (diag - w) / 2.0
    m[1, 2] += (diag - h) / 2.0
    rotated = cv2.warpAffine(mask, m, (diag, diag), flags=cv2.INTER_NEAREST, borderValue=0)
    inv = cv2.invertAffineTransform(m)

    segments: List[Path] = []
    spacing = max(2, spacing)
    for y in range(offset, diag, spacing):
        row = rotated[y]
        idx = np.flatnonzero(row)
        if idx.size == 0:
            continue
        breaks = np.flatnonzero(np.diff(idx) > 1)
        starts = np.concatenate(([0], breaks + 1))
        ends = np.concatenate((breaks, [idx.size - 1]))
        # A direção de cada segmento é decidida depois, por order_paths.
        for s, e in zip(starts, ends):
            x0, x1 = float(idx[s]), float(idx[e])
            if x1 - x0 < max(2.0, min_len * 0.25):
                continue
            p0 = inv @ np.array([x0, y, 1.0])
            p1 = inv @ np.array([x1, y, 1.0])
            segments.append(np.array([p0, p1], dtype=np.float32))
    return segments


def _simplify(paths: Sequence[Path], settings: Settings) -> List[Path]:
    """Reduz o número de pontos preservando o formato (Douglas-Peucker)."""
    eps = settings.epsilon
    out: List[Path] = []
    for p in paths:
        if len(p) <= 2:
            out.append(np.asarray(p, dtype=np.float32))
            continue
        approx = cv2.approxPolyDP(p.astype(np.float32), eps, False).reshape(-1, 2)
        if len(approx) < 2:
            continue
        out.append(approx.astype(np.float32))
    return out


def _limit(paths: List[Path], max_paths: int) -> List[Path]:
    """Mantém apenas os traços mais longos quando há excesso."""
    if len(paths) <= max_paths:
        return paths
    lengths = [float(np.sum(np.linalg.norm(np.diff(p, axis=0), axis=1))) if len(p) > 1 else 0.0
               for p in paths]
    keep = np.argsort(lengths)[::-1][:max_paths]
    keep.sort()
    return [paths[i] for i in keep]


# ----------------------------------------------------------------------
# Otimização da ordem (menor deslocamento com a "caneta" levantada)
# ----------------------------------------------------------------------

def order_paths(paths: Sequence[Path], start: Optional[np.ndarray] = None) -> List[Path]:
    """Ordena os traços pelo vizinho mais próximo, invertendo quando compensa.

    Implementação vetorizada: a cada passo compara a posição atual (de início,
    `start` ou a origem) com os dois extremos de todos os traços restantes.
    """
    n = len(paths)
    if n <= 2:
        return list(paths)

    starts = np.array([p[0] for p in paths], dtype=np.float32)
    ends = np.array([p[-1] for p in paths], dtype=np.float32)
    used = np.zeros(n, dtype=bool)

    ordered: List[Path] = []
    current = np.zeros(2, dtype=np.float32) if start is None else np.asarray(start, dtype=np.float32)
    big = np.float32(np.inf)

    for _ in range(n):
        d_start = np.linalg.norm(starts - current, axis=1)
        d_end = np.linalg.norm(ends - current, axis=1)
        d_start[used] = big
        d_end[used] = big
        i_start = int(np.argmin(d_start))
        i_end = int(np.argmin(d_end))
        if d_start[i_start] <= d_end[i_end]:
            idx, reverse = i_start, False
        else:
            idx, reverse = i_end, True
        used[idx] = True
        path = paths[idx][::-1] if reverse else paths[idx]
        ordered.append(np.ascontiguousarray(path))
        current = np.asarray(path[-1], dtype=np.float32)

    return ordered


# ----------------------------------------------------------------------
# Mapeamento para a área da tela
# ----------------------------------------------------------------------

@dataclass
class FittedDrawing:
    """Traços já convertidos para pixels de tela, prontos para o mouse."""

    paths: List[Path]
    rect: Tuple[int, int, int, int]   # área efetivamente ocupada (x, y, w, h)
    scale: float

    @property
    def stroke_count(self) -> int:
        return len(self.paths)


def fit_rect(src_w: int, src_h: int, area: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
    """Encaixa (src_w, src_h) dentro de `area` preservando a proporção."""
    ax, ay, aw, ah = area
    if src_w <= 0 or src_h <= 0 or aw <= 0 or ah <= 0:
        return ax, ay, 0, 0
    scale = min(aw / src_w, ah / src_h)
    w = src_w * scale
    h = src_h * scale
    x = ax + (aw - w) / 2.0
    y = ay + (ah - h) / 2.0
    return int(round(x)), int(round(y)), int(round(w)), int(round(h))


def fit_to_rect(drawing: Drawing, area: Tuple[int, int, int, int],
                min_segment_px: float = 0.0) -> FittedDrawing:
    """Converte os traços para coordenadas de tela dentro da área escolhida.

    A proporção da imagem é sempre preservada; sobras são distribuídas
    igualmente nas laterais. Traços que ficarem menores que `min_segment_px`
    após a escala são descartados, evitando cliques inúteis.
    """
    x, y, w, h = fit_rect(drawing.width, drawing.height, area)
    if w == 0 or h == 0 or not drawing.paths:
        return FittedDrawing(paths=[], rect=(x, y, w, h), scale=0.0)

    scale = w / drawing.width
    out: List[Path] = []
    for p in drawing.paths:
        q = p * scale + np.array([x, y], dtype=np.float32)
        # Clipping defensivo: nada pode sair da área desenhável.
        q[:, 0] = np.clip(q[:, 0], x, x + w - 1)
        q[:, 1] = np.clip(q[:, 1], y, y + h - 1)
        q = _dedupe(q)
        if len(q) < 2:
            continue
        if min_segment_px > 0:
            span = float(np.sum(np.linalg.norm(np.diff(q, axis=0), axis=1)))
            if span < min_segment_px:
                continue
        out.append(q.astype(np.float32))

    return FittedDrawing(paths=out, rect=(x, y, w, h), scale=scale)


def _dedupe(points: np.ndarray, tol: float = 0.75) -> np.ndarray:
    """Remove pontos consecutivos praticamente idênticos."""
    if len(points) < 2:
        return points
    keep = [0]
    last = points[0]
    for i in range(1, len(points)):
        if float(np.linalg.norm(points[i] - last)) >= tol:
            keep.append(i)
            last = points[i]
    if keep[-1] != len(points) - 1:
        keep.append(len(points) - 1)
    return points[keep]
