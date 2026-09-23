"""
Referência do pós-processamento no AutoDraw: imagem de linhas -> traços.

    limiar -> remove sujeira -> esqueleto de 1 px -> percorre em traços longos
           -> simplifica (Douglas-Peucker) -> descarta traços curtos

Por que linha central: detectar bordas (Canny) numa linha de 4 px acha as
duas margens dela, e contornar cada margem ida e volta faz o mouse passar
pela mesma linha 4 vezes. O esqueleto passa uma vez só.

Validado no experimento (docs/integracao-autodraw.md): limiar 220 preservou
olhos e detalhes; 170 perdia linhas cinza-claras que o modelo gera.

Requer: pip install opencv-python-headless scikit-image   (ou o extra [examples])
Uso direto: python linhas_para_tracos.py <linhas.png> [<previa.png>]
"""

from __future__ import annotations

import sys

import cv2
import numpy as np
from skimage.morphology import skeletonize

# Vizinhos: os 4 ortogonais primeiro, para não pular pixels numa escada diagonal.
_OFFSETS = ((0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1))


def binarize(lines: np.ndarray, threshold: int = 220, min_area: int = 12) -> np.ndarray:
    """Pixels de linha (mais escuros que `threshold`), sem manchas menores que `min_area`."""
    mask = (lines < threshold).astype(np.uint8)
    count, comp, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    keep = np.zeros(count, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_area
    return keep[comp]


def trace_skeleton(skeleton: np.ndarray) -> list[np.ndarray]:
    """Percorre o esqueleto em traços longos, atravessando os cruzamentos.

    Começa pelas pontas (pixels com um vizinho) e segue enquanto houver vizinho
    não visitado; o que sobrar (laços fechados) é percorrido depois. Passar
    direto pelos cruzamentos em vez de parar neles reduz as vezes em que a
    caneta sobe, que é o que mais pesa no tempo de desenho.
    """
    h, w = skeleton.shape
    sk = skeleton.astype(np.uint8)
    degree = cv2.filter2D(sk, -1, np.ones((3, 3), np.float32), borderType=cv2.BORDER_CONSTANT) - sk
    visited = np.zeros_like(skeleton, dtype=bool)
    ys, xs = np.nonzero(skeleton)
    ends = [(y, x) for y, x in zip(ys, xs, strict=True) if degree[y, x] == 1]
    paths = []
    for y0, x0 in ends + list(zip(ys, xs, strict=True)):
        if visited[y0, x0]:
            continue
        y, x = y0, x0
        visited[y, x] = True
        path = [(x, y)]
        while True:
            for dy, dx in _OFFSETS:
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and skeleton[ny, nx] and not visited[ny, nx]:
                    y, x = ny, nx
                    visited[y, x] = True
                    path.append((x, y))
                    break
            else:
                break
        if len(path) >= 2:
            paths.append(np.array(path, np.float32))
    return paths


def path_length(path: np.ndarray) -> float:
    return float(np.sum(np.linalg.norm(np.diff(path, axis=0), axis=1))) if len(path) > 1 else 0.0


def lines_to_strokes(lines: np.ndarray, threshold: int = 220, min_area: int = 12,
                     epsilon: float = 1.7, min_length: float = 22.0) -> list[np.ndarray]:
    """Imagem de linhas (uint8, fundo claro) -> lista de polilinhas (N, 2) em (x, y).

    `epsilon` e `min_length` usam os valores que o AutoDraw deriva dos ajustes
    padrão (Precisão 55 e Detalhes 55, na imagem de trabalho de até 900 px).
    No AutoDraw, passe `settings.epsilon` e `settings.min_contour_length`.
    O traço mínimo pesa muito no tempo: cada traço custa duas pausas de caneta.
    """
    skeleton = skeletonize(binarize(lines, threshold, min_area))
    strokes = []
    for path in trace_skeleton(skeleton):
        simple = cv2.approxPolyDP(path.reshape(-1, 1, 2), epsilon, False).reshape(-1, 2)
        if len(simple) >= 2 and path_length(simple) >= min_length:
            strokes.append(simple.astype(np.float32))
    return strokes


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    image = cv2.imread(sys.argv[1], cv2.IMREAD_GRAYSCALE)
    if image is None:
        sys.exit(f"não foi possível ler {sys.argv[1]}")
    strokes = lines_to_strokes(image)
    ink = sum(path_length(s) for s in strokes)
    print(f"{len(strokes)} traços, {ink:.0f} px de tinta")
    if len(sys.argv) == 3:
        preview = np.full(image.shape, 255, np.uint8)
        cv2.polylines(preview, [s.astype(np.int32) for s in strokes], False, 0, 1)
        cv2.imwrite(sys.argv[2], preview)
