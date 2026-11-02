# Referência rápida da linguagem (v0.2)

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
| `entities` | `id`, `kind`, `plane`, `label`, `desc`, `box` ou `at`+`size`, `orient`, `brightness`, `saturation`, `tags`, `material`, `parts`, `detail`, `wind_parts`, `translucent` |
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
- **Materiais (base):** metal, stone, cloth, leather, skin, wood, glass, water, crystal, fur, paper, bone · **acabamento:** polished, matte, scratched, oxidized, wet, rough, glossy, mossy, dusty
- **Regras de fundo:** no_spill, no_shadow_on_key, no_gradient, subject_inside_frame

## Asserts (layout) e verify (imagem)

- `asserts`: above, below, left_of, right_of, inside, near, count, visible, facing, brightest, focal_single
- `verify`: max_colors(N), grid_aligned(N), symmetric(vertical, mín), fit_guides(tol), palette_match(ΔE), chroma_clean(), no_spill(), margin(células)

## Protocolo de planejamento

1. `scenelang plan cena.yaml` → JSON com o que o modelo deve responder (cores faltantes, linhas, regras).
2. O modelo responde um YAML: `palette: {papel: [valores]}` e/ou `guides: {linha: y}`.
3. `scenelang plan-apply cena.yaml proposta.yaml` valida (harmonia, contraste, cânone) e grava.
