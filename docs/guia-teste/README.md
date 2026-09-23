# Guia de teste para Windows

O guia em PDF que é enviado a quem testa o AutoDraw no Windows 11, e tudo o
que é preciso para gerá-lo de novo.

| Arquivo | O que é |
| --- | --- |
| `gerar_guia.py` | Gera o PDF (reportlab). O texto do guia está todo aqui |
| `imagens.py` | Gera as três imagens de teste citadas no guia |
| `capturar_janela.py` | Captura a janela do AutoDraw com os marcadores numerados (`janela.png`) |
| `teste-1-casa.png` | Desenho simples em preto e branco: primeiro teste, modo `contornos` |
| `teste-2-lineart.png` | Line art estilo mangá: comparação entre `contornos` e `linhas` |
| `teste-3-colorida.png` | Ilustração colorida estilo anime: modos `misto` e Linhas por IA |
| `janela.png` | Captura usada na página "As partes do programa" |

As imagens são próprias, sem direitos de terceiros. O PDF gerado não vai
para o git (`.gitignore`): gere quando for enviar.

## Gerar o PDF

```bash
pip install -e ".[docs]"
python docs/guia-teste/gerar_guia.py                 # grava AutoDraw_Guia_de_Teste_Windows11.pdf nesta pasta
python docs/guia-teste/gerar_guia.py ~/saida.pdf     # ou em outro lugar
```

Usa Noto Sans e DejaVu Sans Mono no Linux, ou Segoe UI e Consolas no Windows;
sem elas, cai nas fontes padrão do PDF.

## Quando a interface mudar

1. `python docs/guia-teste/capturar_janela.py`: refaz `janela.png`. Precisa de
   Linux com X11/XWayland e do `import` do ImageMagick. Se o `autodraw-lineart`
   estiver instalado, a captura mostra a opção de IA habilitada. Os marcadores
   seguem a posição real dos widgets.
2. Revise, em `gerar_guia.py`, a tabela "As partes do programa" (ela descreve
   os números da captura) e a lista "Os ajustes, em resumo".
3. Gere o PDF e confira as páginas antes de enviar. Em especial, confira se
   nenhum comando quebrou em duas linhas: os blocos de código encolhem a
   fonte para caber, mas só até 6,5 pt.
