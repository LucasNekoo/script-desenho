# Documentação do autodraw-lineart

Ferramenta que extrai *line art* de ilustrações com IA (Anime2Sketch, em CPU)
para o AutoDraw, rodando em processo separado. O [README principal](../README.md)
é o resumo; aqui está o detalhe.

| Documento | Responde a |
| --- | --- |
| [Arquitetura](arquitetura.md) | Como a ferramenta funciona por dentro, do comando à imagem de linhas |
| [Contrato v1](contrato.md) | O que exatamente cada comando aceita e devolve (a especificação que o AutoDraw segue) |
| [Integração com o AutoDraw](integracao-autodraw.md) | Como ligar a ferramenta no AutoDraw, passo a passo, com resultados medidos |
| [Desempenho e recursos](desempenho.md) | Quanto custa em tempo, memória e disco, e como ajustar |
| [Segurança](seguranca.md) | O incidente no projeto original e as proteções adotadas |
| [Decisões](decisoes.md) | Por que as coisas são como são (e o que foi descartado) |
| [Desenvolvimento](desenvolvimento.md) | Ambiente, testes, CI, como adicionar modelos e publicar mudanças |

## Ordem de leitura sugerida

* **Vai integrar no AutoDraw?** [Contrato](contrato.md) → [Integração](integracao-autodraw.md).
* **Vai mexer nesta ferramenta?** [Arquitetura](arquitetura.md) → [Desenvolvimento](desenvolvimento.md) → [Segurança](seguranca.md).
* **Quer entender se vale a pena?** [Integração § Resultados](integracao-autodraw.md#resultados-medidos) → [Desempenho](desempenho.md).

## Estado atual (versão 0.1.1, contrato 1)

* Pronto e testado: os três comandos (`check`, `extract`, `download`), os dois
  modelos (`default`, `improved`), a conferência dos pesos e os exemplos de
  integração. 35 testes; CI verde em Linux e Windows (Python 3.10 e 3.13).
* **Integrado no AutoDraw** (branch `developer`): opção "Linhas por IA" nos
  modos `linhas` e `misto`. Veja [Integração](integracao-autodraw.md), com os
  resultados medidos pelo caminho real.
* Limitação principal: ilustrações de **fundo escuro com efeitos de luz** geram
  ruído (veja [Integração § Limitações](integracao-autodraw.md#limitações-e-como-contornar)).

## Onde este código vive

Na branch órfã `autodraw-lineart` do repositório
[LucasNekoo/script-desenho](https://github.com/LucasNekoo/script-desenho). É um
histórico independente de `main`/`developer` e **não deve ser mesclado** neles
(veja [Decisões § D2](decisoes.md#d2-branch-órfã-no-repositório-do-autodraw)).
