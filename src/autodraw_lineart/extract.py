"""Inferência: imagem colorida -> imagem de linhas (fundo branco, traços escuros)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from .weights import MODELS, weights_path

# A U-Net reduz a imagem 8 vezes pela metade: o lado precisa ser múltiplo de 2^8.
SIZE_STEP = 256


def load_model(model: str = "default", weights_dir: Path | None = None, verify: bool = True):
    """Monta a rede e carrega os pesos conferidos, sem executar código do arquivo."""
    import torch

    from .network import build_generator

    spec = MODELS[model]
    state = torch.load(weights_path(model, weights_dir, verify), map_location="cpu", weights_only=True)
    state = {key.replace("module.", ""): value for key, value in state.items()}
    net = build_generator(spec.improved)
    net.load_state_dict(state)
    return net.eval()


def flatten(image: Image.Image) -> Image.Image:
    """RGB sobre fundo branco: transparência não pode virar fundo preto."""
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, (255, 255, 255))
        canvas.paste(rgba, mask=rgba.split()[-1])
        return canvas
    return image.convert("RGB")


def extract_lines(net, image: Image.Image, size: int = 512) -> Image.Image:
    """Mesmo pré e pós-processamento do test.py original; saída no tamanho da entrada."""
    import torch

    if size < SIZE_STEP or size % SIZE_STEP:
        raise ValueError(f"size precisa ser múltiplo de {SIZE_STEP} (recebido {size}).")
    rgb = flatten(image)
    x = np.asarray(rgb.resize((size, size), Image.BICUBIC), np.float32) / 255.0
    tensor = torch.from_numpy((x - 0.5) / 0.5).permute(2, 0, 1).unsqueeze(0).contiguous()
    with torch.inference_mode():
        y = net(tensor)[0, 0].numpy()
    lines = ((y + 1.0) / 2.0 * 255.0).clip(0, 255).astype(np.uint8)
    return Image.fromarray(lines, "L").resize(rgb.size, Image.BICUBIC)
