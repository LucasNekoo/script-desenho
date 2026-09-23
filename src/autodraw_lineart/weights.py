"""
Pesos dos modelos: onde ficam, como conferir e como baixar.

Os pesos são pickles do PyTorch. Por isso:
* cada arquivo tem SHA-256 fixo e é conferido antes de ser carregado;
* o carregamento usa weights_only=True, que não executa código do arquivo.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path

ENV_WEIGHTS_DIR = "AUTODRAW_LINEART_WEIGHTS"


class WeightsError(Exception):
    """Pesos ausentes ou diferentes dos publicados."""


@dataclass(frozen=True)
class WeightsSpec:
    model: str
    filename: str
    sha256: str
    size: int
    drive_id: str
    improved: bool


# Publicados pelo Anime2Sketch (links do README, commit 1c1a2ed).
MODELS = {
    "default": WeightsSpec(
        model="default",
        filename="netG.pth",
        sha256="ccabdcc3f5cf3c07cf65d58776acb21df7dfda825cdc70c9766a93fd62bfc488",
        size=217_631_959,
        drive_id="1RILKwUdjjBBngB17JHwhZNBEaW4Mr-Ml",
        improved=False,
    ),
    "improved": WeightsSpec(
        model="improved",
        filename="improved.bin",
        sha256="d2913793286bdeb32f340e2f64e54154ab291daf43f5a352f73543cd3a5a3248",
        size=191_927_595,
        drive_id="1cf90_fPW-elGOKu5mTXT5N1dum-XY_46",
        improved=True,
    ),
}


def default_weights_dir() -> Path:
    """Pasta de dados do usuário: %LOCALAPPDATA% no Windows, XDG no Linux."""
    env = os.environ.get(ENV_WEIGHTS_DIR)
    if env:
        return Path(env)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "autodraw-lineart" / "weights"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def weights_path(model: str, weights_dir: Path | None = None, verify: bool = True) -> Path:
    """Caminho dos pesos já conferidos. Levanta WeightsError se algo não bate."""
    spec = MODELS[model]
    path = (weights_dir or default_weights_dir()) / spec.filename
    if not path.is_file():
        raise WeightsError(f"Pesos '{spec.filename}' não encontrados em {path.parent}. "
                           f"Rode: autodraw-lineart download --model {model}")
    if path.stat().st_size != spec.size:
        raise WeightsError(f"{path.name} tem {path.stat().st_size} bytes; esperado {spec.size}.")
    if verify and sha256_of(path) != spec.sha256:
        raise WeightsError(f"{path.name} não confere com o SHA-256 publicado; apague e baixe de novo.")
    return path


def download(model: str, weights_dir: Path | None = None) -> Path:
    """Baixa do Google Drive (requer o extra [download]) e confere o SHA-256."""
    try:
        import gdown
    except ImportError as exc:
        raise WeightsError("Para baixar, instale o extra: pip install 'autodraw-lineart[download]'") from exc
    spec = MODELS[model]
    target_dir = weights_dir or default_weights_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / spec.filename
    partial = target.with_suffix(target.suffix + ".part")
    # O stdout é do contrato (uma linha JSON): o progresso do gdown vai para o stderr.
    with contextlib.redirect_stdout(sys.stderr):
        gdown.download(id=spec.drive_id, output=str(partial), quiet=False)
    if sha256_of(partial) != spec.sha256:
        partial.unlink(missing_ok=True)
        raise WeightsError(f"O arquivo baixado para '{model}' não confere com o SHA-256 publicado.")
    partial.replace(target)
    return target
