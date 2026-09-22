"""
Modo misto: analisa a imagem e decide, região por região, o que desenhar.

    análise (maps)  ->  estrutura: silhueta + bordas estruturais
                    ->  tom: hachura adaptativa (densidade, direção, cruzamento)
                    ->  orçamento de traços por prioridade

A estrutura é desenhada antes do tom: se o desenho for interrompido, o que já
saiu é legível.
"""

from __future__ import annotations

from typing import List

from ..config import Settings
from ..image_processing import LoadedImage
from ..path_generation import Path
from .layers import structure_layer, tone_layer
from .maps import analyze


def mixed_layers(image: LoadedImage, settings: Settings) -> List[List[Path]]:
    """Devolve [estrutura, tom], já cortados para caber em `settings.max_paths`.

    O corte segue a hierarquia visual: silhueta, bordas longas, bordas curtas,
    e só então a hachura, das sombras mais fortes para as mais leves.
    """
    maps = analyze(image, settings)
    structure = structure_layer(maps, settings)[: settings.max_paths]
    remaining = settings.max_paths - len(structure)

    tone = tone_layer(maps, settings)
    tone.sort(key=lambda item: item[0], reverse=True)
    return [structure, [seg for _, seg in tone[: max(0, remaining)]]]
