"""Fundo (chromakey / recorte) e atmosfera (mood, clima, vento).

background:
  mode: scene | chromakey
  key: auto | "#00ff00" | {rgb: [...]}   # cor da chave; auto escolhe a mais distante da paleta
  alpha: chroma | difference               # difference = duas passadas (fundo preto e branco)
  tolerance: 12                            # ΔE aceito como "fundo"
  edge: hard | soft
  rules: [no_spill, no_shadow_on_key, no_gradient, subject_inside_frame]

atmosphere:
  mood: {name: tense, level: high}
  weather: storm
  wind: {direction: right, strength: high}  # sempre do ponto de vista de quem vê

entidade:
  wind_parts: [cape, hair]                  # herdam a direção do vento
  wind_parts: {cape: right, hair: left}     # direção própria (conflito com o vento é erro)
  translucent: true                         # partes semitransparentes (vidro, fumaça, brilho)
"""
from __future__ import annotations

from . import color as C
from . import palette as PAL
from . import vocab as V
from .checks import enum_check, is_num, str_list, unknown_keys

BG_MODES = ("scene", "chromakey")
ALPHA_METHODS = ("chroma", "difference")
EDGES = ("hard", "soft")
BG_RULES = {
    "no_spill": "nenhuma parte do sujeito usa a cor da chave nem reflexos dela",
    "no_shadow_on_key": "sem sombras projetadas sobre o fundo",
    "no_gradient": "fundo uniforme, sem degradê, textura ou vinheta",
    "subject_inside_frame": "o sujeito inteiro dentro do quadro, sem tocar a borda",
}
KEY_CANDIDATES = [(0, 255, 0), (255, 0, 255), (0, 0, 255), (0, 255, 255)]
BG_KEYS = {"mode", "key", "alpha", "tolerance", "edge", "rules"}

MOODS = {
    "serene": ("sereno", "luz suave, contraste baixo, cores calmas"),
    "tense": ("tenso", "contraste alto, sombras profundas, enquadramento apertado"),
    "melancholic": ("melancólico", "cores frias e dessaturadas, luz baixa"),
    "epic": ("épico", "escala grande, luz dramática, céu imponente"),
    "mysterious": ("misterioso", "névoa, luz baixa, silhuetas parcialmente escondidas"),
    "joyful": ("alegre", "cores vivas, luz quente e clara"),
    "ominous": ("agourento", "céu pesado, tons frios e escuros, ameaça no horizonte"),
    "cozy": ("aconchegante", "luz quente e baixa, tons suaves"),
}
WEATHERS = {"clear": "céu limpo", "rain": "chuva", "snow": "neve", "fog": "névoa densa", "storm": "tempestade", "dust": "poeira no ar"}
WIND_STRENGTH = {"calm": "sem vento", "low": "vento fraco", "normal": "vento moderado", "high": "vento forte", "max": "vendaval"}
CALM_MOODS = {"serene", "cozy", "joyful"}
ATMO_KEYS = {"mood", "weather", "wind"}


# ---- fundo -----------------------------------------------------------------
def pick_key(data: dict) -> tuple[int, int, int]:
    """Cor de chave mais distante da paleta conhecida (verde se a paleta não disser nada)."""
    refs = PAL.reference_colors(data)
    if not refs:
        return KEY_CANDIDATES[0]
    return max(KEY_CANDIDATES, key=lambda k: min(C.delta_e(k, r) for r in refs))


def key_color(data: dict) -> tuple[int, int, int] | None:
    bg = data.get("background")
    if not isinstance(bg, dict) or bg.get("mode") != "chromakey":
        return None
    spec = bg.get("key", "auto")
    if spec == "auto":
        return pick_key(data)
    try:
        return PAL.resolve_spec(data, spec)
    except C.ColorError:
        return None


def check_background(c, data: dict, scene) -> None:
    bg = data.get("background")
    if bg is None:
        return
    if not isinstance(bg, dict):
        c.error("$.background", "deve ser um mapa", got=bg)
        return
    unknown_keys(c, "$.background", bg, BG_KEYS)
    mode = bg.get("mode", "scene")
    enum_check(c, "$.background.mode", mode, BG_MODES, required=False)
    if "alpha" in bg:
        enum_check(c, "$.background.alpha", bg["alpha"], ALPHA_METHODS)
    if "edge" in bg:
        enum_check(c, "$.background.edge", bg["edge"], EDGES)
    if "tolerance" in bg and not (is_num(bg["tolerance"]) and 0 < bg["tolerance"] <= 60):
        c.error("$.background.tolerance", "deve ser um número em (0, 60] (ΔE)", got=bg["tolerance"])
    if "rules" in bg:
        for i, r in enumerate(str_list(c, "$.background.rules", bg["rules"])):
            enum_check(c, f"$.background.rules[{i}]", r, list(BG_RULES))
    if mode != "chromakey":
        if any(k in bg for k in ("key", "alpha", "rules")):
            c.warn("$.background", "key, alpha e rules só valem com mode: chromakey")
        return
    key = None
    spec = bg.get("key", "auto")
    if spec != "auto":
        try:
            key = PAL.resolve_spec(data, spec)
        except C.ColorError as e:
            c.error("$.background.key", str(e), got=spec, hint="use 'auto', #rrggbb, rgb, cmyk ou hsl")
    else:
        key = pick_key(data)
    if key is not None:
        for name, rgb in {**PAL.all_colors(data), **PAL.approx_named_colors(data), **PAL.mentioned_colors(data)}.items():
            d = C.delta_e(key, rgb)
            if d < 35:
                c.warn("$.background.key", f"a chave {C.to_hex(key)} é parecida com a cor {name!r} da paleta (ΔE {d:.0f}): vai vazar para o sujeito",
                       hint=f"use key: auto (sugere {C.to_hex(pick_key(data))})")
    if scene is not None:
        raw = {e["id"]: e for e in data.get("entities", []) if isinstance(e, dict) and "id" in e}
        method = bg.get("alpha", "chroma")
        for ent in scene.entities:
            tr = bool(raw.get(ent.id, {}).get("translucent"))
            if tr and method == "chroma":
                c.warn(f"entity:{ent.id}", "parte translúcida com recorte por chave será aproximada", hint="use background.alpha: difference")
            elif ent.kind in ("effect", "light_source") and not tr and method == "chroma":
                c.warn(f"entity:{ent.id}", f"{ent.kind} tem bordas suaves e recorta mal por chave",
                       hint="marque translucent: true ou use background.alpha: difference")


def background_section(scene, passname: str | None = None) -> str | None:
    bg = scene.data.get("background")
    if not isinstance(bg, dict) or bg.get("mode") != "chromakey":
        return None
    if bg.get("alpha") == "difference":
        col = {"black": (0, 0, 0), "white": (255, 255, 255)}.get(passname or "black")
        base = f"Fundo sólido {'preto' if col == (0, 0, 0) else 'branco'} ({C.to_hex(col)}), uniforme"
    else:
        key = key_color(scene.data)
        base = f"Fundo de chroma key: cor sólida e uniforme {C.describe(key)}" if key else "Fundo de chroma key sólido e uniforme"
    rules = bg.get("rules") or list(BG_RULES)[:3]
    edge = "bordas nítidas e bem definidas" if bg.get("edge", "hard") == "hard" else "bordas suaves"
    return base + "; " + "; ".join(BG_RULES[r] for r in rules) + f"; {edge}."


# ---- atmosfera ---------------------------------------------------------------
def wind_vector(data: dict):
    w = (data.get("atmosphere") or {}).get("wind")
    if isinstance(w, dict) and w.get("direction") in V.DIRECTIONS and w.get("strength", "normal") != "calm":
        return V.DIRECTIONS[w["direction"]]
    return None


def check_atmosphere(c, data: dict, scene) -> None:
    at = data.get("atmosphere")
    if at is not None:
        if not isinstance(at, dict):
            c.error("$.atmosphere", "deve ser um mapa", got=at)
            at = None
        else:
            unknown_keys(c, "$.atmosphere", at, ATMO_KEYS)
    if at:
        mood = at.get("mood")
        if mood is not None:
            if not isinstance(mood, dict):
                c.error("$.atmosphere.mood", "deve ser um mapa {name, level}", got=mood)
            else:
                unknown_keys(c, "$.atmosphere.mood", mood, {"name", "level"})
                enum_check(c, "$.atmosphere.mood.name", mood.get("name"), list(MOODS))
                enum_check(c, "$.atmosphere.mood.level", mood.get("level", "normal"), V.LEVELS, required=False)
        if "weather" in at:
            enum_check(c, "$.atmosphere.weather", at["weather"], list(WEATHERS))
        wind = at.get("wind")
        if wind is not None:
            if not isinstance(wind, dict):
                c.error("$.atmosphere.wind", "deve ser um mapa {direction, strength}", got=wind)
            else:
                unknown_keys(c, "$.atmosphere.wind", wind, {"direction", "strength"})
                enum_check(c, "$.atmosphere.wind.direction", wind.get("direction"), list(V.DIRECTIONS))
                enum_check(c, "$.atmosphere.wind.strength", wind.get("strength", "normal"), list(WIND_STRENGTH), required=False)
        m = (mood or {}).get("name") if isinstance(mood, dict) else None
        lvl = (mood or {}).get("level", "normal") if isinstance(mood, dict) else "normal"
        if m in CALM_MOODS and at.get("weather") == "storm" and lvl in ("high", "max"):
            c.warn("$.atmosphere", f"mood {m!r} intenso com tempestade é contraditório", hint="baixe o nível do mood ou troque o clima")
    # partes que reagem ao vento (por entidade)
    wv = wind_vector(data)
    for i, e in enumerate(data.get("entities") or []):
        if not isinstance(e, dict):
            continue
        p = f"$.entities[{i}]"
        if "translucent" in e and not isinstance(e["translucent"], bool):
            c.error(f"{p}.translucent", "deve ser true ou false", got=e["translucent"])
        wp = e.get("wind_parts")
        if wp is None:
            continue
        if not at or "wind" not in at:
            c.warn(f"{p}.wind_parts", "a entidade reage ao vento, mas a cena não define atmosphere.wind")
        if isinstance(wp, list):
            str_list(c, f"{p}.wind_parts", wp)
        elif isinstance(wp, dict):
            for part, d in wp.items():
                if not enum_check(c, f"{p}.wind_parts.{part}", d, list(V.DIRECTIONS)):
                    continue
                v = V.DIRECTIONS[d]
                if wv and v != (0, 0) and (v[0] * wv[0] + v[1] * wv[1]) < 0:
                    c.error(f"{p}.wind_parts.{part}", f"a parte {part!r} aponta contra o vento ({at['wind']['direction']})",
                            got=d, hint="use a direção do vento ou remova a direção própria")
        else:
            c.error(f"{p}.wind_parts", "deve ser uma lista de partes ou um mapa parte → direção", got=wp)


def atmosphere_section(scene) -> str | None:
    at = scene.data.get("atmosphere")
    if not isinstance(at, dict):
        return None
    bits = []
    mood = at.get("mood")
    if isinstance(mood, dict) and mood.get("name") in MOODS:
        pt, how = MOODS[mood["name"]]
        lvl = mood.get("level", "normal")
        pre = {"low": "levemente ", "normal": "", "high": "muito ", "max": "extremamente "}[lvl]
        bits.append(f"clima emocional {pre}{pt}: {how}")
    if at.get("weather") in WEATHERS:
        w = WEATHERS[at["weather"]]
        wind = at.get("wind") or {}
        if wind.get("direction") in V.DIRECTIONS and at["weather"] in ("rain", "snow", "dust", "storm") and wind.get("strength", "normal") != "calm":
            w += f", inclinada {V.DIRECTION_PT[wind['direction']]}"
        bits.append(w)
    wind = at.get("wind")
    if isinstance(wind, dict) and wind.get("direction") in V.DIRECTIONS:
        s = WIND_STRENGTH[wind.get("strength", "normal")]
        if wind.get("strength") == "calm":
            bits.append("sem vento: tecidos, cabelos e bandeiras caem parados")
        else:
            bits.append(f"{s} soprando {V.DIRECTION_PT[wind['direction']]} ({_SCREEN}); tudo o que é leve (tecidos, cabelo, bandeiras, vegetação, espuma) obedece a essa mesma direção")
    return "; ".join(bits).capitalize() + "." if bits else None


_SCREEN = "do ponto de vista de quem vê a imagem"


def wind_sentence(scene, entity_id: str) -> str | None:
    """Frase para a entidade: suas partes leves seguem o vento."""
    at = scene.data.get("atmosphere")
    raw = next((e for e in scene.data["entities"] if e["id"] == entity_id), {})
    wp = raw.get("wind_parts")
    if not wp or not isinstance(at, dict) or not isinstance(at.get("wind"), dict):
        return None
    if at["wind"].get("strength") == "calm":
        return None
    if isinstance(wp, dict):
        return "; ".join(f"{V.part_pt(part)} {V.DIRECTION_PT[d]}" for part, d in wp.items()).capitalize() + " (movidos pelo vento)."
    d = V.DIRECTION_PT[at["wind"]["direction"]]
    names = [V.part_pt(x) for x in wp]
    verb = "flui" if len(names) == 1 else "fluem"
    listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " e " + names[-1]
    return f"Com o vento, {listed} {verb} {d}."
