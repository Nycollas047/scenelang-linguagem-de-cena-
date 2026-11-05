"""Validador: esquema, vocabulário fechado, referências e conflitos.

Retorna todos os problemas de uma vez, cada um com campo, valor recebido,
valores aceitos e sugestão, para que uma pessoa ou um modelo de linguagem
possa corrigir a cena em uma rodada só.
"""
from __future__ import annotations

import copy
import difflib
import re
from pathlib import Path

import yaml

from . import layout as L
from . import vocab as V
from .assertions import AssertSyntaxError, check_refs, parse_assert
from .model import SLUG, Diagnostic, RefError, Scene, build_scene
from . import character, fx, guides, lint, locate, materials, pose, palette as pal_layer
from . import variants
from . import verify as verify_mod
from .negations import to_affirmation

TOP_KEYS = {
    "scene", "version", "canvas", "grid", "style", "intent", "camera", "palette",
    "lights", "entities", "gaze", "asserts", "details", "finish", "glossary",
    "avoid", "priority_boost", "history",
    "colors", "guides", "background", "atmosphere", "materials", "detail", "verify", "lock", "extends", "import",
}
REQUIRED_TOP = ("scene", "canvas", "grid", "style", "intent", "entities")
ENTITY_KEYS = {
    "id", "kind", "label", "desc", "plane", "at", "size", "box", "orient",
    "brightness", "saturation", "tags", "details",
    "wind_parts", "translucent", "material", "parts", "detail", "character", "pose", "signature",
}
LIGHT_KEYS = {"role", "color", "source", "hits", "note"}
CAMERA_KEYS = {"angle", "lens", "focus", "depth_blur"}
PALETTE_KEYS = {"dominant", "accent", "accent_use", "notes", "mode", "space", "count", "harmony", "colors", "constraints", "proposal"}
LOCKABLE = {"palette", "style", "camera", "lights", "guides", "atmosphere", "background", "materials"}
RESERVED_IDS = set(V.POINT_NAMES) | set(L.region_names()) | {"canvas"}


class _Collector:
    def __init__(self) -> None:
        self.items: list[Diagnostic] = []
        self.skipped: set[str] = set()  # ids de entidades sem geometria utilizável

    def error(self, path, message, got=None, accepted=None, hint=None, fix=None):
        self.items.append(Diagnostic("error", path, message, got, accepted, hint, fix))

    def warn(self, path, message, got=None, accepted=None, hint=None):
        self.items.append(Diagnostic("warning", path, message, got, accepted, hint))

    @property
    def has_errors(self) -> bool:
        return any(d.level == "error" for d in self.items)


from .checks import enum_check as _enum  # noqa: E402
from .checks import is_num as _is_num  # noqa: E402
from .checks import str_list as _str_list  # noqa: E402
from .checks import closest  # noqa: E402
from .checks import suggest as _suggest  # noqa: E402


def validate_data(data) -> tuple[list[Diagnostic], Scene | None]:
    c = _Collector()
    if not isinstance(data, dict):
        c.error("$", "a cena deve ser um mapa YAML/JSON", got=type(data).__name__)
        return c.items, None

    for key in data:
        if key not in TOP_KEYS:
            near = closest(key, TOP_KEYS)
            c.error(f"$.{key}", "campo desconhecido", got=key, accepted=sorted(TOP_KEYS), hint=_suggest(key, TOP_KEYS),
                    fix={"path": f"$.{key}", "rename": near} if near else None)
    for key in REQUIRED_TOP:
        if key not in data:
            c.error(f"$.{key}", "campo obrigatório ausente")

    if not isinstance(data.get("scene", ""), str) or not str(data.get("scene", "x")).strip():
        c.error("$.scene", "o nome da cena deve ser um texto não vazio", got=data.get("scene"))

    # ---- canvas e grade ------------------------------------------------
    canvas = data.get("canvas")
    ratio_ok = False
    if isinstance(canvas, dict):
        _enum(c, "$.canvas.shape", canvas.get("shape", "rect"), V.CANVAS_SHAPES, required=False)
        try:
            L.parse_ratio(canvas.get("ratio"))
            ratio_ok = True
        except (ValueError, TypeError):
            c.error("$.canvas.ratio", "proporção inválida", got=canvas.get("ratio"), hint='use "16:9", "1:1", "9:16"')
    elif canvas is not None:
        c.error("$.canvas", "deve ser um mapa com shape e ratio", got=canvas)
    grid = data.get("grid")
    grid_ok = False
    if isinstance(grid, dict):
        grid_ok = _enum(c, "$.grid.kind", grid.get("kind"), V.GRIDS)
    elif grid is not None:
        c.error("$.grid", "deve ser um mapa com kind", got=grid)

    # ---- estilo --------------------------------------------------------
    style = data.get("style")
    if isinstance(style, dict):
        if not isinstance(style.get("base"), str) or not style.get("base", "").strip():
            c.error("$.style.base", "campo obrigatório: texto com o estilo base")
        mix = style.get("mix")
        if mix is not None:
            if not isinstance(mix, dict) or not mix or not all(_is_num(v) and v >= 0 for v in mix.values()):
                c.error("$.style.mix", "deve ser um mapa nome → porcentagem (números ≥ 0)", got=mix)
            elif abs(sum(mix.values()) - 100) > 0.5:
                c.error("$.style.mix", "as porcentagens devem somar 100", got=sum(mix.values()),
                        hint="ajuste os pesos para totalizar 100")
    elif style is not None:
        c.error("$.style", "deve ser um mapa com base (e mix opcional)", got=style)

    # ---- entidades -----------------------------------------------------
    ents = data.get("entities")
    ids_seen: dict[str, int] = {}
    skip: set[int] = set()  # entidades que não dá para posicionar
    if ents is not None and (not isinstance(ents, list) or not ents):
        c.error("$.entities", "deve ser uma lista com ao menos uma entidade", got=ents)
    if isinstance(ents, list):
        for i, e in enumerate(ents):
            p = f"$.entities[{i}]"
            if not isinstance(e, dict):
                c.error(p, "cada entidade deve ser um mapa", got=e)
                skip.add(i)
                continue
            n_id = len(c.items)
            for key in e:
                if key not in ENTITY_KEYS:
                    near = closest(key, ENTITY_KEYS)
                    c.error(f"{p}.{key}", "campo desconhecido", got=key, accepted=sorted(ENTITY_KEYS), hint=_suggest(key, ENTITY_KEYS),
                            fix={"path": f"{p}.{key}", "rename": near} if near else None)
            eid = e.get("id")
            if not isinstance(eid, str) or not SLUG.match(eid):
                c.error(f"{p}.id", "id deve ser um slug (minúsculas, dígitos e _, começando por letra)", got=eid)
            else:
                if eid in RESERVED_IDS:
                    c.error(f"{p}.id", "id reservado (nome de região, ponto ou canvas)", got=eid)
                if eid in ids_seen:
                    c.error(f"{p}.id", f"id repetido (já usado em entities[{ids_seen[eid]}])", got=eid)
                ids_seen.setdefault(eid, i)
            id_bad = any(d.level == "error" for d in c.items[n_id:])
            _enum(c, f"{p}.kind", e.get("kind"), V.KINDS)
            _enum(c, f"{p}.plane", e.get("plane"), V.PLANES)
            for req in ("label", "desc"):
                if not isinstance(e.get(req), str) or not e.get(req, "").strip():
                    c.error(f"{p}.{req}", "campo obrigatório: texto não vazio",
                            hint='label com artigo, ex.: "a lança"' if req == "label" else None)
            auto = isinstance(e.get("id"), str) and e.get("label") == e["id"].replace("_", " ")   # label gerado do id
            if isinstance(e.get("label"), str) and not auto and not re.match(r"^(o|a|os|as) ", e["label"]):
                c.warn(f"{p}.label", "label sem artigo; as frases ficam melhores com 'o/a/os/as'", got=e["label"])
            if "orient" in e:
                _enum(c, f"{p}.orient", e["orient"], V.DIRECTIONS)
            if "brightness" in e:
                _enum(c, f"{p}.brightness", e["brightness"], V.LEVELS)
            if "saturation" in e:
                _enum(c, f"{p}.saturation", e["saturation"], V.SATURATION_LEVELS)
            if "tags" in e:
                tags = _str_list(c, f"{p}.tags", e["tags"])
                for t in tags:
                    if not SLUG.match(t):
                        c.error(f"{p}.tags", "etiqueta deve ser um slug", got=t)
            if "details" in e:
                _str_list(c, f"{p}.details", e["details"])
            # geometria
            n_geo = len(c.items)
            has_box, has_at = "box" in e, "at" in e
            if has_box == has_at:
                c.error(p, "informe exatamente um entre `box` e `at`",
                        hint="box: [x, y, largura, altura] ou at: <região|ponto> (+ size)")
            elif has_box:
                bx = e["box"]
                if not (isinstance(bx, list) and len(bx) == 4 and all(_is_num(v) for v in bx) and bx[2] > 0 and bx[3] > 0):
                    c.error(f"{p}.box", "deve ser [x, y, largura, altura] com largura e altura > 0", got=bx)
            else:
                at_opts = V.POINT_NAMES_LIST
                if e["at"] not in at_opts:
                    c.error(f"{p}.at", "região ou ponto inexistente", got=e["at"], accepted=at_opts, hint=_suggest(e["at"], at_opts))
                if "size" in e:
                    sz = e["size"]
                    if not (isinstance(sz, list) and len(sz) == 2 and all(_is_num(v) and 0 < v <= 1 for v in sz)):
                        c.error(f"{p}.size", "deve ser [largura, altura], cada um em (0, 1]", got=sz)
            if id_bad or any(d.level == "error" for d in c.items[n_geo:]):
                skip.add(i)
                if isinstance(eid, str) and ids_seen.get(eid) == i:
                    c.skipped.add(eid)

    # ---- cena tolerante: permite as checagens cruzadas mesmo com erros ----
    scene: Scene | None = None
    if ratio_ok and grid_ok and isinstance(ents, list) and ents:
        scene = _build_lenient(data, skip)
    if scene is not None:
        for ent in scene.entities:
            bx, by, bw, bh = ent.box
            if bx < -1e-9 or by < -1e-9 or bx + bw > 1 + 1e-9 or by + bh > 1 + 1e-9:
                c.warn(f"entity:{ent.id}", "a caixa ultrapassa os limites do quadro", got=[round(v, 3) for v in ent.box])
            if not scene.in_canvas(ent.center):
                c.warn(f"entity:{ent.id}", f"o centro está fora do formato {scene.canvas_shape} do quadro", got=[round(v, 3) for v in ent.center])
        _check_focus(c, scene)

    # ---- demais seções (dependem das entidades para referências) --------
    _check_intent(c, data, scene)
    _check_camera(c, data, scene)
    _check_palette(c, data)
    _check_lights(c, data, scene)
    _check_gaze(c, data, scene)
    _check_asserts(c, data, scene)
    _check_misc(c, data)
    pal_layer.check(c, data)
    guides.check(c, data, scene)
    fx.check_background(c, data, scene)
    fx.check_atmosphere(c, data, scene)
    materials.check(c, data)
    character.check(c, data, scene)
    pose.check(c, data, scene)
    locate.check(c, data)
    _check_lock(c, data, scene)
    verify_mod.check(c, data)
    lint.check(c, data, scene)

    return c.items, (scene if not c.has_errors else None)


# ---------------------------------------------------------------------------
def _ref_ok(c: _Collector, scene: Scene | None, path: str, ref) -> bool:
    if scene is None:
        return False
    if not isinstance(ref, str):
        c.error(path, "a referência deve ser um texto", got=ref)
        return False
    if ref.split(".")[0] in c.skipped:
        return False  # a entidade já tem erro próprio; não repetir em cascata
    try:
        scene.resolve(ref)
    except RefError as e:
        c.error(path, str(e), got=ref, accepted=e.accepted, hint=_suggest(ref.split(".")[0], e.accepted or []))
        return False
    return True


def _closest(value, options, default):
    m = difflib.get_close_matches(str(value), [str(o) for o in options], n=1, cutoff=0.6)
    return m[0] if m else default


def _build_lenient(data: dict, skip: set[int]) -> Scene | None:
    """Cena provisória para as checagens cruzadas: troca campos inválidos pelo valor
    mais próximo e descarta entidades sem geometria. Nunca é devolvida como cena válida."""
    d = copy.deepcopy(data)
    keep = []
    for i, e in enumerate(d["entities"]):
        if i in skip or not isinstance(e, dict):
            continue
        e["kind"] = e.get("kind") if e.get("kind") in V.KINDS else _closest(e.get("kind"), V.KINDS, "prop")
        e["plane"] = e.get("plane") if e.get("plane") in V.PLANES else _closest(e.get("plane"), V.PLANES, "midground")
        if "orient" in e and e["orient"] not in V.DIRECTIONS:
            e["orient"] = _closest(e["orient"], V.DIRECTIONS, "up")
        if "brightness" in e and e["brightness"] not in V.LEVELS:
            e["brightness"] = _closest(e["brightness"], V.LEVELS, "normal")
        if "saturation" in e and e["saturation"] not in V.SATURATION_LEVELS:
            e["saturation"] = _closest(e["saturation"], V.SATURATION_LEVELS, "normal")
        for key in ("label", "desc"):
            if not isinstance(e.get(key), str) or not e[key].strip():
                e[key] = f"o {e['id']}"
        for key in ("tags", "details"):
            if key in e and not (isinstance(e[key], list) and all(isinstance(x, str) for x in e[key])):
                e[key] = []
        keep.append(e)
    if not keep:
        return None
    d["entities"] = keep
    if not isinstance(d.get("scene"), str):
        d["scene"] = "?"
    if d["canvas"].get("shape", "rect") not in V.CANVAS_SHAPES:
        d["canvas"]["shape"] = "rect"
    return build_scene(d)


def _check_focus(c: _Collector, scene: Scene) -> None:
    maxed = [e for e in scene.entities if e.brightness == "max"]
    if len(maxed) > 1:
        c.error("$.entities", "foco duplo: mais de um elemento com brilho máximo", got=[e.id for e in maxed],
                hint="deixe brightness: max só no ponto focal e rebaixe os demais")
    sat_over = [e.id for e in scene.entities if e.saturation == "max" and e.brightness != "max"]
    if sat_over:
        c.error("$.entities", "saturação máxima fora do ponto focal", got=sat_over,
                hint="saturation: max só no elemento focal")


def _check_intent(c: _Collector, data: dict, scene: Scene | None) -> None:
    intent = data.get("intent")
    if intent is None:
        return
    if not isinstance(intent, dict):
        c.error("$.intent", "deve ser um mapa com emotion, story e focal", got=intent)
        return
    for key in intent:
        if key not in ("emotion", "story", "focal"):
            c.error(f"$.intent.{key}", "campo desconhecido", got=key, accepted=["emotion", "story", "focal"])
    if "focal" not in intent:
        c.error("$.intent.focal", "campo obrigatório: o ponto focal único (entidade ou entidade.âncora)")
        return
    if _ref_ok(c, scene, "$.intent.focal", intent["focal"]) and scene is not None:
        t = scene.resolve(intent["focal"])
        if t.entity is not None and t.entity.brightness != "max":
            c.warn("$.intent.focal", f"a entidade focal {t.entity.id!r} não tem brightness: max",
                   got=t.entity.brightness, hint="o foco deve ser o elemento mais brilhante")
    for key in ("emotion", "story"):
        if key in intent and not isinstance(intent[key], str):
            c.error(f"$.intent.{key}", "deve ser um texto", got=intent[key])


def _check_camera(c: _Collector, data: dict, scene: Scene | None) -> None:
    cam = data.get("camera")
    if cam is None:
        return
    if not isinstance(cam, dict):
        c.error("$.camera", "deve ser um mapa", got=cam)
        return
    for key in cam:
        if key not in CAMERA_KEYS:
            c.error(f"$.camera.{key}", "campo desconhecido", got=key, accepted=sorted(CAMERA_KEYS), hint=_suggest(key, CAMERA_KEYS))
    if "angle" in cam:
        _enum(c, "$.camera.angle", cam["angle"], list(V.ANGLES))
    if "lens" in cam:
        _enum(c, "$.camera.lens", cam["lens"], list(V.LENSES))
    for i, ref in enumerate(cam.get("focus", []) or []):
        _ref_ok(c, scene, f"$.camera.focus[{i}]", ref)


def _check_palette(c: _Collector, data: dict) -> None:
    pal = data.get("palette")
    if pal is None:
        return
    if not isinstance(pal, dict):
        c.error("$.palette", "deve ser um mapa", got=pal)
        return
    for key in pal:
        if key not in PALETTE_KEYS:
            c.error(f"$.palette.{key}", "campo desconhecido", got=key, accepted=sorted(PALETTE_KEYS), hint=_suggest(key, PALETTE_KEYS))
    for key in ("dominant", "notes"):
        if key in pal:
            _str_list(c, f"$.palette.{key}", pal[key])
    for key in ("accent", "accent_use"):
        if key in pal and not isinstance(pal[key], str):
            c.error(f"$.palette.{key}", "deve ser um texto", got=pal[key])


def _check_lights(c: _Collector, data: dict, scene: Scene | None) -> None:
    lights = data.get("lights")
    if lights is None:
        return
    if not isinstance(lights, list):
        c.error("$.lights", "deve ser uma lista", got=lights)
        return
    for i, li in enumerate(lights):
        p = f"$.lights[{i}]"
        if not isinstance(li, dict):
            c.error(p, "cada luz deve ser um mapa", got=li)
            continue
        for key in li:
            if key not in LIGHT_KEYS:
                c.error(f"{p}.{key}", "campo desconhecido", got=key, accepted=sorted(LIGHT_KEYS), hint=_suggest(key, LIGHT_KEYS))
        _enum(c, f"{p}.role", li.get("role"), V.LIGHT_ROLES)
        if not isinstance(li.get("color"), str) or not li.get("color", "").strip():
            c.error(f"{p}.color", "campo obrigatório: texto com a cor da luz")
        if "source" not in li:
            c.error(f"{p}.source", "campo obrigatório: de onde a luz nasce (entidade, região ou ponto)")
        else:
            _ref_ok(c, scene, f"{p}.source", li["source"])
        for j, ref in enumerate(li.get("hits", []) or []):
            _ref_ok(c, scene, f"{p}.hits[{j}]", ref)


def _check_gaze(c: _Collector, data: dict, scene: Scene | None) -> None:
    gaze = data.get("gaze")
    if gaze is None:
        return
    if not isinstance(gaze, list) or not gaze:
        c.error("$.gaze", "deve ser uma lista não vazia de referências", got=gaze)
        return
    ok_all = True
    for i, ref in enumerate(gaze):
        ok_all &= _ref_ok(c, scene, f"$.gaze[{i}]", ref)
    intent = data.get("intent")
    if ok_all and scene is not None and isinstance(intent, dict) and "focal" in intent:
        if str(gaze[0]).strip() != str(intent["focal"]).strip():
            c.error("$.gaze[0]", "a leitura do olhar deve começar no ponto focal", got=gaze[0],
                    hint=f"use {intent['focal']!r} como primeiro item")


def _check_asserts(c: _Collector, data: dict, scene: Scene | None) -> None:
    asserts = data.get("asserts")
    if asserts is None:
        return
    if not isinstance(asserts, list) or not all(isinstance(a, str) for a in asserts):
        c.error("$.asserts", "deve ser uma lista de textos", got=asserts)
        return
    for i, raw in enumerate(asserts):
        p = f"$.asserts[{i}]"
        try:
            a = parse_assert(raw)
        except AssertSyntaxError as e:
            hint = _suggest(raw.split("(")[0].strip(), V.PREDICATES)
            if raw.count("(") != raw.count(")"):
                hint = ("em YAML, a vírgula dentro de [ ] separa itens: escreva os asserts como lista em bloco "
                        "(`- left_of(a, b)`) ou entre aspas (`[\"left_of(a, b)\"]`)")
            c.error(p, str(e), got=raw, accepted=list(V.PREDICATES), hint=hint)
            continue
        if a.name == "count" and a.args[0] not in (data.get("glossary") or {}):
            c.warn(p, "count sem glossário: o prompt sairia com a etiqueta crua", got=a.args[0],
                   hint=f"adicione em glossary: {a.args[0]}: \"<nome no plural>\"")
        if scene is not None and not any(arg.split(".")[0] in c.skipped for arg in a.args):
            try:
                check_refs(scene, a)
            except RefError as e:
                c.error(p, str(e), got=raw, accepted=e.accepted)


def _check_misc(c: _Collector, data: dict) -> None:
    for key in ("details", "avoid", "priority_boost"):
        if key in data:
            _str_list(c, f"$.{key}", data[key])
    if "finish" in data and not isinstance(data["finish"], str):
        c.error("$.finish", "deve ser um texto", got=data["finish"])
    if "glossary" in data and not (isinstance(data["glossary"], dict) and all(isinstance(v, str) for v in data["glossary"].values())):
        c.error("$.glossary", "deve ser um mapa etiqueta → texto no plural", got=data["glossary"])
    for i, text in enumerate(data.get("avoid", []) or []):
        if isinstance(text, str) and to_affirmation(text) is None:
            c.warn(f"$.avoid[{i}]", "negação sem regra de conversão; ela será descartada do prompt",
                   got=text, hint="reescreva como afirmação (o que deve aparecer) em details ou finish")
    boost = data.get("priority_boost", [])
    asserts = data.get("asserts", [])
    if isinstance(boost, list) and isinstance(asserts, list):
        for i, b in enumerate(boost):
            if b not in asserts:
                c.error(f"$.priority_boost[{i}]", "o reforço deve repetir exatamente um item de `asserts`", got=b)
    if isinstance(data.get("asserts"), list) and not data["asserts"]:
        c.warn("$.asserts", "sem asserts não há como verificar a cena")
    if "asserts" not in data:
        c.warn("$.asserts", "sem asserts não há como verificar a cena")


def _check_lock(c: _Collector, data: dict, scene: Scene | None) -> None:
    lock = data.get("lock")
    if lock is None:
        return
    if not isinstance(lock, list) or not all(isinstance(x, str) for x in lock):
        c.error("$.lock", "deve ser uma lista de textos", got=lock)
        return
    valid = set(LOCKABLE) | (set(scene.by_id) if scene is not None else set())
    for i, name in enumerate(lock):
        if scene is not None and name not in valid:
            c.error(f"$.lock[{i}]", "nada com esse nome para travar", got=name, accepted=sorted(valid), hint=_suggest(name, valid))


def load_file(path: str | Path) -> tuple[list[Diagnostic], Scene | None, dict | None]:
    path = Path(path)
    return load_text(path.read_text(encoding="utf-8"), base_dir=path.resolve().parent)


def load_text(text: str, base_dir: str | Path | None = None) -> tuple[list[Diagnostic], Scene | None, dict | None]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return [Diagnostic("error", "$", f"YAML inválido: {e}")], None, None
    try:
        data = variants.resolve(data, Path(base_dir) if base_dir else None)
    except variants.VariantError as e:
        return [Diagnostic("error", "$.extends", str(e))], None, None
    from . import normalize

    data, _notes = normalize.apply_defaults(data)
    diags, scene = validate_data(data)
    return diags, scene, data
