"""
Análise da imagem para o modo misto.

Transforma a imagem de trabalho nos mapas intermediários que orientam as
decisões de traçado: luminância, cor (Lab), bordas estruturais, regiões de
cor, fundo, sombra, brilho e variações sutis de cor.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from ..config import Settings
from ..image_processing import LoadedImage

# Pesos Rec. 709 para a luminância.
LUMA_WEIGHTS = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)

# Brilho: precisa superar a vizinhança por esta margem e ser claro de fato.
HIGHLIGHT_CONTRAST = 0.10
HIGHLIGHT_MIN_LUMA = 0.72

# Variação sutil de cor (blush, reflexo colorido): distância mínima em a*/b*
# entre a região e a região que a envolve.
TINT_MIN_DELTA = 8.0
TINT_ENCLOSURE = 0.7  # fração do entorno que precisa pertencer a uma única região

# Bordas "fortes" (line art, grandes saltos de luz) que delimitam as regiões da
# sombra relativa. Limiares sobre o gradiente do Canny (L2) no canal L*.
STRONG_EDGE_LOW = 200
STRONG_EDGE_HIGH = 400

# Pixels usados para ajustar o k-means (o resto só é atribuído ao centro mais próximo).
MAX_KMEANS_SAMPLES = 40_000

# Fundo: a cor dominante da borda precisa ocupar esta fração dela.
BACKGROUND_BORDER_SHARE = 0.6


@dataclass
class ImageMaps:
    luminance: np.ndarray   # float32 0-1 (Rec. 709) da imagem suavizada
    lab: np.ndarray         # float32: L* 0-100, a*/b* com sinal
    edges: np.ndarray       # uint8 0/255: bordas estruturais (de luz ou de cor)
    labels: np.ndarray      # int32: grupo de cor de cada pixel
    background: np.ndarray  # bool: fundo liso ligado à borda da imagem
    shadow: np.ndarray      # float32 0-1: 0 = iluminação máxima, 1 = sombra intensa
    relief: np.ndarray      # float32 0-1: quanto o pixel é mais escuro que sua região
    light: np.ndarray       # bool: brilhos que não devem receber hachura
    tint: np.ndarray        # bool: variação sutil de cor numa área clara
    grad_x: np.ndarray      # gradiente suavizado da luminância (direção da hachura)
    grad_y: np.ndarray


def analyze(image: LoadedImage, settings: Settings) -> ImageMaps:
    rgb = 255 - image.rgb if settings.invert else image.rgb
    smooth = smooth_image(rgb)
    lum = luminance_map(smooth)
    lab = cv2.cvtColor(smooth.astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)
    edges = edge_map(lab, settings)
    labels = color_regions(lab, settings.color_clusters)
    background = background_mask(labels, edges)

    blurred = cv2.GaussianBlur(lum, (0, 0), 2.0)
    return ImageMaps(
        luminance=lum,
        lab=lab,
        edges=edges,
        labels=labels,
        background=background,
        shadow=1.0 - lum,
        relief=relative_shadow(lum, strong_edges(lab) | background, settings),
        light=light_map(lum),
        tint=tint_map(lab, labels, lum, edges, settings),
        grad_x=cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3),
        grad_y=cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3),
    )


# ----------------------------------------------------------------------
# Mapas básicos
# ----------------------------------------------------------------------

def smooth_image(rgb: np.ndarray) -> np.ndarray:
    """Suaviza texturas e ruído de compressão preservando as bordas."""
    return cv2.bilateralFilter(np.ascontiguousarray(rgb), d=7, sigmaColor=35, sigmaSpace=7)


def luminance_map(rgb: np.ndarray) -> np.ndarray:
    return (rgb.astype(np.float32) @ LUMA_WEIGHTS) / 255.0


def edge_map(lab: np.ndarray, settings: Settings) -> np.ndarray:
    """Bordas de luminosidade e de cor.

    O Canny roda também nos canais a*/b*, então duas cores de mesma
    luminosidade (rosa e vermelho, por exemplo) ainda ficam separadas. Como a
    imagem já foi suavizada, gradientes suaves de iluminação não passam do
    limiar e ficam para a hachura.
    """
    lightness, a, b = cv2.split(lab)
    channels = (lightness * 2.55, a * 1.5 + 128.0, b * 1.5 + 128.0)
    edges = np.zeros(lightness.shape, np.uint8)
    for channel in channels:
        u8 = np.clip(channel, 0, 255).astype(np.uint8)
        edges |= cv2.Canny(u8, settings.canny_low, settings.canny_high, L2gradient=True)
    return cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((2, 2), np.uint8))


def color_regions(lab: np.ndarray, k: int) -> np.ndarray:
    """Agrupa cores próximas (k-means em Lab) para que tons contínuos virem uma região só."""
    h, w = lab.shape[:2]
    pixels = lab.reshape(-1, 3).astype(np.float32)
    if len(pixels) > MAX_KMEANS_SAMPLES:
        idx = np.random.default_rng(0).choice(len(pixels), MAX_KMEANS_SAMPLES, replace=False)
        sample = pixels[idx]
    else:
        sample = pixels
    k = max(2, min(k, len(sample)))
    cv2.setRNGSeed(0)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5)
    _, _, centers = cv2.kmeans(sample, k, None, criteria, 2, cv2.KMEANS_PP_CENTERS)
    dist = ((pixels ** 2).sum(axis=1, keepdims=True) - 2.0 * pixels @ centers.T
            + (centers ** 2).sum(axis=1)[None, :])
    return np.argmin(dist, axis=1).astype(np.int32).reshape(h, w)


def background_mask(labels: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """Fundo liso: a cor dominante da borda, ligada à borda e sem atravessar linhas.

    As bordas funcionam como barreira: uma camisa branca contornada sobre um
    fundo branco não é confundida com o fundo.
    """
    empty = np.zeros(labels.shape, bool)
    border = np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])
    values, counts = np.unique(border, return_counts=True)
    if counts.max() < BACKGROUND_BORDER_SHARE * border.size:
        return empty

    barrier = cv2.dilate(edges, np.ones((3, 3), np.uint8)) > 0
    candidate = ((labels == values[np.argmax(counts)]) & ~barrier).astype(np.uint8)
    _, comp = cv2.connectedComponents(candidate, connectivity=4)
    touching = np.unique(np.concatenate([comp[0], comp[-1], comp[:, 0], comp[:, -1]]))
    touching = touching[touching != 0]
    background = np.isin(comp, touching)
    if not 0.05 <= background.mean() <= 0.9:
        return empty
    return background


def strong_edges(lab: np.ndarray) -> np.ndarray:
    """Só as bordas marcantes: linhas do desenho e grandes saltos de luminosidade.

    A borda de uma sombra "cel" (típica de anime) não entra aqui: ela separa a
    sombra da área iluminada, e é justamente essa comparação que interessa.
    """
    u8 = np.clip(lab[..., 0] * 2.55, 0, 255).astype(np.uint8)
    return cv2.Canny(u8, STRONG_EDGE_LOW, STRONG_EDGE_HIGH, L2gradient=True) > 0


def relative_shadow(lum: np.ndarray, barriers: np.ndarray, settings: Settings) -> np.ndarray:
    """Sombra relativa: quanto cada pixel é mais escuro que a parte clara da sua região.

    As regiões são as áreas cercadas por `barriers` (bordas fortes e fundo).
    Assim a dobra de uma camisa branca ou a sombra da franja sobre a pele,
    claras em termos absolutos, ainda contam como sombra, enquanto uma área
    uniformemente escura não vira "sombra de si mesma".
    """
    out = np.zeros(lum.shape, np.float32)
    free = (cv2.dilate(barriers.astype(np.uint8), np.ones((3, 3), np.uint8)) == 0).astype(np.uint8)
    count, seg, stats, _ = cv2.connectedComponentsWithStats(free, connectivity=4)
    h, w = lum.shape
    for i in range(1, count):
        x, y, bw, bh, area = stats[i]
        if area < 4 * settings.min_region_area:
            continue
        ys, xs = slice(y, y + bh), slice(x, x + bw)
        region = seg[ys, xs] == i
        values = lum[ys, xs][region]
        base = float(np.percentile(values, 90))
        out[ys, xs][region] = np.maximum(0.0, base - values)
    return out


def light_map(lum: np.ndarray) -> np.ndarray:
    """Brilhos: pontos bem mais claros que a vizinhança (reflexos, olhos, cabelo)."""
    sigma = max(lum.shape) / 60.0
    local = lum - cv2.GaussianBlur(lum, (0, 0), sigma)
    mask = ((local > HIGHLIGHT_CONTRAST) & (lum > HIGHLIGHT_MIN_LUMA)).astype(np.uint8)
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8)).astype(bool)


def tint_map(lab: np.ndarray, labels: np.ndarray, lum: np.ndarray, edges: np.ndarray,
             settings: Settings) -> np.ndarray:
    """Regiões claras cuja cor difere da região que as envolve (blush, por exemplo).

    Sem isso, uma bochecha rosada sobre pele clara não teria sombra suficiente
    para receber hachura e desapareceria. Só conta quando a região está
    cercada quase toda por uma única região também clara.
    """
    out = np.zeros(labels.shape, bool)
    light_enough = (1.0 - lum) < settings.shadow_threshold
    total = labels.size
    # O anel de comparação começa alguns pixels depois da borda, pulando a faixa
    # de transição (antisserrilhado) que o k-means espalha por outros grupos.
    gap, pad = 3, 9
    inner = np.ones((2 * gap + 1, 2 * gap + 1), np.uint8)
    outer = np.ones((2 * pad + 1, 2 * pad + 1), np.uint8)
    h, w = labels.shape

    for k in np.unique(labels):
        n, comp, stats, _ = cv2.connectedComponentsWithStats((labels == k).astype(np.uint8), connectivity=8)
        for i in range(1, n):
            x, y, bw, bh, area = stats[i]
            if area < settings.min_region_area or area > 0.25 * total:
                continue
            ys = slice(max(0, y - pad), min(h, y + bh + pad))
            xs = slice(max(0, x - pad), min(w, x + bw + pad))
            region = comp[ys, xs] == i
            if light_enough[ys, xs][region].mean() < 0.5:
                continue
            region_u8 = region.astype(np.uint8)
            ring = ((cv2.dilate(region_u8, outer) > 0) & ~(cv2.dilate(region_u8, inner) > 0)
                    & (edges[ys, xs] == 0))
            if not ring.any():
                continue
            ring_labels = labels[ys, xs][ring]
            counts = np.bincount(ring_labels)
            neighbor = int(np.argmax(counts))
            if counts[neighbor] < TINT_ENCLOSURE * ring_labels.size:
                continue
            around = ring & (labels[ys, xs] == neighbor)
            if light_enough[ys, xs][around].mean() < 0.5:
                continue
            a_crop, b_crop = lab[ys, xs, 1], lab[ys, xs, 2]
            delta = math.hypot(float(a_crop[region].mean() - a_crop[around].mean()),
                               float(b_crop[region].mean() - b_crop[around].mean()))
            if delta >= TINT_MIN_DELTA:
                out[ys, xs] |= region
    return out
