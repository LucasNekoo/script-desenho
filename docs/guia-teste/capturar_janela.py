"""
Captura a janela do AutoDraw para o guia, com marcadores numerados.

A janela é aberta no modo linhas, com a imagem de teste colorida e a caixa
"Linhas por IA" visível; cada marcador é posicionado pela geometria real do
widget, então a figura acompanha mudanças na interface.

Requer Linux com X11/XWayland e o `import` do ImageMagick. Rode da raiz do
repositório:  python docs/guia-teste/capturar_janela.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

import autodraw.app as A  # noqa: E402
from autodraw.image_processing import load_image  # noqa: E402

ACCENT = (37, 99, 235)
# O guia é para Windows: mostra um caminho de exemplo em vez do caminho desta máquina.
EXEMPLO_CAMINHO = r"Pronto: C:\Users\voce\Documents\autodraw-lineart\.venv\Scripts\autodraw-lineart.exe"


def _font(size: int):
    for path in ("/usr/share/fonts/noto/NotoSans-Bold.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def main(out: Path) -> None:
    os.environ.pop("XDG_SESSION_TYPE", None)  # sem o aviso de Wayland no registro
    A.DEFAULT_SETTINGS_PATH = Path(tempfile.mkdtemp()) / "cfg.json"  # não mexe nas preferências reais
    app = A.AutoDrawApp()
    app.geometry("1100x1060+40+0")

    def pump(cond=lambda: False, t: float = 1.0) -> bool:
        end = time.time() + t
        while time.time() < end:
            app.update()
            if cond():
                return True
            time.sleep(0.02)
        return False

    pump(t=0.5)
    image = load_image(HERE / "teste-3-colorida.png")
    app.image = image
    app.image_label.configure(text="teste-3-colorida.png · 700×900 px")
    app._render_image_preview()
    app.mode_var.set("linhas")
    app._on_mode_change()
    if pump(lambda: app._ai_command is not None, 10):
        app.var_ai.set(True)
        app._on_image_setting()
        pump(lambda: image.ai_lines is not None, 30)
    pump(lambda: app.fitted is not None, 10)
    app._on_area_selected((600, 300, 800, 500))
    pump(t=1.5)
    app.ai_status.configure(text=EXEMPLO_CAMINHO)
    pump(t=0.5)

    ox, oy = app.winfo_rootx(), app.winfo_rooty()

    def box(widget, pad: int = 3):
        x, y = widget.winfo_rootx() - ox, widget.winfo_rooty() - oy
        return (x - pad, y - pad, x + widget.winfo_width() + pad, y + widget.winfo_height() + pad)

    def union(*boxes):
        return (min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes))

    settings_box = app.mode_help.master
    mode_row = settings_box.winfo_children()[0]
    marks = [
        box(app.btn_image),
        box(app.btn_area),
        union(box(mode_row), box(app.mode_help)),
        box(app.ai_box),
        box(app.preview_canvas.master),
        box(app.btn_start),
        box(app.btn_stop),
        union(box(app.status_label), box(app.log)),
    ]

    raw = Path(tempfile.mkdtemp()) / "janela.png"
    subprocess.run(["import", "-window", str(app.winfo_id()), str(raw)], check=True)
    app._regen_executor.shutdown(wait=True)
    app.destroy()

    img = Image.open(raw).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    font = _font(26)
    for rect in marks:
        d.rounded_rectangle(rect, radius=6, outline=ACCENT + (255,), width=4)
    for n, (x0, y0, x1, _y1) in enumerate(marks, 1):
        r = 19
        # Onde o canto do quadro cobriria texto, o marcador vai para fora dele:
        # acima dos botões pequenos (6 e 7), à esquerda da coluna de ajustes
        # (3, 4 e 5) e à direita do registro (8).
        if n in (6, 7):
            cx, cy = (x0 + x1) // 2, y0 - r - 4
        elif n in (3, 4, 5):
            cx, cy = x0 - r + 2, y0 + r
        elif n == 8:
            cx, cy = x1 - r - 6, y0 - r + 6
        else:
            cx, cy = x0 + 4, y0 + 2
        cx, cy = max(cx, r + 2), max(cy, r + 2)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ACCENT + (255,),
                  outline=(255, 255, 255, 255), width=3)
        d.text((cx, cy - 1), str(n), font=font, fill="white", anchor="mm")
    Image.alpha_composite(img, overlay).convert("RGB").save(out, optimize=True)
    print(out, img.size)


if __name__ == "__main__":
    main(HERE / "janela.png")
