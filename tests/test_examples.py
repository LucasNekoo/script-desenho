from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
sys.path.insert(0, str(EXAMPLES))

from cliente_autodraw import LineartClient, LineartError  # noqa: E402

from .conftest import real_weights_dir, requires_weights  # noqa: E402

cv2 = pytest.importorskip("cv2")
pytest.importorskip("skimage")
from linhas_para_tracos import lines_to_strokes, path_length  # noqa: E402

CLI = [sys.executable, "-m", "autodraw_lineart"]


def _canvas(h: int = 200, w: int = 300) -> np.ndarray:
    return np.full((h, w), 255, np.uint8)


def _ink(strokes) -> float:
    return sum(path_length(s) for s in strokes)


# ----------------------------------------------------------------------
# linhas_para_tracos
# ----------------------------------------------------------------------

@pytest.mark.parametrize("thickness", [1, 4, 9])
def test_thick_line_becomes_one_stroke_drawn_once(thickness: int) -> None:
    """O ponto central: a linha é percorrida uma vez, não 2 a 4 como no Canny."""
    img = _canvas()
    cv2.line(img, (50, 100), (250, 100), 0, thickness)
    strokes = lines_to_strokes(img)
    assert len(strokes) == 1
    assert 185 <= _ink(strokes) <= 210


def test_cross_is_covered_without_repeating() -> None:
    img = _canvas()
    cv2.line(img, (50, 100), (250, 100), 0, 3)
    cv2.line(img, (150, 20), (150, 180), 0, 3)
    strokes = lines_to_strokes(img)
    assert len(strokes) <= 3
    assert 330 <= _ink(strokes) <= 380  # 200 + 160 px


def test_closed_outline_is_a_single_loop() -> None:
    img = _canvas()
    cv2.circle(img, (150, 100), 60, 0, 3)
    strokes = lines_to_strokes(img)
    assert len(strokes) == 1
    assert abs(_ink(strokes) - 2 * math.pi * 60) < 0.1 * 2 * math.pi * 60


def test_threshold_keeps_light_gray_lines() -> None:
    img = _canvas()
    cv2.line(img, (50, 100), (250, 100), 200, 2)  # cinza claro, como o modelo costuma gerar
    assert lines_to_strokes(img, threshold=220)
    assert not lines_to_strokes(img, threshold=170)


def test_specks_and_blank_images_give_nothing() -> None:
    img = _canvas()
    assert lines_to_strokes(img) == []
    img[50:52, 50:52] = 0  # sujeira de 4 px
    assert lines_to_strokes(img) == []


# ----------------------------------------------------------------------
# cliente_autodraw
# ----------------------------------------------------------------------

def test_client_reports_missing_tool() -> None:
    client = LineartClient(command=["/caminho/que/nao/existe/autodraw-lineart"])
    assert not client.available()
    with pytest.raises(LineartError) as info:
        client.extract(Path("x.png"), Path("y.png"))
    assert info.value.kind == "missing"


def test_client_without_weights(tmp_path: Path, drawing: Path) -> None:
    client = LineartClient(command=CLI, weights_dir=tmp_path)
    assert not client.available()
    with pytest.raises(LineartError) as info:
        client.extract(drawing, tmp_path / "o.png")
    assert info.value.kind == "weights" and info.value.exit_code == 3


def test_client_invalid_image(tmp_path: Path) -> None:
    bad = tmp_path / "ruim.png"
    bad.write_bytes(b"nada")
    with pytest.raises(LineartError) as info:
        LineartClient(command=CLI).extract(bad, tmp_path / "o.png")
    assert info.value.kind == "input" and info.value.exit_code == 4


@requires_weights
@pytest.mark.weights
def test_client_end_to_end(tmp_path: Path, drawing: Path) -> None:
    client = LineartClient(command=CLI, weights_dir=real_weights_dir())
    assert client.available()
    result = client.extract(drawing, tmp_path / "linhas.png", threads=2)
    assert result.output.is_file() and (result.width, result.height) == (300, 220)
    strokes = lines_to_strokes(cv2.imread(str(result.output), cv2.IMREAD_GRAYSCALE))
    assert strokes  # o contorno do rosto vira traços
