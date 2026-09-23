from __future__ import annotations

import pytest
import torch

from autodraw_lineart.network import Upsample, build_generator


@pytest.mark.parametrize("improved", [False, True])
def test_output_is_one_channel_in_minus_one_to_one(improved: bool) -> None:
    net = build_generator(improved).eval()
    with torch.inference_mode():
        y = net(torch.rand(1, 3, 256, 256) * 2 - 1)
    assert y.shape == (1, 1, 256, 256)
    assert float(y.min()) >= -1.0 and float(y.max()) <= 1.0


def test_improved_swaps_six_deconvolutions() -> None:
    assert sum(isinstance(m, Upsample) for m in build_generator(True).modules()) == 6
    assert not any(isinstance(m, Upsample) for m in build_generator(False).modules())


@pytest.mark.parametrize("improved, count", [(False, 32), (True, 62)])
def test_parameter_names_match_published_weights(improved: bool, count: int) -> None:
    """Os pesos são carregados por nome: a cópia da rede não pode renomear nada.

    As contagens foram conferidas contra netG.pth (32) e improved.bin (62).
    """
    keys = set(build_generator(improved).state_dict())
    assert "model.model.0.weight" in keys
    assert "model.model.1.model.3.model.3.model.3.model.3.model.3.model.3.model.1.weight" in keys
    assert len(keys) == count
