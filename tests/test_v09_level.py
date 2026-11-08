"""v0.9: level design — raycast, grafo/topologia, métrica, fluxo, planta baixa, piso conectado e exportadores."""
import json
from pathlib import Path

import pytest
import yaml

from scenelang import api
from scenelang import layout as L
from scenelang.assertions import evaluate_all
from scenelang.compile import BACKENDS
from scenelang.validate import load_text

EX = Path(__file__).resolve().parents[1] / "examples" / "interior_santuario_level.yaml"
BASE = EX.read_text(encoding="utf-8")


def load(text):
    return load_text(text)


def errors(d):
    return [x for x in d if x.level == "error"]


def mutate(fn):
    data = yaml.safe_load(BASE)
    fn(data)
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def ent(data, eid):
    return next(e for e in data["entities"] if e["id"] == eid)


def results(text):
    d, s, _ = load(text)
    assert s is not None, [str(x) for x in errors(d)]
    return {r.raw: r for r in evaluate_all(s)}


# ---- geometria ------------------------------------------------------------------------------------------------
def test_liang_barsky():
    box = (0.4, 0.4, 0.2, 0.2)
    assert L.segment_intersects_box((0.0, 0.5), (1.0, 0.5), box)
    assert not L.segment_intersects_box((0.0, 0.1), (1.0, 0.1), box)
    assert not L.segment_intersects_box((0.0, 0.5), (0.3, 0.5), box)            # para antes da caixa
    assert L.segment_intersects_box((0.5, 0.5), (0.9, 0.9), box)                # começa dentro
    assert not L.segment_intersects_box((0.5, 0.0), (0.5, 0.3), box)            # paralelo, fora
    assert L.segment_intersects_box((0.0, 0.0), (1.0, 1.0), box)                # diagonal


def test_overlap_e_clearance():
    a, b = (0.0, 0.0, 0.2, 0.2), (0.2, 0.0, 0.2, 0.2)
    assert not L.boxes_overlap(a, b)                        # encostar não é sobrepor
    assert L.boxes_overlap(a, (0.1, 0.1, 0.2, 0.2))
    assert L.box_clearance(a, b) == 0
    assert L.box_clearance(a, (0.5, 0.0, 0.1, 0.2), 1.0) == pytest.approx(0.3)
    assert L.box_clearance(a, (0.5, 0.0, 0.1, 0.2), 2.0) == pytest.approx(0.6)   # corrige a proporção


# ---- predicados -----------------------------------------------------------------------------------------------
def test_exemplo_cumpre_todos_os_asserts():
    assert all(r.ok for r in results(BASE).values())


def test_occluded_reprova_quando_o_pilar_sai_do_caminho():
    t = mutate(lambda d: ent(d, "cover_pilar_oeste").update({"box": [0.21, 0.80, 0.06, 0.1]}))
    r = results(t)
    assert not r["occluded(porta_entrada, besta_automatica, cover_pilar_oeste)"].ok
    assert "não intercepta" in r["occluded(porta_entrada, besta_automatica, cover_pilar_oeste)"].detail


def test_line_of_sight_bloqueada_cita_quem_bloqueia():
    t = mutate(lambda d: d["asserts"].append("line_of_sight(porta_entrada, besta_automatica)"))
    r = results(t)["line_of_sight(porta_entrada, besta_automatica)"]
    assert not r.ok and "cover_pilar_oeste" in r.detail


def test_no_overlap_por_etiqueta_e_por_id():
    t = mutate(lambda d: ent(d, "cover_pilar_oeste").update({"box": [0.06, 0.46, 0.05, 0.14]}))   # em cima da porta
    r = results(t)["no_overlap(cover, door)"]
    assert not r.ok and "cover_pilar_oeste×porta_entrada" in r.detail
    assert results(mutate(lambda d: d["asserts"].append("no_overlap(besta_automatica, altar_relicario)")))["no_overlap(besta_automatica, altar_relicario)"].ok


def test_clearance_mede_borda_a_borda():
    t = mutate(lambda d: ent(d, "cover_banco_sul").update({"box": [0.63, 0.40, 0.09, 0.08]}))
    r = results(t)["clearance(cover_banco_norte, cover_banco_sul, 0.12)"]
    assert not r.ok and "folga" in r.detail


def test_predicado_invalido_e_referencias():
    d, s, _ = load(mutate(lambda d: d["asserts"].append("clearance(a, b)")))
    assert errors(d)
    d, s, _ = load(mutate(lambda d: d["asserts"].append("no_overlap(nada, door)")))
    assert any("nem entidade" in x.message for x in errors(d))
    d, s, _ = load(mutate(lambda d: d["asserts"].append("min_paths(atrio_entrada, sala_altar)")))
    assert any("exige comparação" in x.message for x in errors(d))
    d, s, _ = load(mutate(lambda d: d.pop("graph")))
    assert any("exige a seção `graph`" in x.message for x in errors(d))


# ---- topologia ------------------------------------------------------------------------------------------------
def test_softlock_chave_atras_da_propria_porta():
    def f(d):
        d["graph"]["edges"] = [{"from": "atrio_entrada", "to": "corredor_flanco_norte", "via": "porta_grade_norte", "kind": "locked", "unlocked_by": "altar_relicario"},
                               {"from": "corredor_flanco_norte", "to": "sala_altar", "kind": "bidirectional"}]
        d["asserts"] = ["no_softlock(atrio_entrada, altar_relicario)", "reachable(atrio_entrada, altar_relicario)", "focal_single"]
    r = results(mutate(f))
    assert r["reachable(atrio_entrada, altar_relicario)"].ok                       # existe caminho no papel...
    sl = r["no_softlock(atrio_entrada, altar_relicario)"]
    assert not sl.ok and "softlock" in sl.detail and "altar_relicario" in sl.detail  # ...mas a chave está do outro lado


def test_one_way_nao_volta_e_min_paths_linear():
    def f(d):
        d["graph"]["edges"] = [{"from": "atrio_entrada", "to": "sala_altar", "via": "ponte_central", "kind": "one_way"}]
        d["asserts"] = ["reachable(atrio_entrada, sala_altar)", "reachable(sala_altar, atrio_entrada)", "min_paths(atrio_entrada, sala_altar) >= 2",
                        "min_paths(atrio_entrada, sala_altar) == 1", "focal_single"]
    r = results(mutate(f))
    assert r["reachable(atrio_entrada, sala_altar)"].ok and not r["reachable(sala_altar, atrio_entrada)"].ok
    assert not r["min_paths(atrio_entrada, sala_altar) >= 2"].ok and r["min_paths(atrio_entrada, sala_altar) == 1"].ok


def test_min_paths_menger_com_arestas_paralelas():
    def f(d):
        d["graph"]["edges"].append({"from": "atrio_entrada", "to": "sala_altar", "via": "porta_grade_norte", "kind": "hazard"})
        d["asserts"] = ["min_paths(atrio_entrada, sala_altar) == 3", "focal_single"]
    assert results(mutate(f))["min_paths(atrio_entrada, sala_altar) == 3"].ok


def test_connected_confere_geometria_do_via():
    t = mutate(lambda d: ent(d, "ponte_central").update({"box": [0.30, 0.95, 0.28, 0.05]}))
    r = results(t)["connected(atrio_entrada, sala_altar)"]
    assert not r.ok and "ponte_central" in r.detail


def test_grafo_validacao():
    def bad(fn, frag):
        d, s, _ = load(mutate(fn))
        assert any(frag in (x.message + x.path) for x in errors(d)), [str(x) for x in d]
    bad(lambda d: d["graph"]["edges"][2].pop("unlocked_by"), "unlocked_by")
    bad(lambda d: d["graph"]["edges"][0].update({"kind": "magico"}), "kind")
    bad(lambda d: d["graph"]["edges"][0].update({"to": "fantasma"}), "inexistente")
    bad(lambda d: d["graph"]["nodes"][0].update({"role": "chefe"}), "role")
    bad(lambda d: d["graph"].update({"spawn": "ponte_central"}), "graph.spawn")
    bad(lambda d: d["graph"]["edges"][0].update({"to": "atrio_entrada"}), "ele mesmo")


# ---- métrica --------------------------------------------------------------------------------------------------
def test_metrica_avisa_porta_estreita_com_fix():
    t = mutate(lambda d: ent(d, "porta_entrada").update({"box": [0.06, 0.46, 0.05, 0.04]}))
    d, s, _ = load(t)
    w = [x for x in d if x.level == "warning" and "porta_entrada" in x.path]
    assert w and "mínimo é 3" in w[0].message and w[0].fix and w[0].fix["path"].endswith(".box")
    fixed = w[0].fix["value"]
    assert fixed[3] * 64 / (16 / 9) >= 3 - 1e-6          # a caixa corrigida cumpre o mínimo


def test_metrica_exige_pixel_grid():
    d, s, _ = load(mutate(lambda d: d["canvas"].pop("pixel_grid")))
    assert any("pixel_grid" in x.message for x in errors(d))


# ---- fluxo ----------------------------------------------------------------------------------------------------
def test_fluxo_validacao_e_prompt():
    d, s, _ = load(mutate(lambda d: d["flow"]["sight_cones"][0].update({"source": "ponte_central", "angle_deg": 500})))
    msgs = " ".join(x.path + x.message for x in errors(d))
    assert "angle_deg" in msgs
    d, s, _ = load(mutate(lambda d: d["flow"]["routes"]["critical"].update({"points": ["porta_entrada.center", "fantasma"]})))
    assert any("points[1]" in x.path for x in errors(d))
    d, s, _ = load(mutate(lambda d: ent(d, "besta_automatica").pop("orient")))
    assert any("orient" in x.message for x in errors(d))


def test_prompt_traz_topologia_e_fluxo_mas_nao_predicados_de_projeto():
    _, s, _ = load(BASE)
    txt = BACKENDS["prose"](s)
    assert "TOPOLOGIA:" in txt and "FLUXO:" in txt and "trancada" in txt and "cone de 45°" in txt
    pri = txt.split("PRIORIDADES")[1].split("INTENÇÃO")[0]
    assert "caminhos independentes" not in pri and "sem ficar preso" not in pri     # só têm sentido na planta
    assert "linha de visão" in pri or "bloqueia a visão" in pri                        # visão chega ao gerador
    for target in ("compact", "json", "regions"):
        assert "trancada" in BACKENDS[target](s)


# ---- render ---------------------------------------------------------------------------------------------------
def test_render_planta_baixa():
    from scenelang.render import render_svg

    _, s, _ = load(BASE)
    svg = render_svg(s, style="floorplan")
    assert "hatch_full" in svg and "grafo de nós" in svg and "5 células = 2.5 m" in svg and "polygon" in svg
    assert "grafo de nós" not in render_svg(s)
    with pytest.raises(ValueError):
        render_svg(s, style="isometrico")


# ---- piso conectado -------------------------------------------------------------------------------------------
def _rooms(extra_verify=None):
    return """
scene: duas salas
canvas: {shape: rect, ratio: "2:1"}
grid: {kind: thirds}
style: {base: planta}
intent: {focal: b}
flow: {player_radius: 0.02}
verify: ["walkable_connected(a, b)"]
entities:
  - {id: a, kind: structure, label: a sala a, desc: sala, plane: background, box: [0.05, 0.3, 0.25, 0.4]}
  - {id: b, kind: structure, label: a sala b, desc: sala, plane: background, box: [0.70, 0.3, 0.25, 0.4], brightness: max}
asserts:
  - left_of(a, b)
"""


def _img(gap: bool, gap_h=30):
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (400, 200), (30, 30, 40))                       # parede/abismo escuro
    d = ImageDraw.Draw(im)
    d.rectangle([20, 60, 120, 140], fill=(200, 190, 170))                # piso da sala a
    d.rectangle([280, 60, 380, 140], fill=(200, 190, 170))               # piso da sala b
    if gap:
        d.rectangle([120, 100 - gap_h // 2, 280, 100 + gap_h // 2], fill=(200, 190, 170))   # corredor
    return im


def test_walkable_connected_com_e_sem_corredor():
    pytest.importorskip("scipy")
    from scenelang import verify

    d, s, _ = load(_rooms())
    assert not errors(d), [str(x) for x in d]
    assert verify.run(s, _img(True))[0].ok
    bad = verify.run(s, _img(False))[0]
    assert not bad.ok and "NÃO conectado" in bad.detail


def test_walkable_gargalo_mais_estreito_que_o_jogador():
    pytest.importorskip("scipy")
    from scenelang import verify

    _, s, _ = load(_rooms())
    assert not verify.run(s, _img(True, gap_h=4))[0].ok          # fresta de 4 px < raio do jogador (4 px de erosão)


def test_walkable_inconclusivo_reprova():
    pytest.importorskip("scipy")
    from PIL import Image

    from scenelang import verify

    _, s, _ = load(_rooms())
    r = verify.run(s, Image.new("RGB", (400, 200), (30, 30, 40)))[0]
    assert r.ok and "conectado" in r.detail          # imagem lisa: tudo é piso e conecta (a medição não quebra nem inventa parede)


def test_walkable_ids_desconhecidos():
    d, s, _ = load(_rooms().replace("walkable_connected(a, b)", "walkable_connected(a, zzz)"))
    assert any("zzz" in x.message for x in errors(d))


# ---- correção -------------------------------------------------------------------------------------------------
def test_todo_predicado_novo_tem_regra_de_correcao():
    from scenelang.correction import rules as RL
    from scenelang.correction.types import Finding

    for raw in ("line_of_sight(a, b)", "occluded(a, b)", "no_overlap(a, b)", "clearance(a, b, 0.1)", "connected(a, b)", "reachable(a, b)",
                "no_softlock(a, b)", "min_paths(a, b) >= 2", "clear_zone(z)"):
        assert RL.rule_for(Finding("layout", raw, False, "x", "imagem", 0.95)) is not None, raw
    assert RL.rule_for(Finding("verify", "walkable_connected(a, b)", False, "x", "imagem", 0.95)) is not None
    assert RL.rule_for(Finding("verify", "zone_quiet(z)", False, "x", "imagem", 0.95)) is not None


def test_regra_de_piso_conectado_texto_e_escalada():
    from scenelang.correction.rules import Ctx, WalkableRule
    from scenelang.correction.types import Finding

    _, s, _ = load(BASE)
    f = Finding("verify", "walkable_connected(porta_entrada, altar_relicario)", False, "x", "imagem", 0.95)
    t0, t1 = WalkableRule().build(Ctx(s, []), f, 0), WalkableRule().build(Ctx(s, []), f, 1)
    assert "Desobstrua a passagem contínua" in t0 and t0 != t1 and "_" not in t0


# ---- exportadores ---------------------------------------------------------------------------------------------
def test_exportadores():
    from scenelang import level_export as LE

    _, s, _ = load(BASE)
    mm = LE.export(s, "mermaid")
    assert mm.startswith("flowchart LR") and "-.->" in mm and "🔒" in mm
    td = json.loads(LE.export(s, "tiled"))
    assert (td["width"], td["height"], td["tilewidth"]) == (64, 36, 32)
    assert sum(len(l["objects"]) for l in td["layers"]) == len(s.entities)
    obj = next(o for l in td["layers"] for o in l["objects"] if o["name"] == "porta_entrada")
    assert obj["x"] == pytest.approx(0.06 * 64 * 32) and {"name": "orient", "type": "string", "value": "right"} in obj["properties"]
    gd = LE.export(s, "godot")
    assert gd.count("CSGBox3D") == len(s.entities) and gd.startswith("[gd_scene")
    un = json.loads(LE.export(s, "unity"))
    pilar = next(b for b in un["blocks"] if b["name"] == "cover_pilar_oeste")
    assert pilar["scale"]["y"] == 2.2 and pilar["scale"]["x"] == pytest.approx(0.06 * 64 * 0.5)     # full_cover 2,2 m; 0,06·64 células·0,5 m
    with pytest.raises(LE.ExportError, match="ldtk"):
        LE.export(s, "ldtk")
    with pytest.raises(LE.ExportError):
        LE.export(s, "obj")


def test_exportador_exige_pixel_grid_e_grafo():
    from scenelang import level_export as LE

    _, s, _ = load(mutate(lambda d: (d["canvas"].pop("pixel_grid"), d["guides"].pop("metrics"), d["guides"].pop("margin"))))
    with pytest.raises(LE.ExportError, match="pixel_grid"):
        LE.export(s, "godot")
    _, s2, _ = load(mutate(lambda d: (d.pop("graph"), d.__setitem__("asserts", ["focal_single"]))))
    with pytest.raises(LE.ExportError, match="graph"):
        LE.export(s2, "mermaid")


def test_api_level_export_e_budget(tmp_path):
    r = api.level_export(BASE, "unity", str(tmp_path / "x" / "l.json"))
    assert r["ok"] and (tmp_path / "x" / "l.json").exists()
    assert not api.level_export(BASE, "ldtk")["ok"]
    c = api.compile_scene(BASE, "prose", token_budget=600)
    assert c["ok"] and c["budget"]["tokens"] <= 600 or not c["budget"]["fits"]
    assert not api.compile_scene(BASE, "json", token_budget=100)["ok"]


def test_metrica_tolera_arredondamento_da_caixa():
    # 3 células exatas escritas com 4 casas (0.0469·64 = 3.0016; 0.0468·64 = 2.9952) não podem virar «3.0 < 3»
    t = mutate(lambda d: (d["guides"]["metrics"].update({"door_width_cells": 3}), ent(d, "porta_grade_norte").update({"box": [0.64, 0.22, 0.0468, 0.06]})))
    d, _, _ = load(t)
    assert not [x for x in d if x.level == "warning" and "porta_grade_norte" in x.path]


def test_requires_detecta_atalho_que_contorna_a_trava():
    ok = mutate(lambda d: d["asserts"].append("requires(atrio_entrada, sala_altar, mecanismo_grade)"))
    # no exemplo a ponte liga direto: a chave NÃO é obrigatória (e o predicado diz isso)
    r = results(ok)["requires(atrio_entrada, sala_altar, mecanismo_grade)"]
    assert not r.ok and "NÃO é obrigatória" in r.detail

    def sem_ponte(d):
        d["graph"]["edges"] = [e for e in d["graph"]["edges"] if e.get("via") != "ponte_central"]
        d["asserts"] = ["requires(atrio_entrada, sala_altar, mecanismo_grade)", "focal_single"]
    r2 = results(mutate(sem_ponte))["requires(atrio_entrada, sala_altar, mecanismo_grade)"]
    assert r2.ok and "exige a chave" in r2.detail


def test_requires_chave_que_nao_abre_nada_e_inalcancavel():
    def f(d):
        d["asserts"] = ["requires(atrio_entrada, sala_altar, cover_pilar_oeste)", "focal_single"]
    r = results(mutate(f))["requires(atrio_entrada, sala_altar, cover_pilar_oeste)"]
    assert not r.ok and "não abre nenhuma passagem" in r.detail
