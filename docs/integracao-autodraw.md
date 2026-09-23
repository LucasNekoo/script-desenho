# Integração com o AutoDraw

Como ligar esta ferramenta no AutoDraw. **Estado:** a ferramenta e as peças de
referência estão prontas e testadas; a integração do lado do AutoDraw ainda
não foi feita. Este documento é o roteiro.

## O que o AutoDraw ganha

Hoje o modo `contornos` (e a camada de estrutura do modo `misto`) detecta
bordas com Canny. Isso tem dois problemas, ambos medidos:

1. **Cada linha é percorrida várias vezes.** Numa linha de 4 px, o Canny acha
   as duas margens e o traçado contorna cada margem indo e voltando. O mouse
   passa pela mesma linha **4 vezes**.
2. **Ruído em ilustrações coloridas:** sombras, reflexos e texturas viram
   pedaços de borda soltos.

A ferramenta resolve o segundo (a rede devolve só as linhas de desenho), e o
pós-processamento por **linha central** resolve o primeiro.

![Uma mesma linha grossa: o Canny gera 2 traços e 2.251 px de percurso; a linha central, 1 traço e 545 px](img/linha-central.png)

## Resultados medidos

Área de 600×600 px na tela, velocidade padrão, ajustes padrão do modo
`contornos`, limiar 220. "Tinta" é a distância percorrida com o botão
pressionado; "tempo" é a estimativa do próprio AutoDraw.

| Imagem | Hoje (Canny) | Com autodraw-lineart + linha central | Veredito |
| --- | --- | --- | --- |
| Ilustração sintética (700×900, abaixo) | 34 traços · 10.852 px · **3,7 s** | 33 traços · 4.708 px · **2,4 s** | ✅ 2,3× menos tinta, 35% mais rápido, linhas únicas |
| `madoka.jpg`¹ (anime, fundo claro) | 154 traços · 29.683 px · **12,7 s** | 125 traços · 11.230 px · **7,7 s** | ✅ 2,6× menos tinta, 39% mais rápido, bem mais limpo |
| `saber.png`¹ (fundo escuro com efeitos), modelo `default` | 125 traços · 15.788 px · **8,6 s** | 358 traços · 11.243 px · **17,3 s** | ❌ o fundo vira ruído |
| `saber.png`¹, modelo `improved` | idem | 260 traços · 10.017 px · **13,0 s** | ❌ melhor, mas ainda pior que o Canny |

¹ Amostras de teste que acompanham o projeto Anime2Sketch (`test_samples/`).
Não estão neste repositório porque são *fan art* de terceiros.

Custo extra por imagem: ~1 s na chamada (uma vez por imagem carregada) e
14–49 ms no traçado. Mexer nos sliders não chama a ferramenta de novo.

![Original, contornos atuais (Canny), saída da ferramenta e traços por linha central](img/comparacao-sintetica.png)

Repare nos olhos: o Canny desenha anéis duplos; a linha central, um traço só.

## Passo a passo

### 1. Detectar se a ferramenta está disponível

Copie a classe `LineartClient` de
[`examples/cliente_autodraw.py`](../examples/cliente_autodraw.py) para o
AutoDraw (ela só usa a biblioteca padrão). Na inicialização, **numa thread**,
chame `available()` (~30 ms). Se der `False`, a opção de IA simplesmente não
aparece e nada mais muda.

A ferramenta vive no próprio ambiente Python, então normalmente **não está no
PATH** do AutoDraw. Guarde o caminho do executável nas preferências
(`~/.roblox_autodraw.json`), por exemplo:

| Sistema | Caminho típico |
| --- | --- |
| Windows | `C:\...\autodraw-lineart\.venv\Scripts\autodraw-lineart.exe` |
| Linux | `~/autodraw-lineart/.venv/bin/autodraw-lineart` |

e passe `LineartClient(command=[caminho])`. Valide esse campo em
`Settings.from_dict` como os demais.

### 2. Gerar as linhas uma vez por imagem, com cache

* Use a **imagem de trabalho** do AutoDraw (`LoadedImage.rgb`, até 900 px),
  não a original. Assim a saída já vem nas coordenadas que o resto do AutoDraw
  usa.
* Grave num PNG temporário, chame `client.extract(entrada, saida)` e leia a
  saída como `numpy` (tons de cinza).
* Guarde em cache por **imagem + modelo** (por exemplo, um dicionário no
  `AutoDrawApp`, ou um campo opcional em `LoadedImage`). Os sliders não mudam
  a imagem de linhas, então ajustar Detalhes ou Precisão só refaz o traçado
  (milissegundos).
* Chame dentro do worker de regeneração que já existe
  (`_regen_executor`/`_regeneration_worker` no `app.py`), nunca na thread do Tk:
  a chamada leva ~1 s.

### 3. Transformar as linhas em traços

Use [`examples/linhas_para_tracos.py`](../examples/linhas_para_tracos.py)
(precisa de `scikit-image`, download de ~14 MB, para o `skeletonize`, ou de uma
implementação própria de afinamento):

```python
strokes = lines_to_strokes(
    lines,                                   # uint8, fundo claro
    threshold=220,                           # 170 perdeu os olhos no teste
    epsilon=settings.epsilon,                # vem de "Precisão"
    min_length=settings.min_contour_length,  # vem de "Detalhes"
)
```

| Parâmetro | Efeito | Medido |
| --- | --- | --- |
| `threshold` | Até que tom de cinza conta como linha | 220 bom; 170 perde as linhas cinza-claras que o modelo gera |
| `min_area` | Descarta manchas pequenas antes do esqueleto | 12 px² |
| `epsilon` | Simplificação Douglas-Peucker | Precisão 55 → 1,7 px |
| `min_length` | Traço mínimo | **Pesa muito no tempo**: com traço mínimo de 8 px (e `epsilon` 1,0), a Madoka ficou com 193 traços e 10,8 s, contra 125 traços e 7,7 s com os valores acima. Cada traço custa duas pausas de caneta |

### 4. Encaixar no `extract_paths`

O `extract_paths` já aceita modos com várias camadas, desenhadas em sequência.
A proposta é trocar **só a fonte das linhas estruturais**:

* **Modo `contornos`:** com a opção de IA ligada, a camada única passa a ser
  `strokes` em vez de `_outline_paths(gray, settings)`.
* **Modo `misto`:** a camada de estrutura (`structure_layer`) usa `strokes` no
  lugar das bordas Canny; a camada de tom (hachura) continua igual.

A simplificação, o limite de traços e a ordenação por camada que o
`extract_paths` já faz continuam valendo.

### 5. Interface

* Uma caixa **"Linhas por IA"** perto do modo de traçado, visível só quando
  `available()` for `True` e o modo for `contornos` ou `misto`.
* Mostrar no registro o tempo da chamada e o modelo usado.
* Mapear os erros para mensagens (o `message` já vem em português):

| `LineartError.kind` | Ação |
| --- | --- |
| `missing` | Esconder a opção |
| `weights` | Esconder a opção e sugerir `autodraw-lineart download` |
| `input` | Mostrar `message` |
| `timeout`, `unexpected`, `protocol` | Voltar ao Canny nesta imagem e registrar |
| `contract` | Avisar que a ferramenta precisa ser atualizada |

### 6. Testes no AutoDraw

Não é preciso instalar o PyTorch na CI do AutoDraw. Crie um **executável falso**
(um script Python de poucas linhas) que responda como o contrato e grave uma
imagem de linhas conhecida, e passe-o como `command`. Os testes de
[`tests/test_examples.py`](../tests/test_examples.py) mostram como testar o
cliente e o traçado.

## Limitações e como contornar

| Situação | O que acontece | Como contornar |
| --- | --- | --- |
| Fundo escuro com efeitos de luz | `default`: padrão quadriculado; `improved`: manchas; os dois viram ruído após o limiar (tabela acima) | Detectar fundo escuro (por exemplo, luminância média da borda da imagem baixa) e **manter o Canny** nesses casos, ou só oferecer a IA com aviso |
| Imagem muito alongada | A rede processa um quadrado esticado; detalhes finos no eixo comprimido podem perder definição | `--size 1024` dá mais resolução à rede (~0,3 s e ~270 MB de RAM a mais); o ganho de qualidade **não foi avaliado** |
| Traços muito curtos (cabelo, texturas) | Viram muitos traços e muitas pausas de caneta | Subir `min_length` (slider Detalhes) |
| Primeira chamada após ligar o PC | Deve levar mais que ~1 s, porque o PyTorch (772 MB) sai do disco (não medido) | Tempo limite folgado; o cliente usa 120 s |

## Relação com a "linha central sem IA"

O traçado por linha central **não depende da IA**. Numa imagem que já tem line
art escura (desenho a nanquim, mangá em preto e branco), dá para passar a
própria imagem em tons de cinza para `lines_to_strokes` e ganhar o mesmo
"percorrer cada linha uma vez", sem PyTorch. Vale implementar isso primeiro no
AutoDraw: é leve, beneficia todo mundo, e a IA passa a ser só outra fonte de
imagem de linhas para o mesmo traçado.
