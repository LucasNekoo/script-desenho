from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from autodraw.config import PROCESSING_MAX_SIDE
from autodraw.image_processing import ImageError, load_image

from .conftest import make_png


def test_loads_png(tmp_path: Path) -> None:
    img = load_image(make_png(tmp_path / "a.png", size=(200, 150)))
    assert img.original_size == (200, 150)
    assert img.pil.mode == "RGB"
    assert img.gray.shape == (150, 200)


def test_transparency_becomes_white(tmp_path: Path) -> None:
    img = load_image(make_png(tmp_path / "t.png", mode="RGBA"))
    assert img.pil.getpixel((1, 1)) == (255, 255, 255)


def test_jpeg_accepted(tmp_path: Path) -> None:
    path = tmp_path / "foto.jpg"
    Image.new("RGB", (64, 64), (10, 200, 30)).save(path, format="JPEG")
    assert load_image(path).original_size == (64, 64)


def test_large_image_is_reduced_for_processing(tmp_path: Path) -> None:
    img = load_image(make_png(tmp_path / "grande.png", size=(3000, 1500)))
    assert max(img.gray.shape) == PROCESSING_MAX_SIDE
    assert img.original_size == (3000, 1500)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ImageError, match="não encontrado"):
        load_image(tmp_path / "sumiu.png")


def test_unsupported_extension(tmp_path: Path) -> None:
    path = tmp_path / "a.gif"
    Image.new("RGB", (32, 32)).save(path, format="GIF")
    with pytest.raises(ImageError, match="Formato não suportado"):
        load_image(path)


def test_disguised_format(tmp_path: Path) -> None:
    path = tmp_path / "disfarce.png"
    Image.new("RGB", (32, 32)).save(path, format="GIF")
    with pytest.raises(ImageError, match="GIF"):
        load_image(path)


def test_corrupted_file(tmp_path: Path) -> None:
    path = tmp_path / "quebrado.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n isto nao e uma imagem")
    with pytest.raises(ImageError):
        load_image(path)


def test_too_small(tmp_path: Path) -> None:
    path = tmp_path / "mini.png"
    Image.new("RGB", (4, 40)).save(path)
    with pytest.raises(ImageError, match="pequena demais"):
        load_image(path)
