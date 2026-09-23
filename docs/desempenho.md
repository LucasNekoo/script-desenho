# Desempenho e recursos

Tudo medido numa máquina com CPU de 12 threads, 30 GB de RAM, **sem GPU**
(CachyOS/Linux, Python 3.14, PyTorch 2.14 CPU), salvo indicação.

## Resumo

| Recurso | Custo | Observação |
| --- | --- | --- |
| Tempo por imagem | **~1,0–1,4 s** por chamada | Uma vez por imagem carregada, não por ajuste |
| Memória | **~680 MB** (`default`) · ~1,8 GB (`improved`) | Só durante a chamada; volta ao sistema quando o processo termina |
| Disco | **~1,2 GB** (ambiente mínimo 1,0 GB + pesos 218 MB) | O AutoDraw sozinho ocupa ~330 MB |
| GPU | nenhuma | Tudo em CPU |

## Tempo

### Só a rede (`seconds.inference`), imagem de 512 px

| Threads | `default` | `improved` |
| --- | --- | --- |
| 1 | 0,25 s | 0,82 s |
| 2 | 0,14 s | 0,48 s |
| 4 | 0,09 s | 0,36 s |
| 6 | 0,07 s | 0,32 s |

Com `--size 1024` (modelo `default`): 0,31 s com 6 threads, 0,58 s com 2.

### A chamada completa, como o AutoDraw vai sentir

| Etapa | `default` | `improved` |
| --- | --- | --- |
| Iniciar processo + importar PyTorch + conferir e carregar pesos (`seconds.load`) | ~0,7 s | ~0,8 s |
| Rede (4 threads) | ~0,1 s | ~0,37 s |
| **Total medido de fora** (`subprocess.run`) | **~1,0–1,1 s** | **~1,3–1,4 s** |
| Linha central no AutoDraw (`lines_to_strokes`) | 14–49 ms | idem |

Só importar o PyTorch custa ~0,57 s. É o preço de rodar em processo separado,
pago uma vez por imagem.

### `check`

| Modo | Tempo |
| --- | --- |
| `--skip-verify` (só existência e tamanho) | ~0,03 s |
| Completo (SHA-256 dos dois arquivos, 410 MB) | ~0,2 s |

## Memória (pico)

| Configuração | Pico |
| --- | --- |
| `default`, 512 px | ~680 MB |
| `default`, 1024 px | ~870–950 MB |
| `improved`, 512 px | ~1,8 GB |

O AutoDraw sozinho fica em ~250 MB. Como a ferramenta roda em outro processo,
o pico acontece por ~1 s e depois some; com o jogo aberto, é isso que importa.

## Disco

| Item | Tamanho |
| --- | --- |
| **Ambiente mínimo de usuário** (`torch` + `autodraw-lineart[download]`) | **1,0 GB** (medido) |
| ↳ só o PyTorch CPU | 188 MB de download, 772 MB instalado |
| Ambiente de desenvolvimento (`[dev,download]`: + OpenCV, scikit-image, SciPy) | 1,4 GB |
| `netG.pth` (`default`) | 218 MB |
| `improved.bin` | 192 MB (opcional) |
| scikit-image (só para o exemplo de traçado) | 14 MB de download |

Instale sempre do índice **CPU** (`--index-url https://download.pytorch.org/whl/cpu`);
sem ele, no Linux, o pip traz a versão com CUDA, muitas vezes maior.

## Orçamento de hardware

O alvo não é a máquina de desenvolvimento, e sim o notebook de quem joga,
**com o Roblox aberto ao mesmo tempo**: 2 a 4 núcleos, 8 GB de RAM e uma GPU
integrada ocupada com o jogo. Diante disso:

| Limite do AutoDraw | autodraw-lineart | Situação |
| --- | --- | --- |
| Processamento < 1 s num núcleo | 0,25 s de rede (1 thread) + ~0,7 s de carga ≈ 0,95 s aqui | ⚠️ no limite nesta máquina; num notebook fraco deve passar de 1 s. Aceitável por acontecer uma vez por imagem |
| RAM < 500 MB | ~680 MB por ~1 s | ⚠️ acima, mas passageiro; `improved` (1,8 GB) só com aviso |
| Instalação < 400 MB | ~1,2 GB | ❌ por isso a ferramenta é **opcional** e vive fora do AutoDraw |
| Sem GPU obrigatória | nenhuma | ✅ |

## Como ajustar

* **Threads:** o padrão é metade dos núcleos, no máximo 4. Num notebook de 4
  núcleos com o jogo aberto, `--threads 2` é um bom meio-termo (0,14 s de rede).
* **Modelo:** use `default`. O `improved` custa 3–4× o tempo e 2,6× a memória
  e só ajuda em fundos escuros, onde nenhum dos dois ficou bom (veja a
  [Integração](integracao-autodraw.md#limitações-e-como-contornar)).
* **Tamanho:** 512 é o padrão do modelo. 1024 custa ~0,25 s e ~270 MB a mais;
  o ganho de qualidade não foi avaliado.

## Como reproduzir as medições

```bash
# tempo e resposta de uma chamada, medidos de fora
python - <<'EOF'
import subprocess, time, json
t = time.perf_counter()
r = subprocess.run(["autodraw-lineart", "extract", "imagem.png", "--out", "linhas.png", "--threads", "2"],
                   capture_output=True, text=True)
print(f"{time.perf_counter() - t:.2f} s", json.loads(r.stdout)["seconds"])
EOF

# pico de memória (Linux; precisa do pacote "time")
/usr/bin/time -v autodraw-lineart extract imagem.png --out linhas.png 2>&1 | grep "Maximum resident"
```

Em CI (runners do GitHub, sem pesos), a suíte inteira leva ~40 s no Linux e
~1,5 min no Windows, quase tudo instalando o PyTorch.
