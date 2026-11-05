# Referência rápida da linguagem (v0.3)

## Estrutura de uma cena

| Chave | Papel |
|---|---|
| `scene`, `version` | nome e versão |
| `canvas` | `ratio`, `shape` (rect, circle, ellipse), `pixel_grid` (células na largura, 4–512) |
| `grid` | `kind`: golden (áurea) ou thirds (terços) |
| `style` | `base` e `mix` (percentuais somando 100) |
| `intent` | `focal` (referência), `emotion`, `story` |
| `colors` | cores nomeadas, usadas como `"@nome"` |
| `palette` | `dominant`, `accent`, `accent_use`, `notes`; e `mode` (fixed, model_picks), `space` (rgb, cmyk, hsl), `count`, `harmony`, `colors`, `constraints` (contrast_min, min_distance, max_colors), `proposal` |
| `guides` | `mode` (fixed, model_proposes), `subject`, `canon`, `axis`, `lines`, `margin`, `proposal` |
| `background` | `mode` (scene, chromakey), `key` (auto ou cor), `alpha` (chroma, difference), `tolerance`, `edge`, `rules` |
| `atmosphere` | `mood {name, level}`, `weather`, `wind {direction, strength}` |
| `materials`, `detail` | biblioteca de materiais; orçamento de detalhe por zona |
| `camera`, `lights`, `gaze` | enquadramento, luz, ordem do olhar |
| `entities` | `id`, `kind`, `plane`, `label`, `desc`, `box` ou `at`+`size`, `orient`, `brightness`, `saturation`, `tags`, `character`, `material`, `parts`, `detail`, `wind_parts`, `translucent` |
| `asserts` | condições de layout (sem imagem) |
| `verify` | medições na imagem gerada |
| `lock` | partes a manter iguais à versão anterior |
| `extends`, `import` | herança de cena e bibliotecas |

## Cores

`"#rrggbb"`, `{rgb: [0-255 ×3]}`, `{cmyk: [0-100 ×4]}`, `{hsl: [0-360, 0-100, 0-100]}` ou `"@nome"`.
Harmonias: monochromatic, analogous, complementary, triadic, free.

## Vocabulário fechado

- **Direções** (de quem vê): up, down, left, right, up_left, up_right, down_left, down_right, toward_camera, away
- **Planos:** background, midground, foreground
- **Cânones de proporção:** chibi (2), stylized (4), child (5), realistic (7,5), heroic (8) ou `{heads_tall: N}`
- **Linhas-guia:** head_top, eye, chin, shoulder, waist, knee, baseline
- **Moods:** serene, tense, melancholic, epic, mysterious, joyful, ominous, cozy · **clima:** clear, rain, snow, fog, storm, dust · **vento:** calm, low, normal, high, max
- **Materiais (base):** metal, stone, cloth, leather, skin, wood, glass, water, crystal, fur, paper, bone, scales, feathers, chitin, shell, rubber, plastic, ceramic, wool · **acabamento:** polished, matte, scratched, oxidized, wet, rough, glossy, mossy, dusty
- **Regras de fundo:** no_spill, no_shadow_on_key, no_gradient, subject_inside_frame

## Asserts (layout) e verify (imagem)

- `asserts`: above, below, left_of, right_of, inside, near, count, visible, facing, brightest, focal_single
- `verify`: max_colors(N), grid_aligned(N), symmetric(vertical, mín), fit_guides(tol), palette_match(ΔE), chroma_clean(), no_spill(), margin(células)

## Protocolo de planejamento

1. `scenelang plan cena.yaml` → JSON com o que o modelo deve responder (cores faltantes, linhas, regras).
2. O modelo responde um YAML: `palette: {papel: [valores]}` e/ou `guides: {linha: y}`.
3. `scenelang plan-apply cena.yaml proposta.yaml` valida (harmonia, contraste, cânone) e grava.

## Personagem (`entities[].character`)

Atributos descritivos e independentes. Nada é deduzido de `heritage` (texto livre do autor, até 80 caracteres).

| Campo | Valores |
|---|---|
| `age_group` | child, teen, young_adult, adult, middle_aged, elder |
| `skin` | `tone` 1–10 (escala Monk, cor de referência embutida) ou `color` exata; `undertone` cool/neutral/warm/olive; `finish` matte/dewy/weathered/smooth; `marks` freckles, moles, scars, vitiligo, birthmark, wrinkles, tattoos, blush, sun_spots |
| `hair` | `texture` straight/wavy/curly/coily, `length` bald…very_long, `density`, `color`, `style` (texto) |
| `facial_hair` | `type` beard/mustache/stubble/goatee/sideburns/beard_and_mustache, `length`, `color`, `style` |
| `eyes`, `face` | cor e formato dos olhos; formato do rosto, nariz, lábios, mandíbula |
| `body` | `build`, `height`, `shoulders`, `waist`, `hips`, `limbs`, `posture`, `proportion` (chibi/stylized/realistic/heroic, avisa se destoa de `guides.canon`) |
| `features` | parte (ears, horns, tail, wings, claws…) → texto livre |

A cor da pele entra nas cores de referência da escolha automática da chave do fundo.

## Pose em graus (`entities[].pose`, v0.4)
Evita anatomia impossível: cada junta recebe um ângulo e a linguagem rejeita o que o corpo humano não faz.
- `body_yaw`: -180..180 (0 de frente, 90 perfil para a direita da imagem, 180 de costas).
- `joints`: `neck`, `spine`, `{left,right}_{shoulder,elbow,wrist,hip,knee,ankle}`; número = eixo principal, mapa = eixos
  (`flex`, `abduct`, `rotate`, `turn`, `twist`, `tilt`, `side`). Esquerda/direita são do personagem; 0° = neutro.
- `hold`: o que cada mão/pé segura (`left_hand`, `right_hand`, `left_foot`, `right_foot`).
- Fora da faixa: erro com `fix` (limita ao máximo); perto do limite: aviso; corpo de costas sem girar o pescoço: aviso.

## Onde as coisas ficaram na imagem (v0.4)
`scenelang locate cena.yaml imagem.png [--boxes achados.json]` mede a caixa de cada entidade na imagem pronta, compara com a declarada,
acusa **espelhamento** e reavalia os asserts de posição (`left_of`, `above`, `inside`...) sobre as caixas medidas.
- `signature: ["#a42625", "#551014"]` (na entidade, 1 a 3 cores): o código acha esses pixels sem modelo de visão; serve quando a cor é distintiva.
- `--boxes`: caixas `{id: [x, y, w, h]}` de quem olhou a imagem; `locate cena.yaml --form` gera o pedido para um modelo de visão.
- `scenelang render` desenha um esqueleto de palitos para entidades com `pose` (D = lado direito do personagem, E = esquerdo).

## Relatório de perdas (v0.4)
`scenelang compile cena.yaml --loss` lista o que o backend não leva ao gerador (`lost`, `approx`, `unchecked`);
`--strict` falha com código 3 se há parte sem tradução ou a cena não tem asserts. O backend `regions` agora leva
intenção, iluminação, detalhes e acabamento no `global_prompt` e as camadas (personagem, pose, material, vento) em cada região.

## Tecidos e escamas (em `material`, `parts` ou `materials`)

- Tecido: `fabric` (cotton, linen, silk, satin, wool, velvet, denim, lace, canvas, tulle, leather, burlap, chiffon, felt, tweed, corduroy, suede, fleece, knit, mesh), `weave` (plain, twill, checked, striped, herringbone, polka, floral, embroidered, brocade, quilted, pleated, ribbed, patched), `drape` (stiff, structured, flowing, heavy, clingy, billowing, tattered). `base: cloth` é implícito.
- Escamas: `scales: {pattern, size, edge, sheen, gradient {from,to}, color, coverage}`. `pattern`: overlapping, hexagonal, diamond, plate, granular, keeled, rounded; `size`: tiny…huge; `edge`: smooth, serrated, spiked, rough. `base: scales` é implícito; `coverage` limita às partes citadas.
- Avisos de contradição: lona (canvas) com caimento fluido, granular grande, caimento rígido em peça movida pelo vento.

## Uso por modelos de linguagem

| Comando | Para quê |
|---|---|
| `primer` | cartilha de uma página gerada do vocabulário |
| `vocab [--json]` | todos os vocabulários fechados |
| `new [modelo] [--out F]` | cena inicial: sprite, splash, emblem, character-sheet |
| `validate --fix [--out F]` | aplica correções seguras (typo de valor ou de campo, com `fix` no diagnóstico) |

Formas curtas aceitas (e registradas em `defaults_applied` na API): `canvas: "16:9"`, `style: "texto"`, `grid` ausente (golden), `pixel_grid: "64x64"`, `label` ausente (vem do id), `atmosphere.mood: epic`, `verify: [grid_aligned]`, apelidos em português (`kind: personagem`, `plane: fundo`, `grid: terços`), `chroma_key`, `sheen: strong`, campos de `character` soltos na entidade.
`scenelang.api` oferece `validate`, `fix`, `compile_scene`, `plan`, `primer`, `vocab`, `new` com retorno JSON-serializável.

## Medir e pós-processar (v0.3)

`snap` (grade real, limite de cores, paleta exata, encaixe nas guias, fundo transparente), `sheet-prompt`/`sheet-measure` (variantes lado a lado, medidas por coluna), `verify symmetric(vertical, 0.8, legs)` (só pernas, ignora capa/cabelo ao vento) e avisos de contradição (paleta × descrição, simetria × vento, margem × sujeito).
