# Definição da rede copiada de Anime2Sketch (https://github.com/Mukosame/Anime2Sketch),
# arquivo model.py no commit 1c1a2ed. Copyright (c) 2021 Xiaoyu Xiang, licença MIT
# (texto completo em THIRD_PARTY_LICENSES.md).
#
# Os nomes de atributos e a ordem das camadas precisam ficar idênticos aos do
# original: os pesos publicados são carregados por nome (model.model.1...).
# Mudanças em relação ao original: remoção de create_model() (que carregava os
# pesos sem weights_only) e formatação; nenhuma mudança de arquitetura.

from __future__ import annotations

import functools

import torch
import torch.nn as nn
import torch.nn.functional as F


class UnetGenerator(nn.Module):
    """Gerador U-Net."""

    def __init__(self, input_nc, output_nc, num_downs, ngf=64, norm_layer=nn.BatchNorm2d, use_dropout=False):
        super().__init__()
        unet_block = UnetSkipConnectionBlock(ngf * 8, ngf * 8, input_nc=None, submodule=None,
                                             norm_layer=norm_layer, innermost=True)
        for _ in range(num_downs - 5):
            unet_block = UnetSkipConnectionBlock(ngf * 8, ngf * 8, input_nc=None, submodule=unet_block,
                                                 norm_layer=norm_layer, use_dropout=use_dropout)
        unet_block = UnetSkipConnectionBlock(ngf * 4, ngf * 8, input_nc=None, submodule=unet_block,
                                             norm_layer=norm_layer)
        unet_block = UnetSkipConnectionBlock(ngf * 2, ngf * 4, input_nc=None, submodule=unet_block,
                                             norm_layer=norm_layer)
        unet_block = UnetSkipConnectionBlock(ngf, ngf * 2, input_nc=None, submodule=unet_block,
                                             norm_layer=norm_layer)
        self.model = UnetSkipConnectionBlock(output_nc, ngf, input_nc=input_nc, submodule=unet_block,
                                             outermost=True, norm_layer=norm_layer)

    def forward(self, input):
        return self.model(input)


class UnetSkipConnectionBlock(nn.Module):
    """Submódulo U-Net com conexão de atalho."""

    def __init__(self, outer_nc, inner_nc, input_nc=None, submodule=None, outermost=False,
                 innermost=False, norm_layer=nn.BatchNorm2d, use_dropout=False):
        super().__init__()
        self.outermost = outermost
        if isinstance(norm_layer, functools.partial):
            use_bias = norm_layer.func == nn.InstanceNorm2d
        else:
            use_bias = norm_layer == nn.InstanceNorm2d
        if input_nc is None:
            input_nc = outer_nc
        downconv = nn.Conv2d(input_nc, inner_nc, kernel_size=4, stride=2, padding=1, bias=use_bias)
        downrelu = nn.LeakyReLU(0.2, True)
        downnorm = norm_layer(inner_nc)
        uprelu = nn.ReLU(True)
        upnorm = norm_layer(outer_nc)

        if outermost:
            upconv = nn.ConvTranspose2d(inner_nc * 2, outer_nc, kernel_size=4, stride=2, padding=1)
            model = [downconv] + [submodule] + [uprelu, upconv, nn.Tanh()]
        elif innermost:
            upconv = nn.ConvTranspose2d(inner_nc, outer_nc, kernel_size=4, stride=2, padding=1, bias=use_bias)
            model = [downrelu, downconv] + [uprelu, upconv, upnorm]
        else:
            upconv = nn.ConvTranspose2d(inner_nc * 2, outer_nc, kernel_size=4, stride=2, padding=1,
                                        bias=use_bias)
            down = [downrelu, downconv, downnorm]
            up = [uprelu, upconv, upnorm]
            model = down + [submodule] + up + ([nn.Dropout(0.5)] if use_dropout else [])

        self.model = nn.Sequential(*model)

    def forward(self, x):
        if self.outermost:
            return self.model(x)
        return torch.cat([x, self.model(x)], 1)


class Smooth(nn.Module):
    def __init__(self):
        super().__init__()
        kernel = torch.tensor([[[[1, 2, 1], [2, 4, 2], [1, 2, 1]]]], dtype=torch.float)
        kernel /= kernel.sum()
        self.register_buffer("kernel", kernel)
        self.pad = nn.ReplicationPad2d(1)

    def forward(self, x):
        b, c, h, w = x.shape
        x = x.view(-1, 1, h, w)
        x = self.pad(x)
        x = F.conv2d(x, self.kernel)
        return x.view(b, c, h, w)


class Upsample(nn.Module):
    def __init__(self, inc, outc, scale_factor=2):
        super().__init__()
        self.scale_factor = scale_factor
        self.up = nn.Upsample(scale_factor=scale_factor, mode="bilinear")
        self.smooth = Smooth()
        self.conv = nn.Conv2d(inc, outc, kernel_size=3, stride=1, padding=1)
        self.mlp = nn.Sequential(
            nn.Conv2d(outc, 4 * outc, kernel_size=1, stride=1, padding=0),
            nn.GELU(),
            nn.Conv2d(4 * outc, outc, kernel_size=1, stride=1, padding=0),
        )

    def forward(self, x):
        x = self.smooth(self.up(x))
        x = self.conv(x)
        x = self.mlp(x) + x
        return x


def build_generator(improved: bool) -> UnetGenerator:
    """Arquitetura sem pesos. A versão "improved" troca 6 deconvoluções por Upsample."""
    norm = functools.partial(nn.InstanceNorm2d, affine=False, track_running_stats=False)
    net = UnetGenerator(3, 1, 8, 64, norm_layer=norm, use_dropout=False)
    if improved:
        base = net.model.model[1]
        for _ in range(6):
            inc, outc = base.model[5].in_channels, base.model[5].out_channels
            base.model[5] = Upsample(inc, outc)
            base = base.model[3]
    return net
