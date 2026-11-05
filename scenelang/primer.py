"""Cartilha curta (para o modelo) e tabela de vocabulário (máquina e gente)."""
from __future__ import annotations

from . import character as CH
from . import fx, guides
from . import materials as M
from . import vocab as V
from .verify import NAMES as VERIFIERS


def vocab() -> dict:
    """Todos os vocabulários fechados, por nome. Fonte única da cartilha, de `vocab --json` e dos avisos de typo."""
    return {
        "entity.kind": list(V.KINDS), "entity.plane": list(V.PLANES), "entity.orient": list(V.DIRECTIONS),
        "grid.kind": list(V.GRIDS), "canvas.shape": list(V.CANVAS_SHAPES),
        "camera.angle": list(V.ANGLES), "camera.lens": list(V.LENSES),
        "light.role": list(V.LIGHT_ROLES), "level": list(V.LEVELS), "anchor": list(V.ANCHORS),
        "assert.predicate": list(V.PREDICATES), "guides.canon": list(guides.CANONS),
        "background.mode": list(fx.BG_MODES), "background.alpha": list(fx.ALPHA_METHODS),
        "atmosphere.mood": list(fx.MOODS), "atmosphere.weather": list(fx.WEATHERS), "wind.strength": list(fx.WIND_STRENGTH),
        "material.base": list(M.BASES), "material.finish": list(M.FINISHES), "material.wear": list(M.WEARS),
        "material.fabric": list(M.FABRICS), "material.weave": list(M.WEAVES), "material.drape": list(M.DRAPES),
        "scales.pattern": list(M.SCALE_PATTERNS), "scales.size": list(M.SCALE_SIZES), "scales.edge": list(M.SCALE_EDGES),
        "character.age_group": list(CH.AGES), "skin.tone": ["1..10 (escala Monk)"], "skin.undertone": list(CH.UNDERTONES),
        "skin.marks": list(CH.MARKS), "hair.texture": list(CH.HAIR_TEXTURE), "hair.length": list(CH.HAIR_LENGTH),
        "eyes.shape": list(CH.EYE_SHAPE), "face.shape": list(CH.FACE_SHAPE), "body.build": list(CH.BUILD),
        "body.height": list(CH.HEIGHT), "body.proportion": list(CH.PROPORTION), "body.posture": list(CH.POSTURE),
        "verify": list(VERIFIERS),
    }


def _row(label: str, key: str, v: dict) -> str:
    return f"- **{label}**: " + ", ".join(v[key])


def primer() -> str:
    v = vocab()
    return f"""# scenelang — cartilha (uma página)

Você escreve uma **cena em YAML**; o compilador a transforma em prompt. Comece por `scenelang new <modelo>`
(sprite, splash, emblem, character-sheet) e edite. Valide com `scenelang validate cena.yaml --json`: cada erro traz
`accepted` (valores válidos) e, havendo palpite seguro, `fix` — `validate --fix` aplica. Formas curtas são aceitas
(`canvas: "16:9"`, `style: "texto"`, `pixel_grid: 64`, `verify: [grid_aligned]`).

## Esqueleto mínimo (o resto é opcional)
```yaml
scene: "Nome"
canvas: {{ratio: "16:9"}}              # pixel art: {{ratio: "1:1", pixel_grid: 64}} (inteiro = células na largura)
style: "estilo em uma frase"           # grid: golden é o padrão
intent: {{emotion: "...", story: "...", focal: fox.face}}   # UM foco: entidade ou entidade.âncora
asserts: ["above(moon, fox)", "visible(fox)"]
entities:
  - id: fox                           # slug
    label: "a raposa"                 # SAI NO PROMPT: escreva em português, com artigo (o/a/os/as)
    kind: creature
    desc: "raposa laranja de pé, de perfil"
    plane: midground                  # background | midground | foreground
    box: [x, y, w, h]                 # 0..1; y cresce para baixo; x para a direita (lado de quem VÊ)
    brightness: max                   # só UMA entidade pode ser max (o foco)
    # blocos que ficam DENTRO da entidade: character, material, parts, wind_parts, detail
```
Âncoras: {", ".join(v["anchor"])}. Asserts: `above|below|left_of|right_of|inside|near(a, b)`, `visible(a)`, `facing(a, left)`,
`brightest(a)`, `count(kind) >= 2`, `focal_single`.

## Regras que mais geram erro
1. Direções e lados são **da tela** (esquerda = esquerda de quem olha). `wind.direction` é **para onde o vento sopra**
   (vento vindo da esquerda = `right`).
2. Cores: `"#rrggbb"`, `{{rgb: [..]}}`, `{{cmyk: [..]}}` (0–100), `{{hsl: [..]}}` ou `@nome` (tabela `colors: {{azul_noite: "#1a2350"}}`).
3. Vocabulário é **fechado** (lista abaixo; o erro mostra os aceitos). Cores citadas por nome em PT valem em `hair.color` etc.
4. Não nomeie na descrição uma cor que a paleta contradiz (o validador avisa).
5. `character` descreve atributos um a um; `heritage` é texto livre e **nunca** gera traços sozinho.
6. `lock: [palette, fox]` congela o que já está bom ao refinar.
7. `verify: chroma_clean/no_spill` exigem `background: {{mode: chromakey}}`; `grid_aligned` exige `canvas.pixel_grid`.
   `palette.count` vai de 2 a 16 (cores a escolher); `max_colors(n)` limita a imagem inteira.
8. Luz vai em `lights:` (`- {{role: key, color: "quente", source: moon, hits: [fox]}}`); `source` é o id de uma entidade ou um ponto da grade
   (`pt_ul`, `pt_ur`, `pt_ll`, `pt_lr`).
9. Centralizar = `x = (1 − w) / 2`. `brightness`/`saturation`: {", ".join(v["level"])} (saturation usa muted no lugar de low).
10. `palette.count` é o TOTAL de cores (fixas + escolhidas), de 2 a 16; harmony: monochromatic, analogous, complementary, triadic, free.
11. `guides.canon` (cabeças de altura): chibi 2, stylized 4, child 5, realistic 7.5, heroic 8, ou `{{heads_tall: 3}}`. Com `guides.canon`, omita `body.proportion`.

## Camadas opcionais
| Para… | Onde | Exemplo |
|---|---|---|
| escolher cores | `palette` (topo) | `{{mode: model_picks, count: 5, harmony: triadic}}` |
| proporção e posição | `guides` (topo) | `{{subject: fox, canon: stylized}}` — canon: {", ".join(v["guides.canon"])} ou `{{heads_tall: 4}}` |
| recortar fundo | `background` (topo) | `{{mode: chromakey}}`: a cor da chave é escolhida longe da sua paleta; para forçar, `key: "#00ff00"` |
| pose (anatomia em graus) | `pose` (na entidade) | `{{body_yaw: 135, joints: {{right_elbow: 90, neck: {{turn: -60}}}}}}` — esquerda/direita do personagem; fora da faixa humana é erro |
| onde ficou na imagem | `signature` (na entidade) + `scenelang locate` | `signature: ["#a42625"]`: cor que identifica a entidade; o código mede a posição e acusa espelhamento |
| clima e vento | `atmosphere` (topo) | `{{mood: epic, weather: storm, wind: {{direction: right, strength: high}}}}`; entidade: `wind_parts: [cape]` |
| tecido/material de uma peça | `parts` (entidade): cada peça é uma ficha com `base`/`fabric`/`scales` (ao menos um), `finish`, `wear`, `sheen`, `color`, `pattern` (texto livre) | `parts: {{cape: {{fabric: wool, weave: plain, drape: flowing, color: "#2850d2"}}}}` |
| escamas | `parts` (entidade) | `parts: {{skin: {{scales: {{pattern: overlapping, size: medium, sheen: high, gradient: {{from: "#14502d", to: "#d4a528"}}, coverage: [back, tail]}}}}}}` |
| pessoa/criatura | `character` (entidade); campos: age_group, heritage (texto livre, sem prefixo), skin, hair, eyes {{color, shape}}, face, facial_hair, body {{build, height, shoulders, waist, hips, limbs, posture, proportion}}, features | `{{age_group: elder, skin: {{tone: 3, marks: [wrinkles]}}, hair: {{texture: wavy, color: branco}}, facial_hair: {{type: beard, length: long, color: branco}}, body: {{build: slim, proportion: stylized}}}}` |
| medir a imagem | `verify` (topo) | `["max_colors(16)", grid_aligned, chroma_clean, "margin(2)", fit_guides, "palette_match(10)"]` — `margin(n)` em células |
Escamas: sem `coverage` cobrem a peça toda; com `coverage: [back, tail]` o resto fica sem escamas. Bordado/estampa de uma cor: `weave: embroidered` + cor do tecido em `color`; detalhe de outra cor vai em `desc`.

## Vocabulário fechado
{_row("kind", "entity.kind", v)}
{_row("orient", "entity.orient", v)}
{_row("camera.angle", "camera.angle", v)} | {_row("lens", "camera.lens", v)}
{_row("mood", "atmosphere.mood", v)}
{_row("weather", "atmosphere.weather", v)}
{_row("wind.strength", "wind.strength", v)}
{_row("material.base", "material.base", v)}
{_row("fabric", "material.fabric", v)}
{_row("weave", "material.weave", v)}
{_row("drape", "material.drape", v)}
{_row("finish", "material.finish", v)}
- **sheen**: low, normal, high, max
{_row("scales.pattern", "scales.pattern", v)}
{_row("scales.size", "scales.size", v)}
{_row("age_group", "character.age_group", v)}
{_row("hair.texture", "hair.texture", v)} | {_row("hair.length", "hair.length", v)}
{_row("body.build", "body.build", v)} | {_row("body.proportion", "body.proportion", v)}
{_row("body.height", "body.height", v)}
- **skin**: `tone` 1–10 (Monk), `undertone` {", ".join(v["skin.undertone"])}, `marks` {", ".join(v["skin.marks"])}
- **verify**: {", ".join(v["verify"])}

## Fluxo
`new` → editar → `validate --fix` → `compile --target prose|json|regions` → gerar → `verify`/`cutout`/`snap`/`eval-form` → refinar com `lock`.
"""
