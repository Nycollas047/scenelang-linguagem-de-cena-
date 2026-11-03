"""Materiais, texturas e orçamento de detalhe.

materials:                        # biblioteca da cena (reutilizável via import)
  bronze_gasto: {base: metal, finish: scratched, wear: high, detail_scale: fine,
                 pattern: "filigrana gravada", sheen: normal, color: "@bronze"}
  seda_azul:    {fabric: silk, weave: plain, drape: flowing, color: "#2850d2"}        # base: cloth é implícito
  couro_dragao: {scales: {pattern: overlapping, size: medium, edge: smooth,           # base: scales é implícito
                          sheen: high, gradient: {from: "#14502d", to: "#d4a528"}, coverage: [back, tail]}}
entidade:
  material: bronze_gasto          # ou um mapa inline
  parts: {armor: bronze_gasto, cape: {base: cloth, finish: matte}}
  detail: high                    # orçamento de detalhe da entidade
detail:                           # orçamento por zona (no máximo UM "max" na cena inteira)
  focal: max
  foreground: high
  midground: normal
  background: low
"""
from __future__ import annotations

from . import color as C
from . import palette as PAL
from . import vocab as V
from .checks import enum_check, unknown_keys

BASES = {"metal": "metal", "stone": "pedra", "cloth": "tecido", "leather": "couro", "skin": "pele", "wood": "madeira",
         "glass": "vidro", "water": "água", "crystal": "cristal", "fur": "pelo", "paper": "papel", "bone": "osso",
         "scales": "escamas", "feathers": "penas", "chitin": "quitina", "shell": "carapaça", "rubber": "borracha",
         "plastic": "plástico", "ceramic": "cerâmica", "wool": "lã"}
FABRICS = {"cotton": "algodão", "linen": "linho", "silk": "seda", "satin": "cetim", "wool": "lã", "velvet": "veludo",
           "denim": "jeans", "lace": "renda", "canvas": "lona", "tulle": "tule", "leather": "couro", "burlap": "juta",
           "chiffon": "chiffon", "felt": "feltro", "tweed": "tweed", "corduroy": "veludo cotelê", "suede": "camurça", "fleece": "fleece", "knit": "malha de tricô", "mesh": "tela vazada"}
WEAVES = {"plain": "trama lisa", "twill": "sarja (diagonal)", "checked": "xadrez", "striped": "listrado", "herringbone": "espinha de peixe",
          "polka": "de bolinhas", "floral": "estampa floral", "embroidered": "bordado", "brocade": "brocado", "quilted": "acolchoado",
          "pleated": "plissado", "ribbed": "canelado", "patched": "remendado"}
DRAPES = {"stiff": "caimento rígido", "structured": "caimento estruturado", "flowing": "caimento fluido", "heavy": "caimento pesado e reto",
          "clingy": "colado ao corpo", "billowing": "volumoso, inflado", "tattered": "em farrapos"}
SCALE_PATTERNS = {"overlapping": "sobrepostas como telhas (imbricadas)", "hexagonal": "hexagonais encaixadas como um favo",
                  "diamond": "em losangos", "plate": "em placas largas", "granular": "granuladas, pequenas e uniformes",
                  "keeled": "carenadas, com uma crista central em cada escama", "rounded": "arredondadas, como escamas de peixe"}
SCALE_SIZES = {"tiny": "minúsculas", "small": "pequenas", "medium": "médias", "large": "grandes", "huge": "enormes"}
SCALE_EDGES = {"smooth": "bordas lisas", "serrated": "bordas serrilhadas", "spiked": "bordas com pontas", "rough": "bordas ásperas"}
SCALE_KEYS = {"pattern", "size", "edge", "sheen", "gradient", "coverage", "color"}
FINISHES = {"polished": "polido", "matte": "fosco", "scratched": "arranhado", "oxidized": "oxidado", "wet": "molhado",
            "rough": "áspero", "glossy": "lustroso", "mossy": "coberto de musgo", "dusty": "empoeirado"}
WEARS = {"low": "quase novo", "normal": "com desgaste de uso", "high": "muito desgastado"}
SCALES = {"fine": "grão fino", "medium": "grão médio", "coarse": "grão grosso"}
SHEEN_ALIASES = {"strong": "high", "weak": "low", "medium": "normal", "intense": "max", "forte": "high", "fraco": "low", "medio": "normal", "intenso": "max"}
SHEENS = {"low": "brilho discreto", "normal": "brilho médio", "high": "brilho forte", "max": "brilho intenso"}
MAT_KEYS = {"base", "finish", "wear", "detail_scale", "pattern", "sheen", "color", "fabric", "weave", "drape", "scales"}
ZONES = ("focal", "foreground", "midground", "background")
DETAIL_PT = {"max": "textura e detalhe máximos", "high": "muito detalhado", "normal": "detalhe moderado", "low": "simplificado e suave"}
ZONE_PT = {"focal": "no ponto focal", "foreground": "no primeiro plano", "midground": "no plano médio", "background": "no fundo"}


def _check_spec(c, path: str, spec, data: dict) -> None:
    if not isinstance(spec, dict):
        c.error(path, "deve ser um mapa de material", got=spec)
        return
    unknown_keys(c, path, spec, MAT_KEYS)
    implied = implied_base(spec)
    if "base" in spec or implied is None:
        enum_check(c, f"{path}.base", spec.get("base"), list(BASES))
    if implied and spec.get("base") not in (None, implied, "leather", "wool") and implied == "cloth":
        c.warn(f"{path}.base", f"fabric só faz sentido com base: cloth (a base {spec.get('base')!r} será ignorada para o tecido)")
    if implied == "scales" and spec.get("base") not in (None, "scales"):
        c.warn(f"{path}.base", f"`scales` descreve base: scales (a base {spec.get('base')!r} conflita)")
    for key, table in (("fabric", FABRICS), ("weave", WEAVES), ("drape", DRAPES)):
        if key in spec:
            enum_check(c, f"{path}.{key}", spec[key], list(table))
    if "scales" in spec:
        _check_scales(c, f"{path}.scales", spec["scales"], data)
    if "weave" in spec and "fabric" not in spec and spec.get("base", "cloth") != "cloth":
        c.warn(f"{path}.weave", "weave vale para tecidos: use base: cloth ou fabric")
    if spec.get("drape") in ("flowing", "clingy", "billowing") and spec.get("fabric") in ("canvas", "burlap", "denim", "leather"):
        c.warn(path, f"tecido {spec['fabric']} dificilmente tem caimento {spec['drape']}", hint="use drape: stiff, structured ou heavy")
    if spec.get("drape") in ("stiff", "structured", "heavy") and spec.get("fabric") in ("chiffon", "tulle", "silk"):
        c.warn(path, f"tecido {spec['fabric']} dificilmente tem caimento {spec['drape']}", hint="use drape: flowing ou billowing")
    if "finish" in spec:
        enum_check(c, f"{path}.finish", spec["finish"], list(FINISHES))
    if "wear" in spec:
        enum_check(c, f"{path}.wear", spec["wear"], list(WEARS))
    if "detail_scale" in spec:
        enum_check(c, f"{path}.detail_scale", spec["detail_scale"], list(SCALES))
    if "sheen" in spec:
        enum_check(c, f"{path}.sheen", spec["sheen"], list(SHEENS))
    if "pattern" in spec and not isinstance(spec["pattern"], str):
        c.error(f"{path}.pattern", "deve ser um texto", got=spec["pattern"])
    if "color" in spec:
        try:
            PAL.resolve_spec(data, spec["color"])
        except C.ColorError as e:
            c.error(f"{path}.color", str(e), got=spec["color"])
    if spec.get("finish") == "polished" and spec.get("wear") == "high":
        c.warn(path, "acabamento polido com desgaste alto é contraditório", hint="use finish: scratched ou wear: normal")
    if spec.get("finish") in ("polished", "glossy") and spec.get("sheen") == "low":
        c.warn(path, "acabamento brilhante com brilho discreto é contraditório", hint="suba o sheen ou use finish: matte")
    if spec.get("finish") == "matte" and spec.get("sheen") in ("high", "max"):
        c.warn(path, "acabamento fosco com brilho forte é contraditório", hint="baixe o sheen ou use finish: glossy")


def implied_base(spec: dict):
    """Base deduzida do bloco: `fabric/weave/drape` → cloth; `scales` → scales."""
    if "scales" in spec:
        return "scales"
    if any(k in spec for k in ("fabric", "weave", "drape")):
        return "cloth"
    return None


def _check_scales(c, path: str, sc, data: dict) -> None:
    if not isinstance(sc, dict):
        c.error(path, "deve ser um mapa (pattern, size, edge, sheen, gradient, coverage)", got=sc)
        return
    unknown_keys(c, path, sc, SCALE_KEYS)
    for key, table in (("pattern", SCALE_PATTERNS), ("size", SCALE_SIZES), ("edge", SCALE_EDGES), ("sheen", SHEENS)):
        if key in sc:
            enum_check(c, f"{path}.{key}", sc[key], list(table))
    if "color" in sc:
        try:
            PAL.resolve_spec(data, sc["color"])
        except C.ColorError as e:
            c.error(f"{path}.color", str(e), got=sc["color"])
    g = sc.get("gradient")
    if g is not None:
        if not (isinstance(g, dict) and set(g) == {"from", "to"}):
            c.error(f"{path}.gradient", "deve ser {from: cor, to: cor}", got=g)
        else:
            for k in ("from", "to"):
                try:
                    PAL.resolve_spec(data, g[k])
                except C.ColorError as e:
                    c.error(f"{path}.gradient.{k}", str(e), got=g[k])
            if "color" in sc:
                c.warn(path, "color e gradient juntos: vale o degradê")
    cov = sc.get("coverage")
    if cov is not None and not (isinstance(cov, list) and cov and all(isinstance(x, str) for x in cov)):
        c.error(f"{path}.coverage", "deve ser uma lista de partes (ex.: [back, tail])", got=cov)
    if sc.get("pattern") == "granular" and sc.get("size") in ("large", "huge"):
        c.warn(path, "escamas granulares são pequenas por natureza: size grande é contraditório", hint="use size: tiny ou small, ou pattern: plate")
    if sc.get("pattern") == "plate" and sc.get("size") in ("tiny",):
        c.warn(path, "placas largas não são minúsculas", hint="use size: medium ou large")


def _resolve(data: dict, ref):
    if isinstance(ref, str):
        return (data.get("materials") or {}).get(ref)
    return ref if isinstance(ref, dict) else None


def check(c, data: dict) -> None:
    mats = data.get("materials")
    if mats is not None:
        if not isinstance(mats, dict):
            c.error("$.materials", "deve ser um mapa nome → material", got=mats)
        else:
            for name, spec in mats.items():
                _check_spec(c, f"$.materials.{name}", spec, data)
    maxes = []
    det = data.get("detail")
    if det is not None:
        if not isinstance(det, dict):
            c.error("$.detail", "deve ser um mapa zona → nível", got=det)
        else:
            unknown_keys(c, "$.detail", det, ZONES)
            for z, lv in det.items():
                if z in ZONES and enum_check(c, f"$.detail.{z}", lv, V.LEVELS) and lv == "max":
                    maxes.append(f"detail.{z}")
    for i, e in enumerate(data.get("entities") or []):
        if not isinstance(e, dict):
            continue
        p = f"$.entities[{i}]"
        refs = {}
        if "material" in e:
            refs["material"] = e["material"]
        if "parts" in e:
            if not isinstance(e["parts"], dict):
                c.error(f"{p}.parts", "deve ser um mapa parte → material", got=e["parts"])
            else:
                for part, ref in e["parts"].items():
                    refs[f"parts.{part}"] = ref
        for key, ref in refs.items():
            if isinstance(ref, str):
                if ref not in (data.get("materials") or {}):
                    c.error(f"{p}.{key}", "material inexistente", got=ref, accepted=sorted(data.get("materials") or {}))
            else:
                _check_spec(c, f"{p}.{key}", ref, data)
        if "detail" in e:
            if enum_check(c, f"{p}.detail", e["detail"], V.LEVELS) and e["detail"] == "max":
                maxes.append(f"entities.{e.get('id', i)}.detail")
    if len(maxes) > 1:
        c.error("$.detail", "detalhe máximo duplo: só um ponto da cena pode concentrar o detalhe máximo", got=maxes,
                hint="deixe um 'max' e rebaixe os demais para high")


def _scales_phrase(sc: dict, data: dict) -> str:
    bits = ["escamas " + SCALE_SIZES.get(sc.get("size", ""), "")]
    bits[0] = bits[0].strip()
    if "pattern" in sc:
        bits.append(SCALE_PATTERNS[sc["pattern"]])
    if "edge" in sc:
        bits.append(SCALE_EDGES[sc["edge"]])
    if "sheen" in sc:
        bits.append(SHEENS[sc["sheen"]])
    g = sc.get("gradient")
    try:
        if isinstance(g, dict):
            bits.append(f"em degradê de {C.describe(PAL.resolve_spec(data, g['from']))} para {C.describe(PAL.resolve_spec(data, g['to']))}")
        elif "color" in sc:
            bits.append("cor " + C.describe(PAL.resolve_spec(data, sc["color"])))
    except C.ColorError:
        pass
    text = ", ".join(bits)
    if sc.get("coverage"):
        text += f", cobrindo {', '.join(V.part_pt(x) for x in sc['coverage'])} (o resto sem escamas)"
    return text


def describe(spec: dict, data: dict) -> str:
    bits = []
    fin = FINISHES.get(spec.get("finish", ""), "")
    if "scales" in spec:
        bits.append(_scales_phrase(spec["scales"], data))
        if fin:
            bits.append(fin)
    elif "fabric" in spec:
        bits.append(f"tecido de {FABRICS[spec['fabric']]} {fin}".strip())
    elif "base" in spec:
        bits.append(f"{BASES[spec['base']]} {fin}".strip())
    else:   # só weave/drape → tecido
        bits.append(f"tecido {fin}".strip())
    for key, table in (("weave", WEAVES), ("drape", DRAPES)):
        if key in spec:
            bits.append(table[spec[key]])
    if "wear" in spec:
        bits.append(WEARS[spec["wear"]])
    if "detail_scale" in spec:
        bits.append(SCALES[spec["detail_scale"]])
    if "sheen" in spec:
        bits.append(SHEENS[spec["sheen"]])
    if spec.get("pattern"):
        bits.append(spec["pattern"])
    if "color" in spec:
        try:
            bits.append("cor " + C.describe(PAL.resolve_spec(data, spec["color"])))
        except C.ColorError:
            pass
    return ", ".join(bits)


def entity_sentence(scene, entity_id: str) -> str | None:
    raw = next((e for e in scene.data["entities"] if e["id"] == entity_id), {})
    parts = []
    if "material" in raw:
        spec = _resolve(scene.data, raw["material"])
        if spec:
            parts.append(f"Material: {describe(spec, scene.data)}.")
    if isinstance(raw.get("parts"), dict):
        items = []
        for part, ref in raw["parts"].items():
            spec = _resolve(scene.data, ref)
            if spec:
                items.append(f"{V.part_pt(part)}: {describe(spec, scene.data)}")
        if items:
            parts.append("Materiais por parte — " + "; ".join(items) + ".")
    if raw.get("detail"):
        parts.append(f"Nível de detalhe: {DETAIL_PT[raw['detail']]}.")
    return " ".join(parts) or None


def detail_section(scene) -> str | None:
    det = scene.data.get("detail")
    if not isinstance(det, dict) or not det:
        return None
    return "Distribuição de detalhe: " + "; ".join(f"{DETAIL_PT[v]} {ZONE_PT[z]}" for z, v in det.items() if z in ZONE_PT) + "."
