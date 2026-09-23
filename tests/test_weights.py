from __future__ import annotations

import builtins
import hashlib
from pathlib import Path

import pytest

from autodraw_lineart import weights
from autodraw_lineart.weights import WeightsError, WeightsSpec, default_weights_dir, weights_path


@pytest.fixture
def tiny_spec(monkeypatch: pytest.MonkeyPatch) -> bytes:
    """Troca o modelo padrão por um "peso" de 16 bytes para testar a conferência."""
    data = b"0123456789abcdef"
    spec = WeightsSpec("default", "netG.pth", hashlib.sha256(data).hexdigest(), len(data), "x", False)
    monkeypatch.setitem(weights.MODELS, "default", spec)
    return data


def test_env_var_overrides_weights_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(weights.ENV_WEIGHTS_DIR, str(tmp_path))
    assert default_weights_dir() == tmp_path


def test_missing_weights_explain_how_to_download(tmp_path: Path) -> None:
    with pytest.raises(WeightsError, match="autodraw-lineart download"):
        weights_path("default", tmp_path)


def test_accepts_matching_file(tmp_path: Path, tiny_spec: bytes) -> None:
    (tmp_path / "netG.pth").write_bytes(tiny_spec)
    assert weights_path("default", tmp_path) == tmp_path / "netG.pth"


def test_rejects_wrong_size(tmp_path: Path, tiny_spec: bytes) -> None:
    (tmp_path / "netG.pth").write_bytes(tiny_spec + b"!")
    with pytest.raises(WeightsError, match="bytes"):
        weights_path("default", tmp_path)


def test_rejects_tampered_file_of_same_size(tmp_path: Path, tiny_spec: bytes) -> None:
    (tmp_path / "netG.pth").write_bytes(tiny_spec[::-1])
    with pytest.raises(WeightsError, match="SHA-256"):
        weights_path("default", tmp_path)
    # sem verificação, só o tamanho conta
    assert weights_path("default", tmp_path, verify=False)


def test_download_without_gdown_is_a_clear_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "gdown":
            raise ImportError("sem gdown")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(WeightsError, match=r"\[download\]"):
        weights.download("default", tmp_path)
