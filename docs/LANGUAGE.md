# Referência rápida da linguagem

## Estrutura de uma cena

| Chave | Papel |
|---|---|
| `scene` | nome |
| `canvas` | `ratio` (ex.: 16:9) e `shape`: rect, circle, ellipse |
| `grid` | golden (áurea) ou thirds (terços) |
| `style` | `base` e `mix` (percentuais somando 100) |
| `intent` | `focal` (referência), emoção, história |
| `camera`, `palette`, `lights` | enquadramento, cor e luz |
| `entities` | id, kind, plane, label, desc, `box` ou `at`+`size`, `orient`, brightness, saturation, tags |
| `gaze` | ordem do olhar (começa no foco) |
| `asserts` | condições verificáveis |
| `avoid` | negações (viram afirmações) |
| `priority_boost` | preenchido pelo ciclo de avaliação |

## Vocabulário fechado
- **Direções** (do ponto de vista de quem vê): up, down, left, right, up_left, up_right, down_left, down_right, toward_camera, away
- **Planos:** background, midground, foreground
- **Referências:** `entidade`, `entidade.tip|base|...` (âncoras), regiões 3×3, pontos `pt_ul pt_ur pt_ll pt_lr`
- **Asserts:** above, below, left_of, right_of, inside, near, count, visible, facing, brightest, focal_single
- **Tags de rejeição:** direção, luz, proporção, estilo, anatomia, enquadramento

Veja `examples/guardia.yaml` para uma cena completa.
