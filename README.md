# scenelang — linguagem de programação para descrição de imagens

> A cena é o código-fonte; o prompt é o binário.

**scenelang** é uma linguagem declarativa (YAML) para descrever uma imagem como uma cena estruturada:
quadro, grade de composição, entidades com posição, plano e orientação, luz, câmera, paleta, ordem do olhar
e **asserts** verificáveis. Um compilador transforma a cena em prompt para qualquer modelo de imagem
(texto, JSON ou regiões), e um ciclo de avaliação reforça o que o modelo errou.

**Ideia central:** mover para código determinístico o que modelos de imagem fazem mal
(layout, direção, contagem, cor exata, recorte) e deixar ao modelo textura, luz e estilo.

![Esquema 2D da cena de exemplo](docs/guardia-esquema.png)

## Instalação rápida

```
pip install -e .[dev]
scenelang validate examples/guardia.yaml
scenelang compile examples/guardia.yaml --target prose
```

Saídas compiladas do exemplo: [`examples/out/`](examples/out/).

## Status

Versão 0.1 (experimental): núcleo funcional (validar, compilar, verificar, desenhar esquema 2D, ciclo de avaliação).
Camadas/alfa, crítico automático, previz 3D e integração com LLMs (MCP) estão no roteiro.
A linguagem é neutra quanto a fornecedor e não contém mecanismos para contornar políticas de uso de modelos.

---

```
cena.yaml ─► validate ─► IR ─┬─► prose    (modelos só de texto)
                             ├─► json     (prioridades no topo)
                             └─► regions  (caixas, pesos, prompts por região)
                                    │
                     imagem gerada ─┴─► ficha de avaliação ─► reforço ─► recompila
cena.yaml ─► check (asserts no layout) ─► render (esquema 2D SVG/PNG)
```

## Comandos

| Comando | O que faz |
|---|---|
| `python -m scenelang validate CENA [--json]` | Valida tudo numa passada: vocabulário fechado, geometria, referências, foco único, olhar, asserts. Erros trazem caminho, valor recebido, aceitos e "você quis dizer…". |
| `compile CENA --target prose\|json\|regions [--size 1344x752] [--out F]` | Compila a cena. Negações viram afirmações. |
| `check CENA` | Avalia os asserts sobre o layout (sem gerar imagem). |
| `render CENA --out F.png` | Esquema 2D: grade, caixas por plano, orientação, olhar, foco, resultado dos asserts. |
| `eval-form CENA [--round N] [--out F]` | Gera a ficha de avaliação (uma pergunta por assert). |
| `eval-apply CENA RESPOSTAS [--out F]` | Aplica sim/não + tag de rejeição; os itens que falharam sobem ao topo como "(reforço)" e entram no "LEMBRETE FINAL". |

## Fluxo

1. Escreva a cena (`examples/guardia.yaml`).
2. `validate` → `check` → `render` para conferir o layout antes de gastar uma geração.
3. `compile --target prose|json|regions` e envie ao modelo de imagem.
4. `eval-form`, responda olhando a imagem, `eval-apply`, recompile, gere de novo.

## Regras importantes

- **Direções são do ponto de vista de quem vê a imagem** (`left` = esquerda da tela). O teste 3 mostrou que "esquerda/direita" sem esse referencial é ambíguo: a lança subiu para cima e à direita e foi pontuada como `up_left`.
- Coordenadas normalizadas: x para a direita, y para baixo, `[0,1]`.
- Grade áurea: linhas em 0,381966 e 0,618034. Regiões 3×3 e 4 pontos de interesse (`pt_ul`, `pt_ur`, `pt_ll`, `pt_lr`).
- Formas de quadro: `rect`, `circle`, `ellipse` (centro e visibilidade são testados contra a forma).
- Tamanhos em pixels são múltiplos de 8 (16:9 → 1344×752).
- `eval-apply` regrava o YAML sem os comentários originais.
- Só um elemento pode ter `brightness: max` (foco único); `saturation: max` só no foco.

## Asserts

`above`, `below`, `left_of`, `right_of`, `inside`, `near` (tol. 0,06 da altura do quadro), `count`, `visible`, `facing`, `brightest`, `focal_single`.

## Desenvolvimento

```
pip install -e .[dev]
pytest
```

Fora do escopo desta versão (fases seguintes): camadas/alfa, crítico automático, previz/Blender via MCP, adaptação para uso por LLMs (MCP), publicação no GitHub.
