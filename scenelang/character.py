"""Personagem: idade, herança, tom de pele, cabelo, olhos, rosto, corpo e partes.

Princípios:
- Descritivo e neutro: cada atributo é independente. A linguagem NUNCA deduz traços a partir de `heritage`
  (texto livre, nas palavras do autor); quem define a aparência é o autor, atributo por atributo.
- O tom de pele usa a escala Monk (1–10), com cor de referência aproximada; `skin.color` dá a cor exata.
- O vocabulário é de design de personagem; não inclui conteúdo sexual.

entities:
  - id: capitao
    kind: character
    character:
      age_group: adult
      heritage: "afro-brasileira"
      skin: {tone: 8, undertone: warm, marks: [freckles]}     # ou color: "#604134"
      hair: {texture: coily, length: medium, color: "#1c1410", style: "tranças finas"}
      eyes: {color: castanhos, shape: almond}
      face: {shape: oval, nose: broad, lips: full, jaw: defined}
      body: {build: athletic, height: tall, shoulders: broad, waist: narrow, hips: average, limbs: long,
             posture: upright, proportion: heroic}
      features: {hands: "mãos largas com dedos longos", ears: "orelhas pontudas"}
"""
from __future__ import annotations

from . import color as C
from . import palette as PAL
from .checks import enum_check, unknown_keys

CHAR_KEYS = {"age_group", "heritage", "skin", "hair", "eyes", "face", "body", "features", "facial_hair"}
FACIAL_TYPES = {"beard": "barba", "mustache": "bigode", "stubble": "barba por fazer", "goatee": "cavanhaque", "sideburns": "costeletas",
                "beard_and_mustache": "barba e bigode"}
FACIAL_LEN = {"short": "curta", "medium": "média", "long": "longa"}
AGES = {"child": "criança", "teen": "adolescente", "young_adult": "jovem adulto", "adult": "adulto",
        "middle_aged": "meia-idade", "elder": "idoso"}
UNDERTONES = {"cool": "subtom frio", "neutral": "subtom neutro", "warm": "subtom quente", "olive": "subtom oliváceo"}
SKIN_KEYS = {"tone", "undertone", "color", "finish", "marks"}
SKIN_FINISH = {"matte": "fosca", "dewy": "viçosa e levemente brilhante", "weathered": "curtida pelo tempo", "smooth": "lisa"}
MARKS = {"freckles": "sardas", "moles": "pintas", "scars": "cicatrizes", "vitiligo": "manchas de vitiligo", "birthmark": "marca de nascença",
         "wrinkles": "rugas", "tattoos": "tatuagens", "blush": "bochechas coradas", "sun_spots": "manchas de sol"}
# Escala Monk (referência aproximada das cores) e palavra de tom.
MONK = {1: "#f6ede4", 2: "#f3e7db", 3: "#f7ead0", 4: "#eadaba", 5: "#d7bd96",
        6: "#a07e56", 7: "#825c43", 8: "#604134", 9: "#3a312a", 10: "#292420"}
TONE_WORD = {1: "muito clara", 2: "muito clara", 3: "clara", 4: "clara", 5: "média", 6: "média", 7: "escura", 8: "escura", 9: "muito escura", 10: "muito escura"}
HAIR_KEYS = {"texture", "length", "color", "style", "density"}
HAIR_TEXTURE = {"straight": "liso", "wavy": "ondulado", "curly": "cacheado", "coily": "crespo"}
HAIR_LENGTH = {"bald": "careca", "buzzed": "raspado", "short": "curto", "medium": "médio", "long": "longo", "very_long": "muito longo"}
HAIR_DENSITY = {"thin": "ralo", "normal": "com volume normal", "thick": "volumoso"}
EYE_SHAPE = {"almond": "amendoados", "round": "redondos", "hooded": "com pálpebra caída", "monolid": "de pálpebra única",
             "upturned": "levemente voltados para cima", "downturned": "levemente voltados para baixo"}
FACE_SHAPE = {"oval": "oval", "round": "redondo", "square": "quadrado", "heart": "em formato de coração", "long": "alongado", "diamond": "em losango"}
NOSE = {"narrow": "nariz estreito", "average": "nariz médio", "broad": "nariz largo", "aquiline": "nariz aquilino", "upturned": "nariz arrebitado"}
LIPS = {"thin": "lábios finos", "average": "lábios médios", "full": "lábios carnudos"}
JAW = {"soft": "mandíbula suave", "defined": "mandíbula definida", "square": "mandíbula quadrada"}
BUILD = {"slim": "esguio", "lean": "magro", "athletic": "atlético", "average": "de constituição média", "stocky": "robusto e atarracado",
         "heavy": "corpulento", "muscular": "musculoso"}
HEIGHT = {"tiny": "minúsculo", "short": "baixo", "average": "de altura média", "tall": "alto", "towering": "imponente, muito alto"}
SHOULDERS = {"narrow": "ombros estreitos", "average": "ombros médios", "broad": "ombros largos"}
WAIST = {"narrow": "cintura estreita", "average": "cintura média", "wide": "cintura larga"}
HIPS = {"narrow": "quadris estreitos", "average": "quadris médios", "wide": "quadris largos"}
LIMBS = {"short": "membros curtos", "average": "membros médios", "long": "membros longos"}
POSTURE = {"slouched": "postura curvada", "relaxed": "postura relaxada", "upright": "postura ereta", "rigid": "postura rígida"}
PROPORTION_PT = {"chibi": "chibi", "stylized": "estilizada", "realistic": "realista", "heroic": "heroica"}
PROPORTION = {"chibi": 2.0, "stylized": 4.0, "realistic": 7.5, "heroic": 8.0}
BODY_KEYS = {"build", "height", "shoulders", "waist", "hips", "limbs", "posture", "proportion"}
FEATURE_PARTS = {"head": "a cabeça", "neck": "o pescoço", "arms": "os braços", "hands": "as mãos", "fingers": "os dedos", "torso": "o tronco",
                 "legs": "as pernas", "feet": "os pés", "ears": "as orelhas", "horns": "os chifres", "tail": "a cauda", "wings": "as asas",
                 "claws": "as garras", "fangs": "as presas", "snout": "o focinho", "eyes": "os olhos", "mouth": "a boca"}


def skin_rgb(skin: dict, data: dict):
    if not isinstance(skin, dict):
        return None
    try:
        if "color" in skin:
            return PAL.resolve_spec(data, skin["color"])
        if isinstance(skin.get("tone"), int) and skin["tone"] in MONK:
            return C.parse_color(MONK[skin["tone"]])
    except C.ColorError:
        return None
    return None


def _rgb_or_name(v, data):
    if isinstance(v, str):
        rgb = C.name_to_rgb(v.replace("_", "-"))
        if rgb is not None:
            return rgb
    try:
        return PAL.resolve_spec(data, v)
    except C.ColorError:
        return None


def skin_colors(data: dict) -> dict[str, tuple[int, int, int]]:
    """Cores do corpo declaradas nas entidades (pele, cabelo, olhos, pelos do rosto) e `signature`.

    Alimenta a escolha da chave de recorte e os avisos de vazamento: a chave não pode se parecer com nenhuma delas.
    """
    out = {}
    for e in data.get("entities") or []:
        if not isinstance(e, dict):
            continue
        eid = e.get("id")
        ch = e.get("character")
        if isinstance(ch, dict):
            rgb = skin_rgb(ch.get("skin"), data)
            if rgb:
                out[f"pele de {eid}"] = rgb
            for key, label in (("hair", "cabelo"), ("eyes", "olhos"), ("facial_hair", "pelos do rosto")):
                sub = ch.get(key)
                if isinstance(sub, dict) and "color" in sub:
                    rgb = _rgb_or_name(sub["color"], data)
                    if rgb:
                        out[f"{label} de {eid}"] = rgb
        sig = e.get("signature")
        for j, v in enumerate(sig if isinstance(sig, list) else [sig] if sig else []):
            rgb = _rgb_or_name(v, data)
            if rgb:
                out[f"assinatura {j + 1} de {eid}"] = rgb
    return out


def _map_enum(c, path: str, m, key: str, table) -> None:
    if key in m:
        enum_check(c, f"{path}.{key}", m[key], list(table))


def _sub(c, path: str, ch: dict, key: str, allowed) -> dict | None:
    v = ch.get(key)
    if v is None:
        return None
    if not isinstance(v, dict):
        c.error(f"{path}.{key}", "deve ser um mapa", got=v)
        return None
    unknown_keys(c, f"{path}.{key}", v, allowed)
    return v


def check(c, data: dict, scene) -> None:
    guide = data.get("guides") if isinstance(data.get("guides"), dict) else {}
    for i, e in enumerate(data.get("entities") or []):
        if not isinstance(e, dict) or "character" not in e:
            continue
        p = f"$.entities[{i}].character"
        ch = e["character"]
        if e.get("kind") not in ("character", "creature"):
            c.error(p, "`character` só vale para kind: character ou creature", got=e.get("kind"))
        if not isinstance(ch, dict):
            c.error(p, "deve ser um mapa", got=ch)
            continue
        unknown_keys(c, p, ch, CHAR_KEYS)
        if "age_group" in ch:
            enum_check(c, f"{p}.age_group", ch["age_group"], list(AGES))
        if "heritage" in ch and not (isinstance(ch["heritage"], str) and 0 < len(ch["heritage"]) <= 80):
            c.error(f"{p}.heritage", "deve ser um texto curto (até 80 caracteres), nas palavras do autor", got=ch["heritage"])
        sk = _sub(c, p, ch, "skin", SKIN_KEYS)
        if sk is not None:
            if "tone" in sk and not (isinstance(sk["tone"], int) and not isinstance(sk["tone"], bool) and 1 <= sk["tone"] <= 10):
                c.error(f"{p}.skin.tone", "deve ser um inteiro de 1 a 10 (escala Monk)", got=sk["tone"])
            _map_enum(c, f"{p}", {"undertone": sk.get("undertone")} if "undertone" in sk else {}, "undertone", UNDERTONES)
            if "finish" in sk:
                enum_check(c, f"{p}.skin.finish", sk["finish"], list(SKIN_FINISH))
            if "color" in sk:
                try:
                    PAL.resolve_spec(data, sk["color"])
                except C.ColorError as ex:
                    c.error(f"{p}.skin.color", str(ex), got=sk["color"])
            if "tone" in sk and "color" in sk:
                c.warn(f"{p}.skin", "tone e color juntos: vale a cor exata; o tom serve só de rótulo")
            if "marks" in sk:
                if not isinstance(sk["marks"], list):
                    c.error(f"{p}.skin.marks", "deve ser uma lista", got=sk["marks"])
                else:
                    for j, m in enumerate(sk["marks"]):
                        enum_check(c, f"{p}.skin.marks[{j}]", m, list(MARKS))
        hr = _sub(c, p, ch, "hair", HAIR_KEYS)
        if hr is not None:
            for k, t in (("texture", HAIR_TEXTURE), ("length", HAIR_LENGTH), ("density", HAIR_DENSITY)):
                _map_enum(c, f"{p}.hair", hr, k, t)
            if "color" in hr and not _color_or_name(hr["color"], data):
                c.error(f"{p}.hair.color", "deve ser uma cor (#rrggbb, rgb, cmyk, hsl, @nome) ou um nome de cor em português", got=hr["color"], accepted=sorted(C.NAMES_PT))
            if hr.get("length") in ("bald", "buzzed") and ("style" in hr or "texture" in hr):
                c.warn(f"{p}.hair", "estilo/textura de cabelo com length careca ou raspado é contraditório")
        ey = _sub(c, p, ch, "eyes", {"color", "shape"})
        if ey is not None:
            _map_enum(c, f"{p}.eyes", ey, "shape", EYE_SHAPE)
            if "color" in ey and not _color_or_name(ey["color"], data):
                c.error(f"{p}.eyes.color", "deve ser uma cor ou um nome de cor em português", got=ey["color"], accepted=sorted(C.NAMES_PT))
        fh = _sub(c, p, ch, "facial_hair", {"type", "length", "color", "style"})
        if fh is not None:
            enum_check(c, f"{p}.facial_hair.type", fh.get("type"), list(FACIAL_TYPES))
            if "length" in fh:
                enum_check(c, f"{p}.facial_hair.length", fh["length"], list(FACIAL_LEN))
            if "color" in fh and not _color_or_name(fh["color"], data):
                c.error(f"{p}.facial_hair.color", "deve ser uma cor ou um nome de cor em português", got=fh["color"], accepted=sorted(C.NAMES_PT))
        fc = _sub(c, p, ch, "face", {"shape", "nose", "lips", "jaw"})
        if fc is not None:
            for k, t in (("shape", FACE_SHAPE), ("nose", NOSE), ("lips", LIPS), ("jaw", JAW)):
                _map_enum(c, f"{p}.face", fc, k, t)
        bd = _sub(c, p, ch, "body", BODY_KEYS)
        if bd is not None:
            for k, t in (("build", BUILD), ("height", HEIGHT), ("shoulders", SHOULDERS), ("waist", WAIST), ("hips", HIPS),
                         ("limbs", LIMBS), ("posture", POSTURE), ("proportion", PROPORTION)):
                _map_enum(c, f"{p}.body", bd, k, t)
        ft = ch.get("features")
        if ft is not None:
            if not isinstance(ft, dict):
                c.error(f"{p}.features", "deve ser um mapa parte → texto", got=ft)
            else:
                for part, text in ft.items():
                    enum_check(c, f"{p}.features.{part}", part, list(FEATURE_PARTS))
                    if not isinstance(text, str) or not text.strip():
                        c.error(f"{p}.features.{part}", "deve ser um texto", got=text)
        # coerência com as guias
        if guide.get("subject") == e.get("id") and isinstance(bd, dict):
            from . import guides as G

            heads = G.heads_of(guide.get("canon")) if "canon" in guide else None
            want = PROPORTION.get(bd.get("proportion", ""))
            if heads and want and abs(heads - want) > 0.6:
                c.warn(f"{p}.body.proportion", f"proporção {bd['proportion']!r} (≈{want:g} cabeças) não bate com guides.canon ({heads:g} cabeças)",
                       hint="alinhe guides.canon ou remova body.proportion")
        if ch.get("age_group") == "child" and guide.get("subject") == e.get("id"):
            from . import guides as G

            heads = G.heads_of(guide.get("canon")) if "canon" in guide else None
            if heads and heads >= 7:
                c.warn(f"{p}.age_group", "criança com cânone de adulto (7 cabeças ou mais): use chibi, stylized ou {heads_tall: 5}")


def _color_or_name(v, data) -> bool:
    if isinstance(v, str) and C.name_to_rgb(v.replace("_", "-")) is not None:
        return True
    try:
        PAL.resolve_spec(data, v)
        return True
    except C.ColorError:
        return False


def _color_phrase(v, data) -> str:
    if isinstance(v, str) and C.name_to_rgb(v.replace("_", "-")) is not None:
        return v.replace("_", " ")
    return C.describe(PAL.resolve_spec(data, v))


def proportion_heads(scene, entity_id: str) -> float | None:
    raw = next((e for e in scene.data["entities"] if e["id"] == entity_id), {})
    bd = ((raw.get("character") or {}).get("body") or {}) if isinstance(raw.get("character"), dict) else {}
    return PROPORTION.get(bd.get("proportion", ""))


def _cap(t: str) -> str:
    return t[:1].upper() + t[1:]


def sentence(scene, entity_id: str) -> str | None:
    data = scene.data
    raw = next((e for e in data["entities"] if e["id"] == entity_id), {})
    ch = raw.get("character")
    if not isinstance(ch, dict):
        return None
    out = []
    head = []
    if "age_group" in ch:
        head.append(AGES[ch["age_group"]])
    if "heritage" in ch:
        h = ch["heritage"].strip()
        head.append(h if h.lower().startswith("herança") else f"herança {h}")
    if head:
        out.append("Personagem: " + ", ".join(head) + ".")
    sk = ch.get("skin")
    if isinstance(sk, dict):
        bits = []
        rgb = skin_rgb(sk, data)
        if "color" in sk and rgb:
            bits.append(f"pele de cor {C.describe(rgb)}")
        elif "tone" in sk:
            bits.append(f"pele {TONE_WORD[sk['tone']]} (tom {sk['tone']} de 10 na escala Monk, cor de referência {MONK[sk['tone']]})")
        if "undertone" in sk:
            bits.append(UNDERTONES[sk["undertone"]])
        if "finish" in sk:
            bits.append(SKIN_FINISH[sk["finish"]])
        if sk.get("marks"):
            bits.append("com " + ", ".join(MARKS[m] for m in sk["marks"]))
        if bits:
            out.append(_cap("; ".join(bits)) + ".")
    hr = ch.get("hair")
    if isinstance(hr, dict):
        bits = ["cabelo " + " ".join(x for x in (
            HAIR_LENGTH.get(hr.get("length", ""), ""), HAIR_TEXTURE.get(hr.get("texture", ""), ""), HAIR_DENSITY.get(hr.get("density", ""), "")) if x)]
        if "color" in hr:
            bits.append("cor " + _color_phrase(hr["color"], data))
        if hr.get("style"):
            bits.append(hr["style"])
        out.append(_cap(", ".join(b.strip() for b in bits)) + ".")
    ey = ch.get("eyes")
    if isinstance(ey, dict):
        bits = ["olhos"]
        if "color" in ey:
            bits.append("de cor " + _color_phrase(ey["color"], data))   # «de cor dourado»: evita a concordância «olhos dourado»
        if "shape" in ey:
            bits.append(EYE_SHAPE[ey["shape"]])
        out.append(_cap(" ".join(bits)) + ".")
    fh = ch.get("facial_hair")
    if isinstance(fh, dict) and fh.get("type") in FACIAL_TYPES:
        bits = [FACIAL_TYPES[fh["type"]]]
        if "length" in fh:
            bits.append(FACIAL_LEN[fh["length"]])
        if "color" in fh:
            bits.append("cor " + _color_phrase(fh["color"], data))
        if fh.get("style"):
            bits.append(fh["style"])
        out.append(_cap(" ".join(bits)) + ".")
    fc = ch.get("face")
    if isinstance(fc, dict):
        bits = []
        if "shape" in fc:
            bits.append("rosto " + FACE_SHAPE[fc["shape"]])
        for k, t in (("nose", NOSE), ("lips", LIPS), ("jaw", JAW)):
            if k in fc:
                bits.append(t[fc[k]])
        out.append(_cap(", ".join(bits)) + ".")
    bd = ch.get("body")
    if isinstance(bd, dict):
        bits = []
        for k, t in (("build", BUILD), ("height", HEIGHT)):
            if k in bd:
                bits.append(t[bd[k]])
        for k, t in (("shoulders", SHOULDERS), ("waist", WAIST), ("hips", HIPS), ("limbs", LIMBS), ("posture", POSTURE)):
            if k in bd:
                bits.append(t[bd[k]])
        if "proportion" in bd:
            bits.append(f"proporção {PROPORTION_PT[bd['proportion']]} (cerca de {PROPORTION[bd['proportion']]:g} cabeças de altura)")
        out.append("Corpo " + ", ".join(bits) + ".")
    ft = ch.get("features")
    if isinstance(ft, dict) and ft:
        out.append("; ".join(_cap(f"{FEATURE_PARTS[k]}: {v}") for k, v in ft.items()) + ".")
    return " ".join(out) or None
