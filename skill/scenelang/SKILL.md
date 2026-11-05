---
name: scenelang
description: Escreve, valida e compila cenas em scenelang (YAML) para gerar imagens com controle de composição, pose, paleta e estilo; mede a imagem gerada e corrige a próxima rodada. Use quando o usuário pedir uma imagem com composição, personagens, pixel art, splash art ou cena detalhada para um gerador de imagem.
---

# scenelang — a cena é o código-fonte, o prompt é o binário

Você descreve a cena em YAML; as ferramentas validam, compilam em prompt e medem a imagem depois. Declare a intenção e deixe o gerador tentar: não use isto para contornar políticas do provedor.

## Ferramentas (servidor MCP `scenelang`)

| Etapa | Ferramenta | Para quê |
|---|---|---|
| 1 | `scenelang_primer` | Cartilha de uma página (chame uma vez) |
| 2 | `scenelang_new` | Cena inicial pronta (sem argumento lista os modelos) |
| 3 | `scenelang_validate` | Todos os erros de uma vez; `fix=true` aplica as correções seguras |
| 4 | `scenelang_check_layout` / `scenelang_render_schema` | Confere os `asserts` e desenha o esquema 2D |
| 5 | `scenelang_pose_sheet` | Manequim da `pose` em graus (só para conferir a anatomia) |
| 6 | `scenelang_compile` | Prompt final (`prose`, `json`, `regions`) + o que o backend perde |
| 7 | `scenelang_pack` | Grava `prompt.txt`, `guia.png`, `cena_unica.png` |
| 8 | `scenelang_locate` / `scenelang_verify` / `scenelang_measure` | Mede a imagem gerada e prepara a próxima rodada |

Sem o servidor MCP, use a CLI equivalente: `scenelang validate|compile|pack|locate|verify|correct`.

## Fluxo

1. `scenelang_primer`, depois `scenelang_new` com o modelo mais próximo; edite em vez de escrever do zero.
2. Escreva a cena: `canvas`, `style`, `palette`, `entities` (cada uma com `id`, `kind`, `desc`, `plane`, `box: [x, y, w, h]` em frações 0..1) e `asserts`.
3. `scenelang_validate` até ficar sem erros. Leia `accepted` e `hint` de cada erro; não invente valores fora do vocabulário.
4. `scenelang_check_layout`; se algum assert falhar, ajuste as caixas.
5. `scenelang_compile` e leia a lista de perdas: o que o backend não consegue expressar. Não prometa ao usuário o que está lá.
6. Entregue o prompt (e, se o gerador aceitar imagem de referência, o guia). Veja a tabela abaixo.
7. Quando o usuário trouxer a imagem gerada, olhe-a e informe você mesmo as caixas (`boxes_json`) em `scenelang_measure`; use o resultado (`corrections`, `next_scene`, `prompt_next`) na rodada seguinte.

## Qual arquivo entregar

| Gerador | Entregue |
|---|---|
| Só prompt de texto | `prompt` (o texto), sem imagem |
| Aceita imagem de estrutura (referência, segmentação) | `guia.png` com `guide_style: seg` + o prompt |
| Chat com visão (imagem + texto) | `cena_unica.png` |
| Dúvida | O texto sozinho: guia em imagem tende a ser copiado para dentro da imagem final |

## Pose em graus

`pose` por entidade, juntas em graus (neutro = 0°), esquerda/direita são as do personagem. Exemplos de faixas: cotovelo 0..150, joelho 0..140, ombro flexão −50..180. `body_yaw` 0 = de frente, 90 = perfil olhando para a direita da imagem, 180 = de costas. Valores fora da faixa viram erro com correção sugerida.

## Regras de ouro

- Medir por cor (`signature`) é frágil: o gerador troca cores. Prefira caixas informadas por você olhando a imagem; relate por qual método cada medida foi feita.
- Geradores ignoram grade de pixels e paleta fixa. Verificações `grid_aligned`/`palette_match` reprovam com frequência; `scenelang snap` pós-processa para pixel art estrita.
- Espelhamento é variação do gerador, não erro da cena: reporte, não "corrija" a cena.
- Elementos extras que o gerador acrescenta: declare-os na cena se quiser mantê-los, ou diga que são indesejados.
- Se uma medição reprovar mas a imagem claramente está certa, o erro é da medição: diga isso ao usuário em vez de reescrever a cena.
