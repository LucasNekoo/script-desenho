# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/);
versões em [SemVer](https://semver.org/lang/pt-BR/). O número do **contrato**
(campo `contract` do JSON) é independente da versão do pacote; veja
[docs/contrato.md](docs/contrato.md#versionamento).

## [0.1.1] - 2026-09-23 · contrato 1

### Corrigido
- Erros de argumento (falta de `--out`, modelo ou comando inexistente) agora
  respondem com a linha JSON do contrato (`"error": "usage"`, código 2), em vez
  do texto padrão do argparse no stderr.
- `download`: o progresso do `gdown` vai para o stderr; o stdout fica só com a
  linha JSON.
- `check` com falha passa a trazer `error` e `message` no topo, como qualquer
  outro erro.

### Adicionado
- `examples/cliente_autodraw.py`: cliente de referência do contrato (só
  biblioteca padrão), pronto para copiar no AutoDraw.
- `examples/linhas_para_tracos.py`: limiar + linha central, o pós-processamento
  de referência do AutoDraw; extra `[examples]`.
- Documentação detalhada em `docs/` (arquitetura, contrato, integração,
  desempenho, segurança, decisões, desenvolvimento) e figuras em `docs/img/`.
- Testes dos exemplos (35 no total).

### Alterado
- CI usa `actions/checkout@v7` e `actions/setup-python@v7` (Node 24).

## [0.1.0] - 2026-09-23 · contrato 1

### Adicionado
- Comandos `check`, `extract` e `download`, com uma linha JSON por chamada e
  códigos de saída por tipo de erro.
- Modelos `default` e `improved` do Anime2Sketch em CPU; definição da rede
  copiada do commit `1c1a2ed` do projeto original.
- Pesos conferidos por tamanho e SHA-256 e carregados com `weights_only=True`.
- CI em Linux e Windows com PyTorch só para CPU.
