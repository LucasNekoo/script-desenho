from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from autodraw_lineart.weights import MODELS, WeightsError, default_weights_dir, weights_path


@pytest.fixture
def drawing(tmp_path: Path) -> Path:
    """Ilustração simples: rosto com contorno escuro sobre fundo claro."""
    img = Image.new("RGB", (300, 220), (250, 250, 250))
    d = ImageDraw.Draw(img)
    d.ellipse([80, 30, 220, 190], fill=(252, 226, 210), outline=(20, 20, 20), width=4)
    d.ellipse([115, 90, 135, 110], fill=(40, 20, 20))
    d.ellipse([165, 90, 185, 110], fill=(40, 20, 20))
    path = tmp_path / "rosto.png"
    img.save(path)
    return path


@pytest.fixture
def run_cli(capsys):
    """Roda a CLI em processo e devolve (código de saída, JSON impresso)."""
    from autodraw_lineart.cli import main

    def run(*argv: str):
        code = main([str(a) for a in argv])
        out = capsys.readouterr().out.strip().splitlines()
        assert len(out) == 1, f"esperada uma linha JSON, veio: {out}"
        return code, json.loads(out[0])

    return run


def real_weights_dir():
    try:
        weights_path("default", default_weights_dir(), verify=False)
        return default_weights_dir()
    except WeightsError:
        return None


requires_weights = pytest.mark.skipif(real_weights_dir() is None,
                                      reason=f"pesos '{MODELS['default'].filename}' não disponíveis")
