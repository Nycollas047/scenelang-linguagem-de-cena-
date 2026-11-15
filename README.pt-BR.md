# scenelang — linguagem de programação para descrição de imagens

> 🇬🇧 [English version](README.md) · Português (esta página)

> A cena é o código-fonte; o prompt é o binário.

**scenelang** é uma linguagem declarativa (YAML) para descrever uma imagem como uma cena estruturada.
Um compilador transforma a cena em prompt para qualquer modelo de imagem; verificadores em código
medem o resultado. A linguagem declara a intenção e o modelo tenta: cada falha medida vira um registro estruturado (ver [`docs/DATA.md`](docs/DATA.md) — o que é gravado e o que **não** está provado).

![Esquema 2D da cena de exemplo](docs/guardia-esquema.png)

## Instalação

```
pip install -e .[dev]
scenelang validate examples/guardia.yaml
scenelang compile examples/guardia.yaml --target prose
```

## Como as peças se encaixam

```
cena.yaml ─► expand (at, preset, auto_asserts, safe_zones) ─► validate ─► IR ─┬─► prose / compact / json / regions ─► modelo de imagem
   ▲                                                                          │        (relatório de perdas por destino)
   │                                                                          ├─► render (esquema 2D · planta baixa)
   │                                                                          ├─► pack (prompt + guia, manifesto com hash)
   │                                                                          └─► level (mermaid · tiled · godot · unity)
   │
   └── correct ◄── Finding ◄── verify / locate (imagem) ── medição com confiança ── diff · patch · delta-prompt (edição incremental)
        (regra por falha, histórico, escalada, adiamento se a evidência é fraca)
```

![Planta baixa do exemplo de level design](docs/santuario-planta.png)

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
| Atalhos (v0.8) | `at` relativo, `auto_asserts`, `pose.preset` | posição por relação, ordem inferida das caixas, pose-base com ajuste fino |
| Relações (v0.8) | `interactions`, `safe_zones` | como duas entidades interagem; onde NÃO pode haver elementos |
| Pose (v0.7) | `pose` em graus, perfil anatômico, rig (`unity_humanoid`, `mixamo`) | manequim e frases de pose por junta |
| Level design (v0.9) | `graph`, `flow`, `guides.metrics`, predicados de visão/folga/alcançabilidade | mapas, interiores, rotas, cones de visão, softlock |

Referência de vocabulário: [`docs/LANGUAGE.md`](docs/LANGUAGE.md).

Representação independente de destino (experimental): [`docs/UNIVERSAL_SCENE_IR.md`](docs/UNIVERSAL_SCENE_IR.md).

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
| `compile … --target compact --token-budget N` | Poda o prompt por prioridade até caber em N tokens e declara o que saiu como perda. |
| `pack CENA [--strict --guide-style blocks\|seg]` / `unpack --check` | Prompt + guia (ou PNG único) com manifesto e hash canônico; confere a integridade na volta. |
| `locate` / `correct` | Localiza entidades na imagem (5 estados, com confiança) e gera o próximo prompt de correção, com histórico. |
| `diff` / `patch` / `delta-prompt` | Compara cenas, aplica edições endereçadas e escreve só o prompt do que mudou. |
| `pose --export unity_humanoid\|mixamo` | Folha de pose e exportação de nomes de ossos (sem calibração). |
| `render CENA --style floorplan` | Planta baixa: paredes duplas, portas, coberturas, rotas, cones, escala e grafo. |
| `level CENA --export mermaid\|tiled\|godot\|unity` | Exporta o grafo e o blockout. |
| `bench plan\|record\|report` | Estrutura de benchmark (convencional × completa × compacta × incremental); métricas offline. |
| `project init\|layer\|add\|status\|round\|export` | Espaço de trabalho: onde cada tela mora, o que já foi medido, o próximo passo; `export` gera o JSONL de dados ([`docs/DATA.md`](docs/DATA.md)). |
| `scenelang-mcp` | Servidor MCP: o modelo escreve, valida, compila, mede e corrige sem copiar arquivos. Há também `skill/scenelang/SKILL.md`. |
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
- `examples/interior_santuario_level.yaml` — level design: grafo com porta trancada, rotas, cone de visão, métrica em células e 29 asserts (visão, cobertura, folga, softlock, caminhos independentes).
- `examples/dark_fantasy_chefe.yaml` — arte conceitual de chefe (pose, interações, zona de respiro, atmosfera).
- `examples/dataset/sample.jsonl` — 3 registros de exemplo do formato de dados (caixas estimadas pelo autor; mostra o **formato**, não um resultado).
- `examples/minecraft_dungeon_puzzle.yaml` — dungeon de quebra-cabeça para Minecraft (1 célula = 1 bloco, 3 puzzles encadeados por chaves, 54 asserts, `requires` e `no_softlock`).

## Status

**Versão 0.9 (experimental).** 475 testes passando, 2 ignorados (Python 3.15 neste checkout; a suíte ainda não foi executada em 3.10, o mínimo declarado). Histórico: [`docs/AUDITORIA.md`](docs/AUDITORIA.md), referência: [`docs/LANGUAGE.md`](docs/LANGUAGE.md), dados: [`docs/DATA.md`](docs/DATA.md).

**O que já foi medido (pequeno, informal, feito pelo autor)**
- Dungeon de Minecraft, 3 imagens por braço, comparação visual: prompts compilados da cena, com guia de composição, não geraram painéis de interface inventados (0/3) contra um prompt escrito à mão (3/3), e puseram as chaves nas salas declaradas (3/3). O prompt à mão foi escrito pelo mesmo autor e não citava esses itens.
- Cena de chefe (arte conceitual), 1 imagem por braço: os prompts compilados reproduziram detalhes por entidade que o prompt à mão resumiu (musgo num pilar, correntes no outro); o guia de composição não deu vantagem clara ali.
- Um teste de ponta a ponta com duas rodadas (v0.7.1): 5 de 6 restrições espaciais na primeira, 6 de 6 após `correct`. **Um caso**, não estatística.
- Defeitos reais achados e corrigidos por teste e por fuzzing (entrada malformada que quebrava o validador; linhas de proporção de personagem aparecendo no prompt de um mapa).

**O que ainda não está provado ou pronto**
- Nenhum resultado estatístico: 1–3 imagens por condição, 2 cenas; o gerador não foi registrado nessas rodadas. As caixas foram estimadas pelo autor, não são independentes.
- **Nenhum modelo foi treinado com esses dados**; a utilidade para treino é hipótese ([`docs/DATA.md`](docs/DATA.md)).
- O benchmark contra um gerador real **não foi executado** em escala: não há número de redução de tentativas ou de custo. O prompt completo gasta mais tokens que um prompt ingênuo (~3,7× no exemplo do sapo mago; use `--token-budget` ou o destino `compact`).
- `seg` desenha retângulos, não máscaras; localizar por cor é frágil (o sistema recusa decidir quando a evidência é fraca).
- Conversão de pose para rigs traz só os nomes dos ossos, sem calibração.
- Exportador Godot (`.tscn`) não foi aberto no Godot; LDtk não é suportado.
- `safe_zones` aparece no esquema, mas ainda não no guia do `pack`.
- O espaço de trabalho (`project`) ainda não tem componentes reutilizáveis, camadas com ordem/visibilidade nem vocabulário de interface.

A linguagem é neutra quanto a fornecedor e não contém mecanismos para contornar políticas de uso de modelos.
