"""
Traçado pela linha central, para desenhos que já têm linhas (line art).

Detectar bordas (Canny) numa linha de 4 px acha as duas margens dela, e
contornar cada margem ida e volta faz o mouse passar pela mesma linha quatro
vezes. Aqui cada linha é afinada até 1 px (esqueleto) e percorrida uma vez só:

    tons escuros -> separa linhas finas de manchas grossas
                 -> linhas: esqueleto (Zhang-Suen) -> percorre em traços longos
                 -> manchas: só o contorno (o esqueleto de uma mancha seria um
                    risco no meio dela)

Não depende do scikit-image: o afinamento é feito com NumPy.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import cv2
import numpy as np

from .config import Settings

# Faixas escuras com meia-espessura acima disto (px da imagem de trabalho, que
# tem até 900 px) são manchas, não linhas: ganham contorno em vez de esqueleto.
LINE_MAX_HALF_WIDTH = 5.0

# No centro de um cruzamento de linhas com meia-espessura h, a distância até a
# borda chega a h·√2 (o canto do "+"), nunca mais que isso. Uma mancha precisa
# ter algum ponto mais fundo que esse limite.
BLOB_SEED_FACTOR = 2 ** 0.5

# Limiar automático: Otsu empurrado esta fração do caminho até o branco, para
# incluir as bordas cinza (antisserrilhado) e linhas claras.
THRESHOLD_BIAS = 0.35
THRESHOLD_RANGE = (96, 230)

# Limiar para as linhas da extração por IA, que são cinza-claras: 220
# preservou olhos e detalhes nos testes; 170 perdia linhas.
AI_LINES_THRESHOLD = 220

# Manchas menores que isto (px²) são sujeira de compressão.
MIN_COMPONENT_AREA = 12

# Pontas de traços a até esta distância (px) viram um traço só (falhas mínimas
# que o afinamento deixa numa linha).
MERGE_TOLERANCE = 2.5

# Galho com uma ponta solta e comprimento até isto (px) é "espinho" do
# afinamento, não desenho.
SPUR_MAX_LENGTH = 2 * LINE_MAX_HALF_WIDTH

# Vizinhos de um pixel: os 4 ortogonais primeiro.
_OFFSETS = ((0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1))


def line_art_paths(gray: np.ndarray, settings: Settings, threshold: Optional[int] = None) -> List[np.ndarray]:
    """Traços de uma imagem com linhas escuras sobre fundo claro.

    `gray` é uint8 (0 = preto). `threshold` automático se omitido; a extração
    por IA passa o seu (as linhas que o modelo gera são cinza-claras).
    """
    if threshold is None:
        threshold = auto_threshold(gray)
    mask = remove_specks(gray < threshold, MIN_COMPONENT_AREA)
    lines, blobs = split_lines_and_blobs(mask, LINE_MAX_HALF_WIDTH)

    # O mínimo do modo contornos mede o contorno de um risco, que tem o dobro do
    # comprimento dele; aqui se mede o próprio risco.
    min_length = settings.min_contour_length / 2.0
    skeleton = drop_short_components(thin(remove_specks(lines, MIN_COMPONENT_AREA)), min_length)
    paths = merge_touching(trace_skeleton(skeleton), MERGE_TOLERANCE)
    paths += [p for p in _blob_outlines(blobs) if _length(p) >= min_length]
    return paths


def source_lines(image, settings: Settings) -> Optional[np.ndarray]:
    """Imagem de linhas da IA, se a opção estiver ligada e a extração tiver dado certo."""
    if settings.ai_lines and getattr(image, "ai_lines", None) is not None:
        return image.ai_lines
    return None


def auto_threshold(gray: np.ndarray) -> int:
    otsu, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    value = otsu + (255 - otsu) * THRESHOLD_BIAS
    return int(np.clip(value, *THRESHOLD_RANGE))


def remove_specks(mask: np.ndarray, min_area: int) -> np.ndarray:
    count, comp, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    keep = np.zeros(count, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_area
    return keep[comp]


def drop_short_components(skeleton: np.ndarray, min_length: float) -> np.ndarray:
    """Descarta desenhos conectados curtos demais (sujeira), inteiros.

    O filtro vale para o componente todo, e não para cada traço: um trecho
    curto entre dois cruzamentos faz parte de uma linha longa e não pode sumir.
    """
    count, comp, stats, _ = cv2.connectedComponentsWithStats(skeleton.astype(np.uint8), connectivity=8)
    keep = np.zeros(count, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_length  # num esqueleto, pixels ≈ comprimento
    return keep[comp]


def split_lines_and_blobs(mask: np.ndarray, half_width: float) -> Tuple[np.ndarray, np.ndarray]:
    """Separa as partes finas (linhas) das grossas (manchas) pela distância à borda.

    O miolo de uma mancha é a região mais funda que `half_width`, mas só conta
    se tiver algum ponto mais fundo que `half_width`·√2. Assim o centro de um
    cruzamento de linhas não vira mancha.
    """
    mask_u8 = mask.astype(np.uint8)
    dist = cv2.distanceTransform(mask_u8, cv2.DIST_L2, 5)
    deep = dist > half_width
    count, comp = cv2.connectedComponents(deep.astype(np.uint8), connectivity=8)
    seeded = np.zeros(count, bool)
    seeded[np.unique(comp[dist > half_width * BLOB_SEED_FACTOR])] = True
    seeded[0] = False
    core = seeded[comp].astype(np.uint8)
    if not core.any():
        return mask.astype(bool), np.zeros(mask.shape, bool)
    # Reconstrói a mancha inteira a partir do miolo grosso.
    size = int(2 * np.ceil(half_width) + 3)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
    blobs = (cv2.dilate(core, kernel) > 0) & mask
    return mask & ~blobs, blobs


def thin(mask: np.ndarray) -> np.ndarray:
    """Afinamento de Zhang-Suen (1984), vetorizado: esqueleto de 1 px, conectividade 8."""
    img = np.pad(mask.astype(np.uint8), 1)
    while True:
        changed = False
        for step in (0, 1):
            p2, p3, p4 = img[:-2, 1:-1], img[:-2, 2:], img[1:-1, 2:]
            p5, p6, p7 = img[2:, 2:], img[2:, 1:-1], img[2:, :-2]
            p8, p9 = img[1:-1, :-2], img[:-2, :-2]
            ring = (p2, p3, p4, p5, p6, p7, p8, p9, p2)
            neighbors = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9
            transitions = sum(((a == 0) & (b == 1)).astype(np.uint8) for a, b in zip(ring, ring[1:]))
            if step == 0:
                side = (p2 * p4 * p6 == 0) & (p4 * p6 * p8 == 0)
            else:
                side = (p2 * p4 * p8 == 0) & (p2 * p6 * p8 == 0)
            delete = (img[1:-1, 1:-1] == 1) & (neighbors >= 2) & (neighbors <= 6) & (transitions == 1) & side
            if delete.any():
                img[1:-1, 1:-1][delete] = 0
                changed = True
        if not changed:
            return img[1:-1, 1:-1].astype(bool)


def trace_skeleton(skeleton: np.ndarray) -> List[np.ndarray]:
    """Cobre o esqueleto com o menor número de traços, cada trecho uma vez só.

    O esqueleto vira um grafo: pontas e cruzamentos são nós; os trechos entre
    eles, arestas. Cada componente é coberto por caminhos de Euler, o que dá o
    mínimo de levantadas de caneta possível sem repetir trecho: metade do
    número de nós de grau ímpar (ou um traço, se não houver nenhum). Um "#"
    sai em 4 traços; um "8", em 1.
    """
    edges, loops = _skeleton_edges(skeleton)
    edges = _prune_spurs(edges, SPUR_MAX_LENGTH)
    strokes = [_join(trail, closed) for trail, closed in _euler_trails(edges)]
    strokes += [np.array(loop, np.float32) for loop in loops]
    return [s for s in strokes if len(s) >= 2]


def merge_touching(paths: List[np.ndarray], tolerance: float) -> List[np.ndarray]:
    """Junta traços cujas pontas se tocam (falhas mínimas no esqueleto).

    Cada junção economiza uma subida e uma descida da caneta. Um traço nunca é
    juntado consigo mesmo (laços fechados continuam laços).
    """
    alive = [p for p in paths if len(p) >= 2]
    merged = True
    while merged and len(alive) > 1:
        merged = False
        starts = np.array([p[0] for p in alive])
        ends = np.array([p[-1] for p in alive])
        used = np.zeros(len(alive), bool)
        result = []
        for i, path in enumerate(alive):
            if used[i]:
                continue
            used[i] = True
            tail = path[-1]
            d_start = np.linalg.norm(starts - tail, axis=1)
            d_end = np.linalg.norm(ends - tail, axis=1)
            d_start[used] = np.inf
            d_end[used] = np.inf
            j_s, j_e = int(np.argmin(d_start)), int(np.argmin(d_end))
            if min(d_start[j_s], d_end[j_e]) <= tolerance:
                if d_start[j_s] <= d_end[j_e]:
                    j, other = j_s, alive[j_s]
                else:
                    j, other = j_e, alive[j_e][::-1]
                used[j] = True
                path = np.vstack([path, other])
                merged = True
            result.append(path)
        alive = result
    return alive


# ----------------------------------------------------------------------
# Grafo do esqueleto
# ----------------------------------------------------------------------

Pixel = Tuple[int, int]            # (x, y)
Edge = Tuple[int, int, List[Pixel]]  # (nó de origem, nó de destino, pixels de origem a destino)


def _skeleton_edges(skeleton: np.ndarray) -> Tuple[List[Edge], List[List[Pixel]]]:
    """Arestas entre nós (pontas e cruzamentos) e laços sem nó nenhum.

    Nós são pixels com número de vizinhos diferente de 2; pixels de nó
    encostados formam um nó só (o "nó" de um cruzamento costuma ter 2 a 4
    pixels). Os demais pixels têm exatamente dois vizinhos, então o caminho
    entre dois nós é único.
    """
    h, w = skeleton.shape
    sk = skeleton.astype(np.uint8)
    degree = cv2.filter2D(sk, -1, np.ones((3, 3), np.float32), borderType=cv2.BORDER_CONSTANT) - sk
    node_mask = (sk == 1) & (degree != 2)
    _, node_label = cv2.connectedComponents(node_mask.astype(np.uint8), connectivity=8)
    next_node = int(node_label.max()) + 1
    seen = np.zeros(skeleton.shape, bool)  # pixels de trecho já percorridos
    edges: List[Edge] = []
    direct = set()

    def neighbors(y: int, x: int):
        for dy, dx in _OFFSETS:
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and sk[ny, nx]:
                yield ny, nx

    ys, xs = np.nonzero(node_mask)
    for y, x in zip(ys.tolist(), xs.tolist()):
        u = int(node_label[y, x])
        for ny, nx in neighbors(y, x):
            v = int(node_label[ny, nx])
            if v == u:
                continue
            if v > 0:  # dois nós encostados: aresta de um passo
                key = frozenset(((y, x), (ny, nx)))
                if key not in direct:
                    direct.add(key)
                    edges.append((u, v, [(x, y), (nx, ny)]))
                continue
            if seen[ny, nx]:
                continue
            seen[ny, nx] = True
            path = [(x, y), (nx, ny)]
            prev, cur = (y, x), (ny, nx)
            end = None
            while end is None:
                step = None
                for q in neighbors(*cur):
                    if q == prev:
                        continue
                    label = int(node_label[q])
                    if label > 0:
                        step, end = q, label
                        break
                    if not seen[q]:
                        step = q
                if step is None:  # ponta morta inesperada: vira um nó novo
                    end = next_node
                    next_node += 1
                    break
                if end is None:
                    seen[step] = True
                path.append((step[1], step[0]))
                prev, cur = cur, step
            edges.append((u, end, path))

    # O que sobrou são laços fechados sem nenhum nó (um círculo isolado).
    loops: List[List[Pixel]] = []
    for y, x in zip(*np.nonzero((sk == 1) & ~node_mask & ~seen)):
        if seen[y, x]:
            continue
        seen[y, x] = True
        loop = [(int(x), int(y))]
        prev, cur = None, (int(y), int(x))
        while True:
            step = next((q for q in neighbors(*cur) if q != prev and not seen[q]), None)
            if step is None:
                break
            seen[step] = True
            loop.append((step[1], step[0]))
            prev, cur = cur, step
        loop.append(loop[0])
        loops.append(loop)
    return edges, loops


def _prune_spurs(edges: List[Edge], max_length: float) -> List[Edge]:
    """Remove "espinhos": arestas curtas que saem de um cruzamento e acabam soltas."""
    degree: dict = {}
    for u, v, _ in edges:
        degree[u] = degree.get(u, 0) + 1
        degree[v] = degree.get(v, 0) + 1
    kept = []
    for u, v, pixels in edges:
        loose = (degree[u] == 1) + (degree[v] == 1)
        if loose == 1 and max(degree[u], degree[v]) >= 3 and _pixel_length(pixels) <= max_length:
            continue
        kept.append((u, v, pixels))
    return kept


def _euler_trails(edges: List[Edge]) -> List[Tuple[List[List[Pixel]], bool]]:
    """Decompõe o grafo no mínimo de trilhas (Hierholzer com um nó virtual).

    Um nó virtual ligado a todos os nós de grau ímpar deixa todos os graus
    pares; o circuito de Euler resultante, cortado nas arestas virtuais, dá as
    trilhas. Cada aresta real aparece exatamente uma vez. Devolve também se a
    trilha termina no mesmo nó em que começou (precisa ser fechada).
    """
    virtual = -1
    adjacency: dict = {}
    for i, (u, v, _) in enumerate(edges):
        adjacency.setdefault(u, []).append(i)
        adjacency.setdefault(v, []).append(i)
    odd = [n for n, lst in adjacency.items() if len(lst) % 2]
    all_edges = list(edges) + [(virtual, n, None) for n in odd]
    for i in range(len(edges), len(all_edges)):
        adjacency.setdefault(virtual, []).append(i)
        adjacency[all_edges[i][1]].append(i)

    used = [False] * len(all_edges)
    cursor = {n: 0 for n in adjacency}
    trails: List[Tuple[List[List[Pixel]], bool]] = []
    for start in ([virtual] if odd else []) + list(adjacency):
        stack = [(start, -1)]
        circuit = []
        while stack:
            node, arrived_by = stack[-1]
            lst = adjacency[node]
            while cursor[node] < len(lst) and used[lst[cursor[node]]]:
                cursor[node] += 1
            if cursor[node] == len(lst):
                circuit.append(stack.pop())
                continue
            e = lst[cursor[node]]
            used[e] = True
            u, v, _ = all_edges[e]
            stack.append((v if u == node else u, e))
        circuit.reverse()

        trail: List[List[Pixel]] = []
        first = last = None
        for (frm, _), (to, e) in zip(circuit, circuit[1:]):
            u, v, pixels = all_edges[e]
            if pixels is None:  # aresta virtual: aqui a caneta sobe
                if trail:
                    trails.append((trail, first == last))
                trail = []
                continue
            if not trail:
                first = frm
            trail.append(pixels if u == frm else pixels[::-1])
            last = to
        if trail:
            trails.append((trail, first == last))
    return trails


def _join(trail: List[List[Pixel]], closed: bool = False) -> np.ndarray:
    """Emenda as arestas de uma trilha, atravessando o nó entre elas.

    Um nó pode ter alguns pixels; a entrada e a saída nem sempre coincidem. Se
    a trilha volta ao nó de partida, o traço é fechado para não deixar falha.
    """
    points: List[Pixel] = []
    for pixels in trail:
        points.extend(pixels if not points or points[-1] != pixels[0] else pixels[1:])
    if closed and len(points) > 2 and points[-1] != points[0]:
        points.append(points[0])
    return np.array(points, np.float32)


def _pixel_length(pixels: List[Pixel]) -> float:
    return _length(np.array(pixels, np.float32))


def _blob_outlines(blobs: np.ndarray) -> List[np.ndarray]:
    if not blobs.any():
        return []
    contours, _ = cv2.findContours(blobs.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    out = []
    for c in contours:
        pts = c.reshape(-1, 2).astype(np.float32)
        if len(pts) >= 3:
            out.append(np.vstack([pts, pts[:1]]))  # fecha o contorno
    return out


def _length(p: np.ndarray) -> float:
    return float(np.sum(np.linalg.norm(np.diff(p, axis=0), axis=1))) if len(p) > 1 else 0.0
