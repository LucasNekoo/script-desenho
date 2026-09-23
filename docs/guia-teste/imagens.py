"""
Gera as imagens de teste que acompanham o guia (todas próprias, sem direitos de terceiros).

    teste-1-casa.png       desenho simples em preto e branco (primeiro teste, modo contornos)
    teste-2-lineart.png    line art estilo mangá: linhas de 1 a 5 px, hachuras, pupilas pretas (modo linhas)
    teste-3-colorida.png   ilustração colorida estilo anime: pele, sombras, blush, brilho (modos misto e IA)

Uso: python docs/guia-teste/imagens.py [pasta_de_saida]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent


def casa() -> Image.Image:
    img = Image.new("RGB", (600, 450), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([150, 220, 400, 400], outline="black", width=6)
    d.polygon([(130, 225), (275, 100), (420, 225)], outline="black", fill=(90, 90, 90))
    d.rectangle([250, 300, 310, 400], fill=(40, 40, 40))
    d.rectangle([175, 250, 225, 295], outline="black", width=4)
    d.ellipse([460, 40, 560, 140], outline="black", width=6)
    for x in range(0, 600, 40):
        d.line([x, 420, x + 20, 440], fill="black", width=3)
    return img


def lineart() -> Image.Image:
    ss = 3
    im = Image.new("L", (700 * ss, 900 * ss), 255)
    d = ImageDraw.Draw(im)

    def s(*v):
        return [x * ss for x in v]

    d.ellipse(s(215, 170, 485, 500), outline=0, width=5 * ss)                        # rosto
    d.arc(s(150, 90, 550, 560), 180, 360, fill=0, width=4 * ss)                      # cabelo
    for x in range(170, 540, 22):                                                    # mechas
        d.line(s(x, 150 + abs(x - 350) // 3, x + 15, 330), fill=0, width=2 * ss)
    for cx in (295, 405):
        d.ellipse(s(cx - 38, 300, cx + 38, 370), outline=0, width=3 * ss)             # olho
        d.ellipse(s(cx - 14, 318, cx + 14, 356), fill=0)                              # pupila
        d.ellipse(s(cx - 10, 322, cx - 2, 332), fill=255)                             # brilho
    d.line(s(335, 430, 365, 430), fill=0, width=3 * ss)                              # boca
    for i in range(8):                                                               # blush
        d.line(s(250 + i * 8, 395, 262 + i * 8, 410), fill=0, width=1 * ss)
    d.polygon(s(170, 560, 530, 560, 600, 900, 100, 900), outline=0, width=4 * ss)   # roupa
    for x0 in (230, 330, 430):                                                       # dobras
        d.line(s(x0, 600, x0 + 40, 900), fill=0, width=2 * ss)
    for y in range(700, 890, 9):                                                     # hachura
        d.line(s(460, y, 590, y - 40), fill=0, width=1 * ss)
    return im.resize((700, 900), Image.LANCZOS).convert("RGB")


def colorida() -> Image.Image:
    ss = 2
    w, h = 700 * ss, 900 * ss
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    line, lw = (30, 20, 25), 3 * ss

    def s(*v):
        return [x * ss for x in v]

    def shape(kind, box, fill, outline=True):
        getattr(d, kind)(s(*box), fill=fill, outline=line if outline else None, width=lw if outline else 0)

    shape("ellipse", (150, 90, 550, 560), (90, 55, 45))                              # cabelo de trás
    shape("rectangle", (160, 300, 540, 620), (90, 55, 45))
    shape("rectangle", (300, 470, 400, 580), (252, 226, 210))                        # pescoço
    d.polygon(s(300, 470, 400, 470, 400, 520, 300, 540), fill=(232, 188, 172))
    shape("polygon", (170, 560, 530, 560, 600, 900, 100, 900), (242, 242, 250))    # camisa
    for x0 in (230, 330, 430):
        d.polygon(s(x0, 600, x0 + 25, 600, x0 + 60, 900, x0 + 20, 900), fill=(205, 205, 222))
    shape("polygon", (100, 620, 200, 580, 230, 900, 90, 900), (45, 52, 95))         # jaqueta
    shape("polygon", (600, 620, 500, 580, 470, 900, 610, 900), (45, 52, 95))
    d.polygon(s(150, 650, 175, 640, 200, 900, 170, 900), fill=(85, 95, 150))
    shape("ellipse", (215, 170, 485, 500), (252, 226, 210))                          # rosto
    d.chord(s(215, 150, 485, 330), 0, 180, fill=(236, 192, 178))                    # sombra da franja
    shape("polygon", (190, 250, 230, 130, 350, 90, 470, 130, 510, 250, 450, 200, 420, 260,
                      370, 190, 330, 265, 280, 200, 240, 270), (90, 55, 45))          # franja
    d.arc(s(250, 120, 450, 230), 200, 330, fill=(200, 150, 120), width=10 * ss)     # brilho do cabelo
    for cx in (285, 415):
        d.ellipse(s(cx - 35, 385, cx + 35, 410), fill=(247, 196, 190))              # blush
    for cx in (295, 405):
        shape("ellipse", (cx - 38, 300, cx + 38, 370), (255, 255, 255))
        shape("ellipse", (cx - 25, 305, cx + 25, 368), (120, 40, 50), outline=False)
        d.ellipse(s(cx - 12, 322, cx + 12, 356), fill=(40, 12, 18))
        d.ellipse(s(cx - 15, 310, cx - 3, 324), fill=(255, 255, 255))
    d.line(s(335, 430, 365, 430), fill=line, width=lw)
    d.line(s(350, 385, 345, 400), fill=(200, 150, 140), width=2 * ss)
    img = img.resize((w // ss, h // ss), Image.LANCZOS)

    arr = np.asarray(img).astype(np.float32)
    yy, xx = np.mgrid[0:arr.shape[0], 0:arr.shape[1]]
    arr[(xx > 520) & (xx < 590) & (yy > 640) & (yy < 880)] = [252, 226, 210]         # braço
    sleeve = (xx > 505) & (xx < 605) & (yy > 620) & (yy < 780)                        # manga semitransparente
    arr[sleeve] = arr[sleeve] * 0.5 + np.array([180, 200, 240]) * 0.5
    cx, cy, r = 600, 110, 80                                                          # esfera com volume
    dx, dy = (xx - cx) / r, (yy - cy) / r
    inside = dx ** 2 + dy ** 2 <= 1
    nz = np.sqrt(np.clip(1 - dx ** 2 - dy ** 2, 0, 1))
    light = np.clip(-0.5 * dx - 0.6 * dy + 0.62 * nz, 0, 1)
    spec = light ** 40
    col = np.stack([c * (0.15 + 0.85 * light) + 255 * spec for c in (200, 90, 110)], -1)
    arr[inside] = np.clip(col[inside], 0, 255)
    return Image.fromarray(arr.astype(np.uint8))


def main(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, make in (("teste-1-casa.png", casa), ("teste-2-lineart.png", lineart),
                       ("teste-3-colorida.png", colorida)):
        make().save(out_dir / name, optimize=True)
        print(out_dir / name)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else HERE)
