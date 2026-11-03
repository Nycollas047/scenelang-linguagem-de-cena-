# scenelang — linguagem de programação para descrição de imagens

> A cena é o código-fonte; o prompt é o binário.

**scenelang** é uma linguagem declarativa (YAML) para descrever uma imagem como uma cena estruturada.
Um compilador transforma a cena em prompt para qualquer modelo de imagem; verificadores em código
medem o resultado. A linguagem declara a intenção e o modelo tenta: cada falha medida é dado de avaliação e de treino.

![Esquema 2D da cena de exemplo](docs/guardia-esquema.png)

## Instalação

```
pip install -e .[dev]
scenelang validate examples/guardia.yaml
scenelang compile examples/guardia.yaml --target prose
```

## Como as peças se encaixam

```
cena.yaml ─► validate ─► IR ─┬─► prose / json / regions ─► modelo de imagem
   ▲                         │                                    │
   │   plan / plan-apply     └─► render (esquema 2D)              ▼
   │   (o modelo propõe        imagem ─► verify (código) ─► placar automático
   │    cores e guias)                └─► eval-form ─► eval-apply ─► reforço + trava
   └──── extends / import / sweep (variações controladas)
```

## Camadas da linguagem

| Camada | Chaves | O que controla |
|---|---|---|
| Quadro e grade | `canvas` (rect/circle/ellipse, `pixel_grid`), `grid` (áurea, terços) | formato, grade de pixels, pontos de interesse |
| Entidades | `entities` (box/at, `orient`, `brightness`, `saturation`) | posição, plano, direção, foco |
| Cor | `colors`, `palette` (`mode: fixed\|model_picks`, RGB/CMYK/HSL, harmonia, contraste) | cores exatas ou escolhidas pelo modelo |
| Guias | `guides` (cânone de cabeças, eixo, linhas, margem; `model_proposes`) | proporção e consistência |
| Fundo | `background` (`chromakey`, `alpha: chroma\|difference`) | recorte e canal alfa |
| Atmosfera | `atmosphere` (mood, clima, vento), `wind_parts` | coerência entre objetos leves e o vento |
| Materiais | `materials`, `material`/`parts` (tecido, trama, caimento, escamas), `detail` | textura por parte e orçamento de detalhe |
| Personagem | `entities[].character` (idade, herança, tom de pele, cabelo, olhos, rosto, corpo, partes) | biotipo descrito atributo por atributo, sem inferências |
| Intenção e olhar | `intent`, `gaze`, `lights`, `camera` | foco e ordem de leitura |
| Verificação | `asserts` (layout), `verify` (imagem) | critérios mensuráveis |
| Reuso | `extends`, `import`, `lock` | variantes, bibliotecas e partes travadas |

Referência de vocabulário: [`docs/LANGUAGE.md`](docs/LANGUAGE.md).

## Comandos

| Comando | O que faz |
|---|---|
| `validate CENA [--json]` | Valida tudo numa passada, com caminho, valores aceitos e "você quis dizer…". |
| `compile CENA --target prose\|json\|regions [--pass black\|white]` | Compila a cena. Negações viram afirmações. |
| `check CENA` | Avalia os asserts de layout (sem imagem). |
| `render CENA --out F.png` | Esquema 2D: grade, caixas, orientação, guias, olhar, foco. |
| `plan CENA` / `plan-apply CENA PROPOSTA` | Pedido estruturado ao modelo (cores e guias) e gravação da proposta, já validada. |
| `verify CENA IMAGEM` | Mede a imagem: cores, grade de pixels, simetria, guias, paleta, fundo, vazamento. |
| `cutout CENA IMAGEM --out F.png` / `cutout --black B --white W --out F.png` | PNG com alfa (por chave ou por diferença de duas passadas). |
| `sweep CENA --axis caminho=v1,v2,v3 --out DIR` / `sweep-score FICHA` | Variantes que mudam um eixo só; mede se a imagem seguiu a ordem. |
| `eval-form` / `eval-apply [--lock-passed]` | Ficha de avaliação, reforço do que falhou e trava do que passou. |
| `snap CENA IMAGEM --out F.png [--grid N --colors N --to-palette --fit]` | Pixel art de verdade: grade, cores, paleta exata, encaixe nas guias, fundo transparente. |
| `sheet-prompt` / `sheet-measure` | Variantes lado a lado num prompt só e medida de cada coluna. |
| `primer` / `vocab [--json]` / `new [modelo]` | Cartilha de uma página, vocabulários e cenas iniciais para o modelo escrever cenas. |
| `validate --fix [--out F]` | Aplica as correções seguras que o validador propõe (typos de valor e de campo). |

## Regras importantes

- Direções são do ponto de vista de quem vê a imagem (`left` = esquerda da tela), inclusive o vento.
- Coordenadas normalizadas: x para a direita, y para baixo, `[0,1]`.
- Pontos de interesse da grade saem com porcentagens ("a cerca de 38% da esquerda e 38% do topo"), porque os modelos leram "superior esquerdo da grade" como o canto do quadro.
- Foco único: só um elemento com `brightness: max`; só um ponto com detalhe `max`.
- CMYK → RGB é aproximado (sem perfil ICC); a cor impressa real depende do perfil.
- Elementos translúcidos (vidro, fumaça, brilho) recortam mal por chave; use `alpha: difference`.
- `eval-apply` regrava o YAML sem os comentários originais.
- Os verificadores de imagem exigem Pillow e numpy (`pip install scenelang[image]`).

## Exemplos

- `examples/guardia.yaml` — splash art 16:9, grade áurea, 11 asserts.
- `examples/emblema.yaml` — quadro circular, grade de terços, `count` com glossário.
- `examples/pixel_heroi.yaml` — pixel art 32×32 com paleta escolhida pelo modelo, guias, chromakey, vento, materiais e 7 verificadores.
- `examples/dragoa_e_cavaleira.yaml` — escrita por um modelo pequeno só com a cartilha: escamas com degradê, personagem com tom de pele, capa ao vento.
- `scenelang new sprite|splash|emblem|character-sheet` — cenas iniciais que já validam sem avisos.
- `examples/pixel_heroi_noite.yaml` — variante por `extends` + biblioteca de materiais + travas.

## Status

Versão 0.3 (experimental). Testada com modelos pequenos escrevendo cenas só com a cartilha (`scenelang primer`): de 3 rodadas de validação na primeira bateria para 2 na segunda, e cada lacuna achada virou correção. Fora desta versão: camadas separadas e crítico automático por visão, previz 3D (Blender via MCP), empacotamento MCP, mais idiomas. A linguagem é neutra quanto a fornecedor e não contém mecanismos para contornar políticas de uso de modelos.
