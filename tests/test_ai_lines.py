"""Linhas por IA, testadas com um autodraw-lineart falso (sem PyTorch)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from autodraw import ai_lines
from autodraw.config import MODE_LINES, MODE_MIXED, Settings
from autodraw.image_processing import LoadedImage, load_image
from autodraw.lineart_client import LineartClient, LineartError
from autodraw.mixed import mixed_layers
from autodraw.path_generation import extract_paths

# Executável falso que segue o contrato v1. FAKE_MODE muda o comportamento.
FAKE_TOOL = r'''
import json, os, sys
from PIL import Image, ImageDraw
mode = os.environ.get("FAKE_MODE", "ok")
args = sys.argv[1:]
def reply(payload, code=0):
    print(json.dumps({"contract": 2 if mode == "contract2" else 1, "version": "falso", **payload}))
    sys.exit(code)
if mode == "garbage":
    print("isto não é JSON"); sys.exit(0)
if args[0] == "check":
    if mode == "noweights":
        reply({"ok": False, "error": "weights", "message": "sem pesos"}, 3)
    reply({"ok": True, "models": {}})
if args[0] == "extract":
    src, out = args[1], args[args.index("--out") + 1]
    w, h = Image.open(src).size
    if mode == "wrongsize":
        w, h = 10, 10
    img = Image.new("L", (w, h), 255)
    ImageDraw.Draw(img).line([(w // 5, h // 2), (4 * w // 5, h // 2)], fill=60, width=3)
    img.save(out)
    reply({"ok": True, "output": out, "model": "default", "size": 512, "threads": 2,
           "width": w, "height": h, "seconds": {"load": 0.0, "inference": 0.0}})
'''


@pytest.fixture
def fake_tool(tmp_path: Path) -> list:
    script = tmp_path / "fake_lineart.py"
    script.write_text(FAKE_TOOL, encoding="utf-8")
    return [sys.executable, str(script)]


@pytest.fixture
def picture(tmp_path: Path) -> LoadedImage:
    """Uma imagem cujas linhas próprias são verticais (a IA falsa devolve uma horizontal)."""
    img = Image.new("RGB", (300, 200), "white")
    d = ImageDraw.Draw(img)
    for x in (80, 150, 220):
        d.line([(x, 30), (x, 170)], fill="black", width=3)
    path = tmp_path / "vertical.png"
    img.save(path)
    return load_image(path)


def _directions(paths) -> set:
    out = set()
    for p in paths:
        d = p[-1] - p[0]
        out.add("h" if abs(d[0]) > abs(d[1]) else "v")
    return out


# ----------------------------------------------------------------------
# Localizar a ferramenta
# ----------------------------------------------------------------------

def test_configured_command_wins(tmp_path: Path) -> None:
    exe = tmp_path / "autodraw-lineart"
    exe.write_text("")
    assert ai_lines.find_command(Settings(lineart_command=str(exe))) == [str(exe)]
    assert ai_lines.find_command(Settings(lineart_command=str(tmp_path / "nao-existe"))) is None


def test_found_in_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai_lines.shutil, "which", lambda name: "/usr/local/bin/autodraw-lineart")
    assert ai_lines.find_command(Settings()) == ["/usr/local/bin/autodraw-lineart"]


def test_found_in_common_install_folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ai_lines.shutil, "which", lambda name: None)
    monkeypatch.setattr(ai_lines.Path, "home", classmethod(lambda cls: tmp_path))
    bindir = "Scripts" if sys.platform == "win32" else "bin"
    exe = tmp_path / "Documentos" / "autodraw-lineart" / ".venv" / bindir / ai_lines.EXECUTABLE
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    assert ai_lines.find_command(Settings()) == [str(exe)]


def test_not_found_anywhere(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ai_lines.shutil, "which", lambda name: None)
    monkeypatch.setattr(ai_lines.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("USERPROFILE", raising=False)
    assert ai_lines.find_command(Settings()) is None


# ----------------------------------------------------------------------
# Cliente
# ----------------------------------------------------------------------

def test_client_talks_to_the_tool(fake_tool, monkeypatch: pytest.MonkeyPatch) -> None:
    assert LineartClient(fake_tool).available()
    monkeypatch.setenv("FAKE_MODE", "noweights")
    assert not LineartClient(fake_tool).available()


@pytest.mark.parametrize("mode, kind", [("garbage", "protocol"), ("contract2", "contract")])
def test_client_rejects_bad_answers(fake_tool, monkeypatch: pytest.MonkeyPatch, mode: str, kind: str) -> None:
    monkeypatch.setenv("FAKE_MODE", mode)
    with pytest.raises(LineartError) as info:
        LineartClient(fake_tool).check()
    assert info.value.kind == kind


def test_client_reports_missing_executable(tmp_path: Path) -> None:
    client = LineartClient([str(tmp_path / "nao-existe")])
    assert not client.available()
    with pytest.raises(LineartError) as info:
        client.check()
    assert info.value.kind == "missing"


# ----------------------------------------------------------------------
# Obter as linhas
# ----------------------------------------------------------------------

def test_fetch_returns_lines_of_the_work_image_size(fake_tool, picture: LoadedImage) -> None:
    lines, seconds = ai_lines.fetch_ai_lines(picture, LineartClient(fake_tool))
    assert lines.shape == picture.gray.shape and lines.dtype == np.uint8
    assert lines[100, 150] < 128 and lines[20, 20] == 255
    assert seconds >= 0


def test_fetch_rejects_wrong_size(fake_tool, picture: LoadedImage, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_MODE", "wrongsize")
    with pytest.raises(LineartError) as info:
        ai_lines.fetch_ai_lines(picture, LineartClient(fake_tool))
    assert info.value.kind == "protocol"


def test_dark_background_detection(tmp_path: Path) -> None:
    dark = tmp_path / "escuro.png"
    Image.new("RGB", (200, 200), (15, 15, 20)).save(dark)
    light = tmp_path / "claro.png"
    Image.new("RGB", (200, 200), (240, 240, 240)).save(light)
    assert ai_lines.has_dark_background(load_image(dark))
    assert not ai_lines.has_dark_background(load_image(light))


# ----------------------------------------------------------------------
# Uso nos modos
# ----------------------------------------------------------------------

def test_lines_mode_uses_ai_lines_only_when_enabled(fake_tool, picture: LoadedImage) -> None:
    picture.ai_lines, _ = ai_lines.fetch_ai_lines(picture, LineartClient(fake_tool))
    with_ai = extract_paths(picture, Settings(mode=MODE_LINES, ai_lines=True))
    without = extract_paths(picture, Settings(mode=MODE_LINES, ai_lines=False))
    assert _directions(with_ai.paths) == {"h"} and with_ai.stroke_count == 1
    assert _directions(without.paths) == {"v"} and without.stroke_count == 3


def test_enabled_but_unavailable_falls_back_to_the_image(picture: LoadedImage) -> None:
    assert picture.ai_lines is None
    drawing = extract_paths(picture, Settings(mode=MODE_LINES, ai_lines=True))
    assert _directions(drawing.paths) == {"v"}


def test_mixed_mode_takes_structure_from_ai_lines(fake_tool, picture: LoadedImage) -> None:
    picture.ai_lines, _ = ai_lines.fetch_ai_lines(picture, LineartClient(fake_tool))
    structure, _ = mixed_layers(picture, Settings(mode=MODE_MIXED, ai_lines=True))
    assert _directions(structure) == {"h"}
    structure_canny, _ = mixed_layers(picture, Settings(mode=MODE_MIXED, ai_lines=False))
    assert "v" in _directions(structure_canny)


# ----------------------------------------------------------------------
# Configurações
# ----------------------------------------------------------------------

def test_settings_roundtrip_and_validation(tmp_path: Path) -> None:
    path = tmp_path / "cfg.json"
    Settings(ai_lines=True, lineart_command="  /opt/x/autodraw-lineart  ").save(path)
    loaded = Settings.load(path)
    assert loaded.ai_lines and loaded.lineart_command == "/opt/x/autodraw-lineart"

    bad = Settings.from_dict({"ai_lines": "sim", "lineart_command": 42})
    assert bad.ai_lines is False and bad.lineart_command == ""
    too_long = Settings.from_dict({"lineart_command": "x" * 5000})
    assert too_long.lineart_command == ""
    assert json.loads(path.read_text(encoding="utf-8"))["ai_lines"] is True
