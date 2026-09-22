"""Fixtures compartilhadas: imagens sintéticas e backend de mouse falso."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional, Tuple

import pytest
from PIL import Image, ImageDraw

from autodraw.image_processing import LoadedImage, load_image


def make_png(path: Path, size: Tuple[int, int] = (200, 150), mode: str = "RGB") -> Path:
    """Fundo claro com um retângulo escuro, um círculo cinza e uma linha."""
    bg = (255, 255, 255, 0) if mode == "RGBA" else (255, 255, 255)
    img = Image.new(mode, size, bg)
    draw = ImageDraw.Draw(img)
    w, h = size
    draw.rectangle([w * 0.1, h * 0.1, w * 0.45, h * 0.8], fill=(20, 20, 20))
    draw.ellipse([w * 0.55, h * 0.2, w * 0.9, h * 0.75], fill=(120, 120, 120))
    draw.line([0, h - 5, w, h - 5], fill=(0, 0, 0), width=3)
    img.save(path)
    return path


@pytest.fixture
def sample_image(tmp_path: Path) -> LoadedImage:
    return load_image(make_png(tmp_path / "amostra.png"))


class FakeBackend:
    """Registra as chamadas em vez de mexer no cursor de verdade."""

    name = "fake"

    def __init__(self, on_move: Optional[Callable[[int], None]] = None) -> None:
        self.pos = (0, 0)
        self.moves: List[Tuple[int, int, bool]] = []  # (x, y, botão pressionado)
        self.downs = 0
        self.ups = 0
        self.pressed = False
        self._on_move = on_move

    def move_to(self, x: int, y: int) -> None:
        self.pos = (int(x), int(y))
        self.moves.append((self.pos[0], self.pos[1], self.pressed))
        if self._on_move:
            self._on_move(len(self.moves))

    def mouse_down(self) -> None:
        self.downs += 1
        self.pressed = True

    def mouse_up(self) -> None:
        self.ups += 1
        self.pressed = False

    def position(self) -> Tuple[int, int]:
        return self.pos


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove as pausas do motor de desenho para os testes rodarem rápido."""
    from autodraw import mouse

    monkeypatch.setattr(mouse.time, "sleep", lambda _s: None)
