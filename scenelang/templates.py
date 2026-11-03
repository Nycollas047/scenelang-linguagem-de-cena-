"""Cenas iniciais prontas: o modelo copia e edita em vez de escrever do zero."""
from __future__ import annotations

TEMPLATES = {
    "sprite": '''# Sprite pixel art de personagem (fundo transparente via chroma key)
scene: "Meu sprite"
canvas: {ratio: "1:1", pixel_grid: 64}
style: "pixel art 16 bits, contorno de 1 pixel, sombreamento em blocos"
intent: {emotion: "determinação", story: "herói pronto para a aventura", focal: hero.face}
palette: {mode: model_picks, count: 5, harmony: analogous, space: rgb}
guides: {subject: hero, canon: stylized}
background: {mode: chromakey}
verify: ["max_colors(16)", grid_aligned, chroma_clean]
asserts: ["visible(hero)"]
entities:
  - id: hero
    kind: character
    desc: "herói de corpo inteiro, de frente, armadura simples e capa curta"
    plane: foreground
    box: [0.2, 0.05, 0.6, 0.9]
    brightness: max
    character:
      age_group: young_adult
      body: {build: athletic, proportion: stylized}
''',
    "splash": '''# Splash art / cena cinematográfica
scene: "Minha splash art"
canvas: {ratio: "16:9"}
grid: golden
style: "pintura digital semi-realista de alta qualidade"
intent: {emotion: "resistência serena", story: "uma guerreira diante de algo colossal", focal: hero.face}
camera: {angle: low, lens: wide}
lights:
  - {role: key, color: "fria, turquesa", source: hero, hits: [hero]}
atmosphere: {mood: epic, weather: storm, wind: {direction: right, strength: strong}}
asserts: ["left_of(hero, colossus)"]
entities:
  - id: hero
    kind: character
    desc: "guerreira de corpo inteiro, armadura e capa ao vento"
    plane: foreground
    box: [0.3, 0.25, 0.34, 0.7]
    brightness: max
    wind_parts: [cape]
    parts: {cape: {fabric: wool, drape: flowing}}
  - id: colossus
    kind: creature
    desc: "colosso de pedra emergindo do mar"
    plane: background
    box: [0.6, 0.1, 0.35, 0.6]
''',
    "emblem": '''# Emblema circular
scene: "Meu emblema"
canvas: {shape: circle, ratio: "1:1"}
grid: thirds
style: "ilustração vetorial de emblema, cores chapadas"
intent: {emotion: "calma", story: "um animal sob a lua", focal: moon.center}
asserts: ["above(moon, animal)"]
entities:
  - id: moon
    kind: light_source
    desc: "lua cheia grande com halo prateado"
    plane: background
    box: [0.55, 0.14, 0.26, 0.26]
    brightness: max
  - id: animal
    kind: creature
    desc: "raposa de pé, de perfil, olhando para a lua"
    plane: midground
    box: [0.2, 0.45, 0.4, 0.4]
''',
    "character-sheet": '''# Ficha de personagem: atributos descritos um a um (nada é deduzido da herança)
scene: "Minha ficha de personagem"
canvas: {ratio: "3:4"}
grid: golden
style: "ilustração de personagem sobre fundo cinza liso e neutro, luz suave"
intent: {emotion: "confiança", story: "retrato de corpo inteiro para referência", focal: hero.face}
asserts: ["visible(hero)"]
entities:
  - id: hero
    kind: character
    desc: "personagem de corpo inteiro, de frente, pose neutra"
    plane: foreground
    box: [0.2, 0.04, 0.6, 0.92]
    brightness: max
    character:
      age_group: adult
      heritage: "texto livre, nas suas palavras"
      skin: {tone: 6, undertone: neutral}
      hair: {texture: wavy, length: medium, color: "#3b2a20"}
      eyes: {color: castanho, shape: almond}
      body: {build: average, height: average, posture: relaxed}
    parts:
      jacket: {fabric: denim, weave: plain, drape: structured}
''',
}


def names() -> list[str]:
    return sorted(TEMPLATES)


def get(name: str) -> str:
    if name not in TEMPLATES:
        raise KeyError(name)
    return TEMPLATES[name]
