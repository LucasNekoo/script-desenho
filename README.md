# Roblox AutoDraw

Aplicativo desktop em Python que converte uma imagem PNG ou JPEG em movimentos
de mouse e reproduz o desenho dentro de uma área da tela escolhida pelo usuário.

Fluxo: **carregar imagem → selecionar área → conferir prévia → confirmar →
contagem de 5 segundos → desenho automático**, com parada imediata a qualquer
momento.

---

## Instalação

Requer Python 3.9 ou superior.

```bash
# 1. clonar/extrair o projeto e entrar na pasta
cd roblox_autodraw

# 2. (recomendado) ambiente virtual
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate     # Linux/macOS

# 3. dependências
pip install -r requirements.txt
```

No Linux, o Tkinter costuma vir em um pacote separado:
`sudo apt install python3-tk`.

## Execução

```bash
python main.py
```

---

## Como usar

1. **Selecionar imagem** — abre o seletor de arquivos (PNG ou JPEG). A prévia
   aparece à esquerda e os traços são gerados automaticamente.
2. **Selecionar área** — a tela escurece; arraste o mouse para marcar o
   retângulo onde o desenho será feito. `Esc` ou o botão direito cancela.
3. **Ajustes** — mexa nos controles e veja a prévia se atualizar. O rodapé
   mostra quantos traços serão feitos e o tempo estimado.
4. **Iniciar desenho** — a confirmação mostra o resumo e oferece três saídas:
   iniciar, voltar para a seleção de área ou cancelar.
5. **Contagem regressiva** — 5 segundos para colocar a janela do jogo em foco.
   A janela do programa se minimiza sozinha e o desenho começa.
6. **Parar** — botão *Parar*, tecla `Esc` (funciona mesmo com o jogo em foco)
   ou leve o cursor ao canto superior esquerdo da tela.

A proporção da imagem é sempre preservada: ela é centralizada dentro da área e
nenhum ponto ultrapassa os limites marcados.

---

## Ajustes

| Modo de traçado | O que faz |
| --- | --- |
| `contornos` | Detecta bordas (Canny) e desenha só o contorno. Rápido e limpo. |
| `níveis` | Separa a imagem em faixas de luminosidade e contorna cada faixa. |
| `hachura` | Preenche as regiões escuras com linhas cruzadas, criando sombreado. |

| Controle | Efeito |
| --- | --- |
| Detalhes | Sensibilidade das bordas e tamanho mínimo do traço. Mais detalhe = mais traços e mais tempo. |
| Precisão | Fidelidade das curvas. Valores baixos simplificam a geometria e aceleram o desenho. |
| Tolerância de cores | Quantas faixas de tom a imagem gera nos modos `níveis` e `hachura`. |
| Inverter claro e escuro | Útil para desenhar em telas de fundo escuro. |
| Velocidade do mouse | Tamanho do passo e pausa entre passos. |
| Suavidade | Aceleração e desaceleração nas pontas de cada trecho. |
| Variação natural | Micro-desvio aleatório para o traço não sair perfeitamente reto. |
| Envio de entrada | `pydirectinput` (recomendado no Windows) ou `pyautogui`. |

Os ajustes são salvos em `~/.roblox_autodraw.json` ao fechar o programa.

---

## Solução de problemas

**O cursor se move, mas o jogo não desenha.**
Troque *Envio de entrada* para `pydirectinput`. Ele usa `SendInput`, aceito por
jogos que ignoram o posicionamento direto do cursor. Rodar o programa como
administrador também ajuda quando o Roblox está elevado.

**O desenho sai deslocado.**
Quase sempre é escala de tela. O programa já declara consciência de DPI ao
iniciar; se o problema persistir, deixe a escala do Windows em 100% ou rode o
jogo em janela sem redimensionamento.

**Área em um segundo monitor.**
O `pydirectinput` calcula coordenadas absolutas pelo monitor principal. O
programa detecta esse caso e oferece a troca para `pyautogui`.

**O desenho ficou lento demais.**
Reduza *Detalhes*, aumente *Velocidade* e prefira o modo `contornos`. O tempo
estimado no rodapé se atualiza junto.

**O traço sai borrado ou com falhas no jogo.**
Diminua a *Velocidade*: alguns jogos amostram a posição do cursor a cada quadro
e perdem pontos quando o passo é grande demais.

**Parada de emergência.**
`Esc` global depende do `pynput`. Sem ele, restam o botão *Parar* e o failsafe
(cursor no canto superior esquerdo). O botão do mouse é sempre solto ao parar.

---

## Arquitetura

```
main.py                    ponto de entrada; ativa consciência de DPI
autodraw/
├── config.py              parâmetros e tradução para valores técnicos
├── image_processing.py    leitura, validação e pré-processamento
├── path_generation.py     extração, simplificação e ordenação dos traços
├── mouse.py               backend de entrada e execução do traçado
├── area_selector.py       overlay de seleção da área
├── preview.py             prévias renderizadas com PIL
├── countdown.py           contagem regressiva
├── hotkeys.py             tecla de parada global
└── app.py                 interface gráfica (Tkinter)
```

Separação de responsabilidades: `app.py` só coordena; nenhum outro módulo
importa Tkinter, exceto os que existem para desenhar janelas
(`area_selector`, `countdown`).

**Threads.** A interface nunca bloqueia. A extração de traços e a execução do
desenho rodam em threads separadas e conversam com a janela por uma
`queue.Queue` consultada a cada 50 ms. Cada regeneração carrega um *token*; um
resultado que chega depois de o usuário mexer nos ajustes é descartado.

**Parada.** Um `threading.Event` é verificado antes de cada passo do cursor, e o
`finally` do motor garante que o botão do mouse seja solto mesmo se algo
falhar.

**Otimização do percurso.** Os traços são ordenados pelo vizinho mais próximo de
forma vetorizada, comparando as duas pontas de cada traço e invertendo quando
isso encurta o caminho — o que reduz o tempo gasto em deslocamentos sem
desenhar.

### Como estender

* **Novo modo de traçado**: escreva uma função `_meu_modo(gray, settings)` em
  `path_generation.py` que devolva uma lista de arrays `(N, 2)`, registre a
  constante em `config.MODES` e ligue-a no `if` de `extract_paths`. A interface
  monta o seletor a partir de `MODES` e `MODE_HELP`.
* **Outro dispositivo de entrada**: implemente a mesma interface de
  `MouseBackend` (`move_to`, `mouse_down`, `mouse_up`, `position`) e passe a
  instância para `DrawingEngine`.
* **Suporte a cores da paleta do jogo**: gere um conjunto de traços por cor em
  `path_generation.py` e insira, entre os grupos, um clique na posição da cor
  correspondente da paleta.

---

## Testes

O núcleo foi validado com imagens sintéticas (formas, texto, gradientes e
ruído): tempo de extração abaixo de 0,2 s para imagens de 1200×900, proporção
preservada em áreas de qualquer formato, todos os pontos dentro dos limites
marcados, botão do mouse sempre liberado ao parar e interface responsiva
durante a execução.

## Observação

Automação de entrada contraria as regras de uso de muitos jogos, inclusive o
Roblox, e pode levar a punições na conta. Use em servidores privados, em
experiências próprias ou onde isso for permitido.
