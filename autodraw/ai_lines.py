"""
Linhas por IA: localiza o autodraw-lineart e obtém a imagem de linhas.

O resultado (uint8, fundo claro, linhas escuras, mesmo tamanho da imagem de
trabalho) vai para `centerline.line_art_paths`, igual à imagem própria do
modo linhas. Nada aqui importa Tkinter: quem chama é a thread de
regeneração da interface.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image

from .config import Settings
from .image_processing import LoadedImage
from .lineart_client import LineartClient, LineartError

# Fundo escuro (média da moldura abaixo disto, 0-1): o modelo gera ruído.
DARK_BORDER_LUMA = 0.35

# Metade dos núcleos da ferramenta já é o padrão; aqui, no máximo 2, porque o
# jogo e o AutoDraw rodam na mesma máquina.
AI_THREADS = 2

EXECUTABLE = "autodraw-lineart.exe" if sys.platform == "win32" else "autodraw-lineart"


def find_command(settings: Settings) -> Optional[List[str]]:
    """Onde está o autodraw-lineart: configuração → PATH → pastas comuns."""
    configured = settings.lineart_command.strip()
    if configured:
        return [configured] if Path(configured).is_file() else None
    found = shutil.which("autodraw-lineart")
    if found:
        return [found]
    for candidate in _common_locations():
        if candidate.is_file():
            return [str(candidate)]
    return None


def _common_locations() -> List[Path]:
    """Pastas comuns de instalação: o clone do autodraw-lineart com o venv dentro."""
    home = Path.home()
    bases = [home / "autodraw-lineart"]
    for docs in ("Documents", "Documentos"):
        bases.append(home / docs / "autodraw-lineart")
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        bases.append(Path(user_profile) / "autodraw-lineart")
    bindir = "Scripts" if sys.platform == "win32" else "bin"
    return [base / ".venv" / bindir / EXECUTABLE for base in bases]


def fetch_ai_lines(image: LoadedImage, client: LineartClient) -> Tuple[np.ndarray, float]:
    """Roda a extração na imagem de trabalho e devolve (linhas, segundos).

    Levanta LineartError se a ferramenta falhar ou devolver outro tamanho.
    """
    with tempfile.TemporaryDirectory(prefix="autodraw-ia-") as tmp:
        src = Path(tmp) / "entrada.png"
        out = Path(tmp) / "linhas.png"
        Image.fromarray(image.rgb).save(src)
        start = time.perf_counter()
        client.extract(src, out, threads=AI_THREADS)
        elapsed = time.perf_counter() - start
        with Image.open(out) as result:
            lines = np.asarray(result.convert("L"), dtype=np.uint8).copy()
    if lines.shape != image.gray.shape:
        raise LineartError("protocol", f"A imagem de linhas veio com {lines.shape[1]}×{lines.shape[0]} px; "
                                       f"esperado {image.gray.shape[1]}×{image.gray.shape[0]}.")
    return lines, elapsed


def has_dark_background(image: LoadedImage) -> bool:
    """Moldura escura: o modelo costuma transformar o fundo em ruído."""
    gray = image.gray.astype(np.float32) / 255.0
    h, w = gray.shape
    band = max(2, min(h, w) // 20)
    border = np.concatenate([gray[:band].ravel(), gray[-band:].ravel(),
                             gray[:, :band].ravel(), gray[:, -band:].ravel()])
    return float(border.mean()) < DARK_BORDER_LUMA
