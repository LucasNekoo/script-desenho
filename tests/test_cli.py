from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from autodraw_lineart import extract
from autodraw_lineart.cli import CONTRACT
from autodraw_lineart.network import build_generator

from .conftest import requires_weights


@pytest.fixture
def random_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rede com pesos aleatórios: valida o contrato sem baixar 200 MB."""
    monkeypatch.setattr(extract, "load_model", lambda *a, **k: build_generator(False).eval())


def test_extract_writes_grayscale_png_of_input_size(run_cli, drawing: Path, tmp_path: Path,
                                                    random_model) -> None:
    out = tmp_path / "linhas.png"
    code, payload = run_cli("extract", drawing, "--out", out, "--size", 256, "--threads", 1)
    assert code == 0 and payload["ok"] and payload["contract"] == CONTRACT
    img = Image.open(out)
    assert img.mode == "L" and img.size == Image.open(drawing).size
    assert (payload["width"], payload["height"]) == img.size


def test_transparent_input_is_flattened_on_white() -> None:
    rgba = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    assert extract.flatten(rgba).getpixel((5, 5)) == (255, 255, 255)


def test_missing_weights_exit_3(run_cli, drawing: Path, tmp_path: Path) -> None:
    code, payload = run_cli("extract", drawing, "--out", tmp_path / "o.png", "--weights-dir", tmp_path)
    assert code == 3 and not payload["ok"] and payload["error"] == "weights"


def test_invalid_image_exit_4(run_cli, tmp_path: Path) -> None:
    bad = tmp_path / "quebrada.png"
    bad.write_bytes(b"nao e imagem")
    code, payload = run_cli("extract", bad, "--out", tmp_path / "o.png")
    assert code == 4 and payload["error"] == "input"


def test_size_must_be_multiple_of_256(run_cli, drawing: Path, tmp_path: Path) -> None:
    code, payload = run_cli("extract", drawing, "--out", tmp_path / "o.png", "--size", 500)
    assert code == 2 and payload["error"] == "usage"


def test_check_reports_each_model(run_cli, tmp_path: Path) -> None:
    code, payload = run_cli("check", "--weights-dir", tmp_path)
    assert code == 3 and not payload["ok"]
    assert set(payload["models"]) == {"default", "improved"}


def test_check_does_not_import_torch(tmp_path: Path) -> None:
    """O autodraw chama o check para saber se a IA está disponível: precisa ser rápido."""
    code = ("import sys; from autodraw_lineart.cli import main; "
            f"main(['check', '--weights-dir', {str(tmp_path)!r}]); print('torch' in sys.modules)")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.stdout.strip().splitlines()[-1] == "False"


@requires_weights
@pytest.mark.weights
def test_real_model_draws_the_outline(run_cli, drawing: Path, tmp_path: Path) -> None:
    out = tmp_path / "linhas.png"
    code, payload = run_cli("extract", drawing, "--out", out, "--threads", 2)
    assert code == 0, payload
    lines = np.asarray(Image.open(out))
    assert lines[5, 5] > 200            # fundo continua claro
    assert (lines < 170).mean() > 0.005  # o contorno do rosto vira linha escura
