"""
Gera o guia de teste do AutoDraw para Windows 11 (PDF).

Público: quem vai testar, sem precisar saber programar. As imagens de teste
(imagens.py) e a captura da janela (capturar_janela.py) ficam nesta pasta.

Uso (da raiz do repositório, com o extra [docs] instalado):
    python docs/guia-teste/gerar_guia.py [saida.pdf]
"""

from __future__ import annotations

import sys
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    CondPageBreak,
    Flowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

HERE = Path(__file__).resolve().parent
VERSION = "23/09/2026 · branch developer"
REPO = "https://github.com/LucasNekoo/script-desenho"

# ---------------------------------------------------------------- fontes
_FONTS = {
    "Sans": ["/usr/share/fonts/noto/NotoSans-Regular.ttf", "C:/Windows/Fonts/segoeui.ttf"],
    "Sans-Bold": ["/usr/share/fonts/noto/NotoSans-Bold.ttf", "C:/Windows/Fonts/segoeuib.ttf"],
    "Sans-Italic": ["/usr/share/fonts/noto/NotoSans-Italic.ttf", "C:/Windows/Fonts/segoeuii.ttf"],
    "Mono": ["/usr/share/fonts/TTF/DejaVuSansMono.ttf", "C:/Windows/Fonts/consola.ttf"],
}
_FALLBACK = {"Sans": "Helvetica", "Sans-Bold": "Helvetica-Bold", "Sans-Italic": "Helvetica-Oblique",
             "Mono": "Courier"}
FONT = {}
for name, candidates in _FONTS.items():
    path = next((p for p in candidates if Path(p).exists()), None)
    if path:
        pdfmetrics.registerFont(TTFont(name, path))
        FONT[name] = name
    else:
        FONT[name] = _FALLBACK[name]
if FONT["Sans"] == "Sans":
    pdfmetrics.registerFontFamily("Sans", normal="Sans", bold=FONT["Sans-Bold"],
                                  italic=FONT["Sans-Italic"], boldItalic=FONT["Sans-Bold"])

# ---------------------------------------------------------------- cores e medidas
INK = colors.HexColor("#1f2937")
MUTED = colors.HexColor("#6b7280")
ACCENT = colors.HexColor("#2563eb")
ACCENT_BG = colors.HexColor("#eff6ff")
WARN = colors.HexColor("#b45309")
WARN_BG = colors.HexColor("#fffbeb")
DANGER = colors.HexColor("#b91c1c")
DANGER_BG = colors.HexColor("#fef2f2")
GOOD = colors.HexColor("#047857")
GOOD_BG = colors.HexColor("#ecfdf5")
CODE_BG = colors.HexColor("#f3f4f6")
RULE = colors.HexColor("#e5e7eb")

PAGE_W, PAGE_H = A4
MARGIN = 2 * cm
CONTENT_W = PAGE_W - 2 * MARGIN

# ---------------------------------------------------------------- estilos
body = ParagraphStyle("body", fontName=FONT["Sans"], fontSize=10, leading=15, textColor=INK, spaceAfter=6)
small = ParagraphStyle("small", parent=body, fontSize=8.5, leading=12, textColor=MUTED, spaceAfter=0)
cell = ParagraphStyle("cell", parent=body, fontSize=9, leading=12.5, spaceAfter=0)
cell_b = ParagraphStyle("cellb", parent=cell, fontName=FONT["Sans-Bold"])
h1 = ParagraphStyle("h1", fontName=FONT["Sans-Bold"], fontSize=16, leading=21, textColor=INK,
                    spaceBefore=4, spaceAfter=8)
h2 = ParagraphStyle("h2", fontName=FONT["Sans-Bold"], fontSize=12, leading=16, textColor=INK,
                    spaceBefore=10, spaceAfter=4)
kicker = ParagraphStyle("kicker", fontName=FONT["Sans-Bold"], fontSize=8.5, leading=11,
                        textColor=ACCENT, spaceAfter=1)
title = ParagraphStyle("title", fontName=FONT["Sans-Bold"], fontSize=26, leading=32, textColor=INK)
subtitle = ParagraphStyle("subtitle", fontName=FONT["Sans"], fontSize=12.5, leading=18, textColor=MUTED)
code_style = ParagraphStyle("code", fontName=FONT["Mono"], fontSize=9, leading=13,
                            textColor=colors.HexColor("#111827"))


def P(text: str, style: ParagraphStyle = body) -> Paragraph:
    return Paragraph(text, style)


def k(text: str) -> str:
    """Botão, tecla ou menu, em negrito."""
    return f'<font name="{FONT["Sans-Bold"]}">{text}</font>'


def c(text: str) -> str:
    """Trecho de código ou nome de arquivo no meio do texto."""
    return f'<font name="{FONT["Mono"]}" size="9" color="#111827">{text}</font>'


# Caminhos do Windows usados no texto (fora das f-strings: barra invertida
# dentro de expressão de f-string só vale a partir do Python 3.12).
PASTA_IMAGENS = c(r"docs\guia-teste")
PASTA_IA_SCRIPTS = c(r"autodraw-lineart\.venv\Scripts")
CMD_IA_CHECK = c(r".\.venv\Scripts\autodraw-lineart.exe check")
PASTA_USUARIO = c(r"C:\Users\SEU_NOME")
PASTA_PESOS = c(r"%LOCALAPPDATA%\autodraw-lineart")


def section(label: str, heading: str) -> list:
    return [CondPageBreak(5 * cm), P(label.upper(), kicker), P(heading, h1)]


def code(*lines: str, note: str = "") -> KeepTogether:
    """Bloco de comandos. Cada comando cabe numa linha só: a fonte encolhe se
    preciso, porque um comando quebrado ao meio seria copiado errado do PDF."""
    size = 9.0
    usable = CONTENT_W - 10 - 8
    while size > 6.5 and max(pdfmetrics.stringWidth(ln, FONT["Mono"], size) for ln in lines) > usable:
        size -= 0.25
    style = ParagraphStyle("code_fit", parent=code_style, fontSize=size, leading=size + 4)
    rows = [[Paragraph(line.replace("&", "&amp;").replace("<", "&lt;"), style)] for line in lines]
    t = Table(rows, colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CODE_BG),
        ("LINEBEFORE", (0, 0), (0, -1), 3, ACCENT),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 7),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 7),
        ("TOPPADDING", (0, 1), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -2), 1),
    ]))
    parts = [Spacer(1, 2), t]
    if note:
        parts.append(P(note, small))
    parts.append(Spacer(1, 8))
    return KeepTogether(parts)


def callout(kind: str, heading: str, text: str) -> KeepTogether:
    fg, bg = {"tip": (ACCENT, ACCENT_BG), "warn": (WARN, WARN_BG), "danger": (DANGER, DANGER_BG),
              "good": (GOOD, GOOD_BG)}[kind]
    hexcolor = fg.hexval().replace("0x", "#")
    content = [P(f'<font color="{hexcolor}">{heading}</font>', cell_b), Spacer(1, 2), P(text, cell)]
    t = Table([[content]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("LINEBEFORE", (0, 0), (0, -1), 3, fg),
        ("LEFTPADDING", (0, 0), (-1, -1), 11),
        ("RIGHTPADDING", (0, 0), (-1, -1), 11),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    return KeepTogether([Spacer(1, 3), t, Spacer(1, 9)])


class Badge(Flowable):
    """Círculo numerado."""

    def __init__(self, text: str, size: float = 15, fill=ACCENT) -> None:
        super().__init__()
        self.text, self.size, self.fill = text, size, fill
        self.width = self.height = size

    def draw(self) -> None:
        r = self.size / 2
        self.canv.setFillColor(self.fill)
        self.canv.circle(r, r - 1, r, stroke=0, fill=1)
        self.canv.setFillColor(colors.white)
        self.canv.setFont(FONT["Sans-Bold"], 8.5 if len(self.text) < 2 else 7.5)
        self.canv.drawCentredString(r, r - 4, self.text)


class CheckBox(Flowable):
    def __init__(self, size: float = 10) -> None:
        super().__init__()
        self.width = self.height = size

    def draw(self) -> None:
        self.canv.setStrokeColor(MUTED)
        self.canv.setLineWidth(0.8)
        self.canv.roundRect(0, 0, self.width, self.height, 1.5, stroke=1, fill=0)


def numbered(items: list, start: int = 1) -> Table:
    rows = [[Badge(str(i)), P(item, ParagraphStyle("step", parent=body, spaceAfter=5))]
            for i, item in enumerate(items, start)]
    t = Table(rows, colWidths=[0.9 * cm, CONTENT_W - 0.9 * cm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def simple_table(header: list, rows: list, widths: list) -> Table:
    has_header = any(header)
    body_rows = [[P(x, cell_b if (not has_header and j == 0) else cell) if isinstance(x, str) else x
                  for j, x in enumerate(r)] for r in rows]
    data = ([[P(h, cell_b) for h in header]] if has_header else []) + body_rows
    t = Table(data, colWidths=widths, repeatRows=1 if has_header else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    style.append(("LINEBELOW", (0, 0), (-1, 0), 1, INK) if has_header else ("LINEABOVE", (0, 0), (-1, 0), 0.5, RULE))
    t.setStyle(TableStyle(style))
    return t


def flow_diagram() -> Drawing:
    steps = [("1", "Instalar", "o Python", False), ("2", "Baixar", "o projeto", False),
             ("3", "Instalar as", "bibliotecas", False), ("4", "Abrir o", "programa", False),
             ("5", "Testar", "no Paint", False), ("6", "Linhas por IA", "(opcional)", True),
             ("7", "Enviar o", "retorno", False)]
    gap = 10
    box_w = (CONTENT_W - gap * (len(steps) - 1)) / len(steps)
    box_h = 58
    d = Drawing(CONTENT_W, box_h + 4)
    for i, (n, a, b, optional) in enumerate(steps):
        x = i * (box_w + gap)
        d.add(Rect(x, 2, box_w, box_h, rx=7, ry=7, fillColor=colors.white if optional else ACCENT_BG,
                   strokeColor=ACCENT, strokeWidth=1, strokeDashArray=[3, 2] if optional else None))
        d.add(String(x + box_w / 2, box_h - 16, n, fontName=FONT["Sans-Bold"], fontSize=12,
                     fillColor=ACCENT, textAnchor="middle"))
        for j, line in enumerate((a, b)):
            d.add(String(x + box_w / 2, box_h - 32 - 12 * j, line, fontName=FONT["Sans"], fontSize=7.5,
                         fillColor=MUTED if optional else INK, textAnchor="middle"))
        if i < len(steps) - 1:
            ax, ay = x + box_w + 1, 2 + box_h / 2
            d.add(Line(ax, ay, ax + gap - 4, ay, strokeColor=MUTED, strokeWidth=1.1))
            d.add(Polygon([ax + gap - 2, ay, ax + gap - 6, ay + 2.5, ax + gap - 6, ay - 2.5],
                          fillColor=MUTED, strokeColor=MUTED, strokeWidth=0.5))
    return d


def on_page(canvas, doc) -> None:
    canvas.saveState()
    if doc.page > 1:
        canvas.setFont(FONT["Sans"], 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN, 1.2 * cm, f"AutoDraw · Guia de teste no Windows 11 · versão de {VERSION}")
        canvas.drawRightString(PAGE_W - MARGIN, 1.2 * cm, f"página {doc.page}")
        canvas.setStrokeColor(RULE)
        canvas.line(MARGIN, 1.5 * cm, PAGE_W - MARGIN, 1.5 * cm)
    canvas.restoreState()


# =================================================================== conteúdo
def build_story() -> list:
    story: list = []

    # ---- capa ----------------------------------------------------------------
    story += [
        Spacer(1, 0.6 * cm),
        P("GUIA DE TESTE", ParagraphStyle("k0", parent=kicker, fontSize=10)),
        Spacer(1, 4),
        P("AutoDraw no Windows 11", title),
        Spacer(1, 6),
        P("Como instalar, usar e relatar o que você encontrar. Não é preciso saber programar: "
          "basta seguir os passos e copiar os comandos.", subtitle),
        Spacer(1, 0.5 * cm),
        P("O que é o AutoDraw", h2),
        P("É um programa que transforma uma imagem (PNG ou JPEG) em movimentos do mouse e a "
          "<b>desenha sozinho</b> numa área da tela que você escolhe, por exemplo a tela branca do Paint "
          "ou o quadro de um jogo de desenho. Você marca a área, confere uma prévia e o programa faz o "
          "resto. Esta é uma <b>versão de teste</b>: o seu retorno é o que mais importa."),
        callout("good", "Novidades desta versão",
                f"• Modo {k('linhas')}: em desenhos com traço escuro (line art, mangá), passa uma vez só "
                f"por cada linha, em vez de contorná-la dos dois lados. Desenha mais rápido.<br/>"
                f"• Modo {k('misto')}: contorno mais sombreado com hachuras, pensado para ilustrações "
                f"coloridas.<br/>"
                f"• {k('Linhas por IA')} (opcional): uma IA extrai as linhas de ilustrações coloridas. "
                f"Exige uma instalação extra, explicada no Passo 6."),
        P("O que você vai precisar", h2),
        simple_table(["", ""], [
            ["Sistema", "Windows 11 (o Windows 10 também deve funcionar)"],
            ["Tempo", "cerca de 20 minutos; mais 15 a 20 se instalar a IA"],
            ["Espaço", "cerca de 600 MB; mais ~1,3 GB se instalar a IA"],
            ["Internet", "para baixar o Python, o projeto e as bibliotecas"],
            ["Outros", "o Paint, que já vem no Windows"],
        ], [3 * cm, CONTENT_W - 3 * cm]),
        Spacer(1, 0.4 * cm),
        P("O caminho completo", h2),
        Spacer(1, 4),
        flow_diagram(),
        Spacer(1, 0.4 * cm),
        callout("danger", "Antes de tudo: como parar o programa",
                f"O AutoDraw controla o mouse de verdade. Enquanto ele desenha, é difícil usar o "
                f"computador. Para parar a qualquer momento: aperte {k('Esc')} ou leve o mouse com força "
                f"até o <b>canto superior esquerdo</b> da tela. O botão do mouse é sempre solto ao parar."),
        PageBreak(),
    ]

    # ---- passo 1 ----------------------------------------------------------------
    story += section("Passo 1", "Instalar o Python")
    story += [
        P("O AutoDraw é escrito em Python, então o Python precisa estar instalado. O jeito mais simples "
          "é pelo Terminal do Windows."),
        numbered([
            f"Abra o menu Iniciar, digite {k('Terminal')} e aperte {k('Enter')}. Abre uma janela escura "
            f"onde se digitam comandos.",
            f"Copie o comando abaixo, cole no Terminal (botão direito do mouse cola) e aperte "
            f"{k('Enter')}. Se o Windows pedir permissão, confirme.",
        ]),
        code("winget install -e --id Python.Python.3.13"),
        numbered([
            "Quando terminar, <b>feche o Terminal e abra de novo</b>. Isso é necessário para ele "
            "reconhecer o Python recém-instalado.",
            f"Confira a instalação com o comando abaixo. Deve aparecer algo como {c('Python 3.13.x')}.",
        ], start=3),
        code("py --version"),
        callout("tip", "Prefere instalar pelo site?",
                f"Baixe o <b>Windows installer (64-bit)</b> do Python 3.13 em "
                f"{c('python.org/downloads/windows')}. Na primeira tela do instalador, marque "
                f"{k('Add python.exe to PATH')} e clique em {k('Install Now')}. Não desmarque nenhuma "
                f"opção: o programa precisa do componente “tcl/tk”, que já vem marcado."),
    ]

    # ---- passo 2 ----------------------------------------------------------------
    story += section("Passo 2", "Baixar o projeto")
    story += [
        numbered([
            "Abra o link abaixo no navegador. O download de um arquivo ZIP começa na hora. Ele contém a "
            "versão de teste (a branch developer).",
        ]),
        code(f"{REPO}/archive/refs/heads/developer.zip"),
        numbered([
            f"Vá até a pasta Downloads, clique com o botão direito no arquivo "
            f"{c('script-desenho-developer.zip')} e escolha {k('Extrair Tudo…')}. Como destino, escolha "
            f"a pasta {k('Documentos')}.",
            f"Abra a pasta extraída. Ela deve ter os arquivos {c('main.py')}, {c('requirements.txt')} e "
            f"a pasta {c('autodraw')}. Se aparecer só uma outra pasta com o mesmo nome, entre nela.",
            f"As <b>imagens de teste</b> usadas neste guia ficam dentro dela, em "
            f"{PASTA_IMAGENS}: {c('teste-1-casa.png')}, {c('teste-2-lineart.png')} e "
            f"{c('teste-3-colorida.png')}.",
        ], start=2),
        callout("warn", "Não rode o programa de dentro do ZIP",
                "O Windows deixa abrir o ZIP como se fosse uma pasta, mas os comandos a seguir só "
                "funcionam na pasta extraída."),
    ]

    # ---- passo 3 ----------------------------------------------------------------
    story += section("Passo 3", "Instalar as bibliotecas")
    story += [
        P(f"Isso só precisa ser feito <b>uma vez</b>. As bibliotecas ficam numa pasta própria "
          f"({c('.venv')}) dentro do projeto, sem mexer no resto do computador."),
        numbered([
            f"Entre na pasta do projeto, clique com o botão direito num espaço vazio <b>dentro dela</b> e "
            f"escolha {k('Abrir no Terminal')}. A linha do Terminal deve terminar com o nome da pasta, por "
            f"exemplo {c('script-desenho-developer>')}, e não em {c('Documents>')}.",
            f"Rode os dois comandos abaixo, um de cada vez. O segundo demora de 1 a 3 minutos e termina "
            f"com uma linha começando por {c('Successfully installed')}.",
        ]),
        code(r"py -m venv .venv",
             r".\.venv\Scripts\python.exe -m pip install -r requirements.txt",
             note="Copie exatamente como está, incluindo o ponto e a barra do começo."),
        callout("tip", "Deu erro?",
                "Veja a seção <b>Problemas comuns</b> no fim deste guia. Se não resolver, tire um print do "
                "Terminal com a mensagem de erro e envie junto com o seu retorno."),
    ]

    # ---- passo 4 ----------------------------------------------------------------
    story += section("Passo 4", "Abrir o programa")
    story += [
        P("Com o Terminal aberto na pasta do projeto, rode:"),
        code(r".\.venv\Scripts\python.exe main.py",
             note="Nas próximas vezes, basta abrir o Terminal na pasta do projeto e rodar só este comando."),
        P("A janela do AutoDraw vai aparecer. O Terminal precisa continuar aberto enquanto você usa o "
          "programa, e as mensagens de erro, se houver, aparecem nele."),
        PageBreak(),
    ]

    # ---- janela ----------------------------------------------------------------
    shot_w = 14.5 * cm
    story += [
        P("CONHEÇA A JANELA", kicker),
        P("As partes do programa", h1),
        Image(str(HERE / "janela.png"), width=shot_w, height=shot_w * 1043 / 1100),
        P("Imagem ilustrativa, capturada em outro sistema e com a IA instalada. No Windows as cores e as "
          "fontes mudam um pouco, e o caminho mostrado na parte 4 é um exemplo.", small),
        Spacer(1, 6),
        simple_table(["", "Parte", "Para que serve"], [
            [Badge("1"), "Selecionar imagem", "Escolhe o arquivo PNG ou JPEG. A miniatura aparece logo abaixo."],
            [Badge("2"), "Selecionar área", "Escurece a tela para você arrastar e marcar onde o desenho vai sair."],
            [Badge("3"), "Modo de traçado", "Como a imagem vira traços (veja “Os ajustes”). O texto abaixo explica o modo escolhido."],
            [Badge("4"), "Linhas por IA", f"Só nos modos {k('linhas')} e {k('misto')}. Fica desabilitada até você instalar a IA (Passo 6)."],
            [Badge("5"), "Prévia do resultado", "Mostra exatamente o que será desenhado. Embaixo: número de traços e tempo estimado."],
            [Badge("6"), "Iniciar desenho", "Pede confirmação e começa a contagem de 5 segundos."],
            [Badge("7"), "Parar (Esc)", "Interrompe a contagem ou o desenho."],
            [Badge("8"), "Situação e registro", "O que o programa está fazendo e o histórico de mensagens. Útil para o retorno."],
        ], [0.9 * cm, 3.6 * cm, CONTENT_W - 4.5 * cm]),
        PageBreak(),
    ]

    # ---- passo 5 ----------------------------------------------------------------
    story += section("Passo 5", "Primeiro desenho, no Paint")
    story += [
        P("Comece sempre pelo Paint: é seguro e fácil de conferir o resultado."),
        numbered([
            f"Abra o <b>Paint</b> e maximize a janela. Escolha o {k('Lápis')} ou um {k('Pincel')} fino, "
            f"na cor preta.",
            f"No AutoDraw, deixe o {k('Modo de traçado')} em {k('contornos')} e clique em "
            f"{k('Selecionar imagem')}. Escolha {c('teste-1-casa.png')} (na pasta {PASTA_IMAGENS}).",
            f"Clique em {k('Selecionar área')}. A tela escurece: arraste o mouse sobre a parte branca do "
            f"Paint para marcar onde o desenho vai sair. {k('Esc')} ou o botão direito cancelam.",
            f"Confira a <b>prévia</b> e o tempo estimado embaixo dela. Se passar de 1 minuto, diminua "
            f"{k('Detalhes')}.",
            f"Clique em {k('Iniciar desenho')}. Uma janela resume o que vai acontecer. Clique em "
            f"{k('Iniciar desenho')} de novo.",
            "Começa uma contagem de 5 segundos e o AutoDraw se minimiza. Nesse tempo, clique na "
            "<b>barra de título</b> do Paint (a faixa de cima da janela) para deixá-lo em primeiro plano. "
            "Não clique na área branca, senão sai um ponto no desenho.",
            f"Solte o mouse e observe. Quando terminar, o AutoDraw volta a aparecer com a mensagem "
            f"{c('Desenho concluído')}.",
        ]),
        callout("danger", "Para parar no meio",
                f"Aperte {k('Esc')}, ou leve o mouse até o canto superior esquerdo da tela. Durante a "
                f"contagem, também dá para cancelar pelo botão {k('Parar (Esc)')}."),
        P("Os ajustes, em resumo", h2),
        simple_table(["Ajuste", "O que faz"], [
            ["Modo de traçado",
             f"{k('contornos')}: só as bordas, rápido. "
             f"{k('linhas')}: para desenhos com traço escuro; passa uma vez pelo centro de cada linha "
             f"(não serve para fotos). "
             f"{k('níveis')}: contorna faixas de claro e escuro. "
             f"{k('hachura')}: preenche as áreas escuras com linhas cruzadas. "
             f"{k('misto')}: contorno mais sombreado, para ilustrações coloridas."],
            ["Detalhes", "Mais detalhe gera mais traços e mais tempo."],
            ["Precisão", "Fidelidade das curvas. Valores baixos simplificam o desenho."],
            ["Tolerância de cores", "Quantas faixas de tom são usadas (níveis, hachura e misto)."],
            ["Inverter claro e escuro", "Útil para desenhar em fundos escuros."],
            ["Linhas por IA", f"Só nos modos {k('linhas')} e {k('misto')}: usa as linhas extraídas pela IA "
                              f"(Passo 6)."],
            ["Intensidade das sombras", f"Só no {k('misto')}: a partir de quão escuro algo ganha hachura."],
            ["Hachura cruzada", f"Só no {k('misto')}: segunda direção de linhas nas sombras mais fortes."],
            ["Velocidade do mouse", "Mais rápido termina antes, mas alguns programas podem “perder” "
                                    "pedaços do traço."],
            ["Suavidade / Variação natural", "Deixam o movimento menos robótico."],
            ["Envio de entrada", f"Como o mouse é controlado. {k('auto')} usa o pydirectinput no Windows; "
                                 f"se o desenho não aparecer, teste {k('pyautogui')}."],
        ], [4.2 * cm, CONTENT_W - 4.2 * cm]),
    ]

    # ---- passo 6: IA ------------------------------------------------------------
    story += section("Passo 6 · opcional", "Linhas por IA")
    story += [
        P(f"Ilustrações coloridas não têm linhas prontas. A ferramenta {k('autodraw-lineart')} usa uma "
          f"rede neural para extrair essas linhas, e o AutoDraw as desenha. Ela é <b>opcional</b>: "
          f"ocupa cerca de 1,3 GB e leva de 15 a 20 minutos para instalar. Se estiver com pouco espaço "
          f"ou tempo, pule este passo; o resto do teste funciona sem ela."),
        numbered([
            "Abra o link abaixo no navegador para baixar a ferramenta (outro ZIP):",
        ]),
        code(f"{REPO}/archive/refs/heads/autodraw-lineart.zip"),
        numbered([
            f"Extraia em {k('Documentos')}, como no Passo 2. A pasta vai se chamar "
            f"{c('script-desenho-autodraw-lineart')}: <b>renomeie para</b> {c('autodraw-lineart')}, com hífen. "
            f"Com esse nome, o AutoDraw a encontra sozinho. Dentro dela deve haver o arquivo "
            f"{c('pyproject.toml')} e a pasta {c('src')}.",
            f"Entre na pasta {c('autodraw-lineart')}, clique com o botão direito num espaço vazio "
            f"<b>dentro dela</b> e escolha {k('Abrir no Terminal')}. A linha do Terminal deve terminar em "
            f"{c('autodraw-lineart>')}, e não em {c('Documents>')}.",
            "Rode os quatro comandos abaixo, um de cada vez. O segundo baixa cerca de 200 MB e o último, "
            "os 218 MB da rede neural.",
        ], start=2),
        code(r"py -m venv .venv",
             r".\.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu",
             r'.\.venv\Scripts\python.exe -m pip install ".[download]"',
             r".\.venv\Scripts\autodraw-lineart.exe download",
             note="O endereço do segundo comando é importante: ele instala a versão para CPU, bem menor."),
        numbered([
            f"Confira com o comando abaixo. A resposta é uma linha de texto que deve conter "
            f"{c('&quot;ok&quot;: true')}.",
        ], start=5),
        code(r".\.venv\Scripts\autodraw-lineart.exe check"),
        numbered([
            f"Feche e abra o AutoDraw. Escolha o modo {k('linhas')}: a caixa {k('Linhas por IA')} deve "
            f"aparecer habilitada, com “Pronto:” e o caminho da ferramenta embaixo.",
            f"Para usar: carregue {c('teste-3-colorida.png')}, marque {k('Linhas por IA')} e espere a "
            f"prévia. Na primeira vez em cada imagem leva de 1 a 2 segundos, e o registro mostra "
            f"“Linhas por IA prontas em … s”. Depois disso, mexer nos ajustes não chama a IA de novo.",
        ], start=6),
        callout("warn", "A caixa continua desabilitada?",
                f"Em muitos computadores a pasta Documentos fica dentro do <b>OneDrive</b>, e aí o AutoDraw "
                f"não a encontra sozinho. Clique em {k('Localizar…')} ao lado da caixa e escolha o arquivo "
                f"{c('autodraw-lineart.exe')}, que fica em {PASTA_IA_SCRIPTS}. "
                f"A mensagem embaixo da caixa diz o que aconteceu."),
    ]

    # ---- roteiro ----------------------------------------------------------------
    story += [PageBreak(), P("ROTEIRO DE TESTES", kicker), P("O que testar", h1),
              P("Siga a lista na ordem e marque o que funcionou. Os itens 1 a 10 são os mais importantes; "
                "17 a 19 só se você instalou a IA (Passo 6). Anote qualquer coisa estranha, mesmo que "
                "pareça pequena.")]
    tests = [
        ("Abrir o programa", "A janela abre sem erro no Terminal."),
        ("Carregar teste-1-casa.png e depois uma foto JPG sua", "A miniatura aparece e a prévia mostra os traços em poucos segundos."),
        ("Mudar o modo e mexer nos controles de Ajustes", "A prévia e o tempo estimado se atualizam logo depois."),
        ("Desenhar teste-1-casa.png no Paint, modo contornos", "O desenho sai dentro da área marcada, sem distorcer e sem ultrapassar a borda."),
        ("Apertar Esc no meio de um desenho", "Para em menos de 1 segundo. Mexer o mouse depois não continua riscando."),
        ("Levar o mouse ao canto superior esquerdo durante um desenho", "Para com a mensagem “Parada de emergência”."),
        ("Cancelar a contagem com Esc ou com o botão Parar", "Nada é desenhado e o programa volta ao normal."),
        ("Conferir o tempo total de um desenho", "Fica próximo do tempo estimado (anote os dois)."),
        ("Carregar teste-2-lineart.png e comparar a prévia nos modos contornos e linhas; desenhar no modo linhas",
         "No linhas, cada linha sai uma vez só (no contornos, ela sai dupla) e o tempo estimado é menor."),
        ("Desenhar teste-3-colorida.png no modo misto",
         "Contorno mais sombreado com hachuras; o blush vira traços curtos; o brilho dos olhos fica sem hachura."),
        ("Desenhar nos modos níveis e hachura", "Os dois desenham; a hachura cria sombreado nas partes escuras."),
        ("Selecionar uma área encostada no canto superior esquerdo da tela",
         "O registro avisa que a área foi recuada alguns pixels, e o desenho não para sozinho."),
        ("Abrir um arquivo que não é imagem (por exemplo, um .txt renomeado para .png)",
         "Aparece uma mensagem de erro clara e o programa continua aberto."),
        ("Trocar Envio de entrada para pyautogui e desenhar de novo", "Também desenha no Paint."),
        ("Se tiver dois monitores: marcar a área no monitor secundário",
         "O programa oferece trocar para pyautogui, e o desenho sai no lugar certo."),
        ("Fechar e abrir o programa de novo", "Os ajustes escolhidos continuam os mesmos."),
        ("(IA) Com teste-3-colorida.png no modo linhas, marcar Linhas por IA",
         "O registro mostra “Linhas por IA prontas em … s” e a prévia fica com linhas limpas, sem as manchas das sombras."),
        ("(IA) Com a IA ligada, mexer em Detalhes", "A prévia se atualiza rápido, sem esperar a IA de novo."),
        ("(IA) Usar Linhas por IA no modo misto", "Contornos limpos da IA mais o sombreado com hachuras."),
    ]
    rows = [[CheckBox(), P(str(i), cell), P(a, cell), P(b, cell)] for i, (a, b) in enumerate(tests, 1)]
    story.append(simple_table(["", "#", "O que fazer", "O que deve acontecer"], rows,
                              [0.7 * cm, 0.9 * cm, 7.0 * cm, CONTENT_W - 8.6 * cm]))
    story.append(Spacer(1, 10))
    story.append(callout("warn", "Escala da tela: um teste importante",
                         f"Muitos notebooks usam escala de 125% ou 150% "
                         f"({k('Configurações › Sistema › Tela › Escala')}). Anote qual é a sua. Se o desenho "
                         f"sair deslocado ou do tamanho errado, isso é exatamente o tipo de problema que "
                         f"queremos descobrir."))
    story.append(callout("warn", "E em jogos?",
                         "O programa foi pensado para jogos de desenho, mas automação de mouse costuma ir "
                         "contra as regras de muitos jogos, inclusive o Roblox, e pode gerar punição na conta. "
                         "Para este teste, <b>o Paint basta</b>. Se for testar num jogo, faça só onde isso "
                         "for permitido, como uma experiência própria ou um servidor privado."))

    # ---- problemas -------------------------------------------------------------
    story += section("Ajuda", "Problemas comuns")
    story.append(simple_table(["Sintoma", "O que fazer"], [
        [f"{c('py')} não é reconhecido como comando",
         "O Python não foi instalado ou o Terminal não foi reaberto. Feche o Terminal, abra de novo e tente "
         "outra vez. Se continuar, refaça o Passo 1."],
        ["Erro ao instalar as bibliotecas, citando “Microsoft Visual C++” ou “wheel”",
         f"A versão do Python pode ser nova demais para alguma biblioteca. Instale o Python 3.13 (Passo 1), "
         f"apague a pasta {c('.venv')} e refaça o Passo 3."],
        [f"{c('Could not open requirements file')} ou {c('Neither setup.py nor pyproject.toml found')}",
         f"O Terminal estava fora da pasta certa (a do projeto no Passo 3, a {c('autodraw-lineart')} no "
         f"Passo 6). Apague o {c('.venv')} criado fora dela e refaça o passo, conferindo a linha do Terminal."],
        [c("No module named tkinter"),
         "O Python foi instalado sem o componente tcl/tk. Reinstale pelo site, sem desmarcar nenhuma opção."],
        ["O cursor se move, mas nada é desenhado",
         f"Confira se o Lápis ou o Pincel está selecionado no Paint. Depois, troque {k('Envio de entrada')} "
         f"para a outra opção e teste de novo."],
        ["O desenho sai deslocado ou do tamanho errado",
         "Anote a escala da tela e a resolução, tire um print e envie. É um dos pontos que mais queremos testar."],
        ["O traço sai falhado ou com buracos", f"Diminua a {k('Velocidade do mouse')} e tente de novo."],
        [f"{k('Esc')} não para o desenho",
         "Use o canto superior esquerdo da tela. E avise no retorno, porque isso não deveria acontecer."],
        ["O antivírus reclama do programa",
         f"O AutoDraw escuta o teclado <b>só durante o desenho</b> e só para detectar o {k('Esc')}. Alguns "
         f"antivírus estranham isso. Avise no retorno qual antivírus foi."],
        [f"A caixa {k('Linhas por IA')} está desabilitada",
         f"A IA não foi instalada ou não foi encontrada. Veja a mensagem embaixo da caixa e use "
         f"{k('Localizar…')} (Passo 6)."],
        ["O registro diz “Linhas por IA falharam nesta imagem”",
         f"O desenho segue sem a IA. Na pasta da IA, rode "
         f"{CMD_IA_CHECK} e envie a resposta junto com o print."],
        ["A instalação da IA baixa gigabytes de pacotes “nvidia”",
         f"Faltou o endereço do índice CPU no comando do torch. Apague a pasta {c('.venv')} da IA e refaça o "
         f"Passo 6 copiando os comandos exatamente."],
        [f"{c('autodraw-lineart download')} falha",
         "O Google Drive às vezes limita arquivos muito baixados. Tente de novo mais tarde."],
        ["Com a IA, uma imagem de fundo escuro fica cheia de riscos",
         "Limitação conhecida: o registro avisa quando detecta fundo escuro. Desmarque Linhas por IA nessas "
         "imagens e conte no retorno."],
        ["Quero voltar os ajustes para o padrão",
         f"Apague o arquivo {c('.roblox_autodraw.json')} da sua pasta de usuário ({PASTA_USUARIO})."],
    ], [5.4 * cm, CONTENT_W - 5.4 * cm]))

    # ---- retorno ----------------------------------------------------------------
    story += section("Passo 7", "Enviar o retorno")
    story += [
        P(f"Mande uma mensagem com as informações abaixo. Prints ajudam muito: "
          f"{k('Windows + Shift + S')} tira um print de uma parte da tela."),
        simple_table(["Informação", "Onde encontrar"], [
            ["Versão do Windows", k("Configurações › Sistema › Sobre")],
            ["Escala e resolução da tela", k("Configurações › Sistema › Tela")],
            ["Quantos monitores você usa", "—"],
            ["Versão do Python", f"resultado de {c('py --version')} no Terminal"],
            ["Itens do roteiro que funcionaram e que falharam", "pelos números da lista de testes"],
            ["Para cada falha: o que você fez e o que aconteceu", "com um print da janela, incluindo o registro (parte 8)"],
            ["Erros que aparecerem no Terminal", "um print ou o texto copiado"],
            ["Se instalou a IA: quanto tempo levou a primeira extração", "está no registro: “Linhas por IA prontas em … s”"],
            ["Impressões gerais", "o que foi confuso, lento ou poderia ser melhor"],
        ], [7 * cm, CONTENT_W - 7 * cm]),
        Spacer(1, 12),
        P("Para desinstalar depois", h2),
        P(f"Basta apagar a pasta do projeto em Documentos. Se instalou a IA, apague também a pasta "
          f"{c('autodraw-lineart')} e a pasta dos pesos, em {PASTA_PESOS}. "
          f"Se quiser, desinstale o Python em {k('Configurações › Aplicativos › Aplicativos instalados')}."),
        Spacer(1, 10),
        P("Obrigado por testar!", ParagraphStyle("thanks", parent=h2, textColor=ACCENT)),
    ]
    return story


def main(out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=MARGIN, bottomMargin=2.2 * cm,
                            title="AutoDraw — Guia de teste no Windows 11", author="AutoDraw",
                            subject="Instalação, uso e roteiro de testes")
    doc.build(build_story(), onFirstPage=on_page, onLaterPages=on_page)
    print(out)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "AutoDraw_Guia_de_Teste_Windows11.pdf")
