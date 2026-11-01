"""Testes do núcleo. Os casos de falha importam tanto quanto os de sucesso."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from scenelang import layout as L
from scenelang.assertions import AssertSyntaxError, evaluate_all, parse_assert
from scenelang.compile import to_json, to_prose, to_regions
from scenelang.evalform import apply_answers, build_form, dump_scene
from scenelang.render import render_svg, write_render
from scenelang.validate import load_text, validate_data

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "guardia.yaml"


@pytest.fixture()
def data() -> dict:
    return yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))


def errors(diags):
    return [d for d in diags if d.level == "error"]


def messages(diags):
    return " | ".join(str(d) for d in diags)


# ---------------------------------------------------------------- válida
def test_example_is_valid(data):
    diags, scene = validate_data(data)
    assert errors(diags) == [] and scene is not None
    assert [d for d in diags if d.level == "warning"] == []


def test_example_asserts_all_pass(data):
    _, scene = validate_data(data)
    results = evaluate_all(scene)
    assert len(results) == 11 and all(r.ok for r in results), [r for r in results if not r.ok]


# ---------------------------------------------------------------- geometria
def test_golden_lines_and_points():
    assert L.grid_lines("golden")[1] == pytest.approx(0.381966, abs=1e-6)
    assert L.grid_lines("golden")[2] == pytest.approx(0.618034, abs=1e-6)
    assert L.point_xy("golden", "pt_lr") == pytest.approx((0.618034, 0.618034), abs=1e-6)
    assert L.grid_lines("thirds")[1] == pytest.approx(1 / 3)


def test_tip_and_base_follow_orientation():
    box = (0.2, 0.2, 0.2, 0.4)
    assert L.anchor_xy(box, "up_left", "tip") == pytest.approx((0.2, 0.2))
    assert L.anchor_xy(box, "up_left", "base") == pytest.approx((0.4, 0.6))
    assert L.anchor_xy(box, "up_right", "tip") == pytest.approx((0.4, 0.2))
    assert L.anchor_xy(box, "up", "tip") == pytest.approx((0.3, 0.2))


def test_circle_and_ellipse_canvas():
    assert L.canvas_contains("circle", 1.0, 0.5, 0.5)
    assert not L.canvas_contains("circle", 1.0, 0.05, 0.05)  # canto fora do círculo
    assert L.canvas_contains("rect", 1.0, 0.05, 0.05)
    assert not L.canvas_contains("ellipse", 1.0, 0.02, 0.02)
    # 16:9 com círculo inscrito na altura: os cantos laterais ficam fora
    assert not L.canvas_contains("circle", 16 / 9, 0.1, 0.5)


def test_size_px_from_ratio():
    w, h = L.size_px(16 / 9)
    assert w == 1344 and w % 8 == 0 and h % 8 == 0  # múltiplos de 8, exigência de modelos abertos
    assert abs(w / h - 16 / 9) < 0.01  # a proporção muda menos de 1%
    assert L.size_px(9 / 16)[0] < L.size_px(9 / 16)[1]
    assert L.size_px(1.0, "512x512") == (512, 512)
    with pytest.raises(ValueError):
        L.size_px(1.0, "grande")


# ---------------------------------------------------------------- erros do validador
def test_unknown_top_key_suggests(data):
    data["intencao"] = {}
    diags, scene = validate_data(data)
    assert scene is None
    assert any("campo desconhecido" in d.message for d in errors(diags))


def test_enum_error_has_accepted_values_and_hint(data):
    data["entities"][1]["orient"] = "up_lef"
    diags, scene = validate_data(data)
    d = next(d for d in errors(diags) if d.path.endswith(".orient"))
    assert d.got == "up_lef" and "up_left" in d.accepted and "up_left" in d.hint


def test_duplicate_focus_is_blocked(data):
    data["entities"][0]["brightness"] = "max"  # a guerreira também brilha no máximo
    diags, scene = validate_data(data)
    assert scene is None
    assert any("foco duplo" in d.message for d in errors(diags))


def test_max_saturation_outside_focus_is_blocked(data):
    data["entities"][2]["saturation"] = "max"
    diags, _ = validate_data(data)
    assert any("saturação máxima fora do ponto focal" in d.message for d in errors(diags))


def test_tip_without_orient_is_error(data):
    del data["entities"][1]["orient"]
    diags, _ = validate_data(data)
    assert any("exige `orient`" in d.message for d in errors(diags))


def test_reference_to_missing_entity_lists_valid_ones(data):
    data["asserts"].append("above(spear.tip, ombro_fantasma)")
    diags, _ = validate_data(data)
    d = next(d for d in errors(diags) if "não existe" in d.message)
    assert "warrior" in d.accepted


def test_reserved_and_duplicate_ids(data):
    data["entities"][2]["id"] = "top_left"
    data["entities"][3]["id"] = "warrior"
    diags, _ = validate_data(data)
    msgs = messages(errors(diags))
    assert "reservado" in msgs and "repetido" in msgs


def test_geometry_needs_exactly_one_of_box_or_at(data):
    data["entities"][2]["at"] = "mid_center"  # já tem box
    diags, _ = validate_data(data)
    assert any("exatamente um entre `box` e `at`" in d.message for d in errors(diags))


def test_style_mix_must_sum_100(data):
    data["style"]["mix"] = {"a": 70, "b": 20}
    diags, _ = validate_data(data)
    assert any("somar 100" in d.message for d in errors(diags))


def test_gaze_must_start_at_focal(data):
    data["gaze"] = ["warrior.face", "spear.tip"]
    diags, _ = validate_data(data)
    assert any("começar no ponto focal" in d.message for d in errors(diags))


def test_bad_ratio_and_bad_yaml():
    diags, scene, _ = load_text("scene: x\ncanvas: {ratio: 'wide'}\n")
    assert scene is None and any("proporção inválida" in d.message for d in errors(diags))
    diags, scene, _ = load_text("a: [1, 2\n")
    assert scene is None and "YAML inválido" in diags[0].message


def test_unknown_negation_warns_but_known_does_not(data):
    data["avoid"].append("nada de cores feias")
    diags, scene = validate_data(data)
    assert scene is not None  # só aviso
    assert any(d.level == "warning" and "negação sem regra" in d.message for d in diags)


def test_priority_boost_must_match_an_assert(data):
    data["priority_boost"] = ["facing(spear, down)"]
    diags, _ = validate_data(data)
    assert any("repetir exatamente um item" in d.message for d in errors(diags))


# ---------------------------------------------------------------- asserts
@pytest.mark.parametrize("raw", ["foo(a)", "above(a)", "count(ally)", "above(a,b) == 2", "facing(spear, nowhere)", "near(a, b, x)"])
def test_assert_syntax_errors(raw):
    with pytest.raises(AssertSyntaxError):
        parse_assert(raw)


def test_assert_failures_are_detected(data):
    data["entities"][1]["orient"] = "up_right"  # lança aponta para o lado errado
    data["entities"][1]["box"] = [0.381966, 0.381966, 0.17, 0.25]
    _, scene = validate_data(data)
    failed = {r.raw for r in evaluate_all(scene) if not r.ok}
    assert "facing(spear, up_left)" in failed
    # a ponta agora fica no canto superior direito da caixa, longe do ponto da grade
    assert "near(spear.tip, pt_ul)" in failed


def test_visible_fails_when_feet_leave_the_frame(data):
    data["entities"][0]["box"] = [0.30, 0.55, 0.34, 0.68]  # desce para fora do quadro
    _, scene = validate_data(data)
    r = {x.raw: x for x in evaluate_all(scene)}
    assert not r["visible(warrior.feet)"].ok


def test_circular_canvas_flags_entities_and_visibility(data):
    data["canvas"] = {"shape": "circle", "ratio": "1:1"}
    # no exemplo, nenhum centro cai fora do círculo: o aviso não pode disparar
    diags, scene = validate_data(data)
    assert scene is not None
    assert not any("fora do formato" in d.message for d in diags)
    # um farol colado no canto superior direito fica fora do círculo
    data["entities"][7]["box"] = [0.88, 0.0, 0.1, 0.2]
    data["asserts"].append("visible(lighthouse)")
    diags, scene = validate_data(data)
    assert scene is not None
    assert any("fora do formato circle" in d.message for d in diags if d.level == "warning")
    r = {x.raw: x for x in evaluate_all(scene)}
    assert not r["visible(lighthouse)"].ok
    assert r["visible(warrior.feet)"].ok  # os pés continuam dentro do círculo


def test_count_comparisons(data):
    for expr, expected in [("count(ally) >= 2", True), ("count(ally) > 2", False), ("count(ally) != 2", False), ("count(ally) <= 1", False)]:
        d = copy.deepcopy(data)
        d["asserts"] = [expr]
        _, scene = validate_data(d)
        assert evaluate_all(scene)[0].ok is expected, expr


# ---------------------------------------------------------------- compilador
def test_prose_orders_priorities_first_and_uses_screen_directions(data):
    _, scene = validate_data(data)
    text = to_prose(scene)
    assert text.index("PRIORIDADES") < text.index("CENA:") < text.index("ILUMINAÇÃO")
    assert "para cima e para a esquerda (do ponto de vista de quem vê a imagem)" in text
    assert "no ponto de interesse superior esquerdo da grade" in text
    assert "predominantemente splash art de MOBA (70%)" in text


def test_prose_never_repeats_negations(data):
    _, scene = validate_data(data)
    text = to_prose(scene).lower()
    assert "evitar" not in text and "sem texto" not in text and "não " not in text
    assert "imagem limpa" in text  # a negação virou afirmação
    assert "composição assimétrica" in text


def test_prose_contractions(data):
    _, scene = validate_data(data)
    text = to_prose(scene)
    assert "nitidez máxima na ponta da lança de cristal e no rosto da guerreira" in text
    assert "em a " not in text and "de a " not in text


def test_oriented_prop_described_by_tip_and_base(data):
    _, scene = validate_data(data)
    assert "A lança de cristal, com a ponta no ponto de interesse superior esquerdo da grade e a base" in to_prose(scene)


def test_json_has_priorities_first_and_is_valid(data):
    _, scene = validate_data(data)
    out = json.loads(to_json(scene))
    assert next(iter(out)) == "prioridade_maxima"
    assert len(out["prioridade_maxima"]) == 11  # foco + 10 asserts (focal_single já coberto)
    assert set(out["planos"]) == {"foreground", "midground", "background"}


def test_regions_backend_boxes_weights_and_focal(data):
    _, scene = validate_data(data)
    out = json.loads(to_regions(scene, "1344x756"))
    assert out["canvas"]["size_px"] == [1344, 756]
    by_id = {r["id"]: r for r in out["regions"]}
    assert len(by_id) == len(scene.entities)
    assert by_id["spear"]["weight"] == 1.5 and by_id["lighthouse"]["weight"] == 0.6
    assert by_id["spear"]["orient"] == "up_left"
    assert out["focal"]["xy_px"] == [round(0.381966 * 1344), round(0.381966 * 756)]
    assert out["style_weights"] == {"splash art de MOBA": 0.7, "pintura digital semi-realista": 0.3}
    # regiões do fundo vêm antes das do primeiro plano
    planes = [r["plane"] for r in out["regions"]]
    assert planes == sorted(planes, key=["background", "midground", "foreground"].index)


# ---------------------------------------------------------------- renderizador
def test_render_svg_and_png(data, tmp_path):
    _, scene = validate_data(data)
    svg = render_svg(scene)
    assert svg.startswith("<svg") and "Asserts: 11/11 cumpridos" in svg and "foco" in svg
    written = write_render(scene, tmp_path / "cena.png")
    assert (tmp_path / "cena.svg").exists()
    if len(written) == 2:  # rsvg-convert disponível
        assert (tmp_path / "cena.png").read_bytes()[:4] == b"\x89PNG"


def test_render_marks_failed_asserts(data):
    data["entities"][1]["orient"] = "up_right"
    _, scene = validate_data(data)
    assert "✗" in render_svg(scene)


def test_render_circle_canvas(data):
    data["canvas"] = {"shape": "circle", "ratio": "1:1"}
    _, scene = validate_data(data)
    assert "<circle" in render_svg(scene) and "clipPath" in render_svg(scene)


# ---------------------------------------------------------------- laço de correção
def test_eval_form_has_one_question_per_assert(data):
    _, scene = validate_data(data)
    form = yaml.safe_load(build_form(scene))
    assert len(form["itens"]) == 11
    q = next(i for i in form["itens"] if i["assert"] == "above(spear.tip, warrior.shoulder)")
    assert q["pergunta"] == "A ponta da lança de cristal fica acima do ombro da guerreira?"


def test_eval_apply_boosts_failed_items_and_keeps_scene_valid(data):
    _, scene = validate_data(data)
    form = yaml.safe_load(build_form(scene))
    for item in form["itens"]:
        item["ok"] = "sim"
    for item in form["itens"]:
        if item["assert"] == "facing(spear, up_left)":
            item["ok"], item["tag"] = "nao", "direção"
        if item["assert"] == "visible(warrior.feet)":
            item["ok"], item["tag"] = "não", "enquadramento"
    new, failed = apply_answers(scene, yaml.safe_dump(form, allow_unicode=True))
    assert [f["assert"] for f in failed] == ["facing(spear, up_left)", "visible(warrior.feet)"]
    assert new["priority_boost"] == ["facing(spear, up_left)", "visible(warrior.feet)"]
    assert new["history"][-1]["tags"] == ["direção", "enquadramento"]
    diags, scene2, _ = load_text(dump_scene(new))
    assert scene2 is not None
    text = to_prose(scene2)
    first_two = text.split("PRIORIDADES (cumpra primeiro):\n")[1].splitlines()[:3]
    assert first_two[1].startswith("2. (reforço) A orientação")
    assert first_two[2].startswith("3. (reforço) Visível por inteiro")
    assert "LEMBRETE FINAL (crítico):" in text


def test_eval_apply_rejects_bad_answers(data):
    _, scene = validate_data(data)
    form = yaml.safe_load(build_form(scene))
    form["itens"][0]["ok"] = "talvez"
    with pytest.raises(ValueError, match="resposta inválida"):
        apply_answers(scene, yaml.safe_dump(form, allow_unicode=True))
    form["itens"][0]["ok"], form["itens"][0]["tag"] = "nao", "cor"
    with pytest.raises(ValueError, match="tag fora do vocabulário"):
        apply_answers(scene, yaml.safe_dump(form, allow_unicode=True))


def test_unanswered_items_are_not_failures(data):
    _, scene = validate_data(data)
    new, failed = apply_answers(scene, build_form(scene))
    assert failed == [] and "priority_boost" not in new
    assert new["history"][-1]["sem_resposta"] == 11


# ------------------------------------------- todos os erros numa única passada
def test_validator_reports_all_errors_in_one_pass(data):
    spear = next(e for e in data["entities"] if e["id"] == "spear")
    spear["orient"] = "up_lef"                                   # erro de vocabulário
    next(e for e in data["entities"] if e["id"] == "warrior")["brightness"] = "max"  # foco duplo
    data["asserts"].append("above(spear.tip, ombro)")             # referência inexistente
    data["gaze"][0] = "warrior.face"                              # olhar não começa no foco
    data["avoid"].append("nada de cores feias")                   # negação sem regra
    diags, scene = validate_data(data)
    assert scene is None
    msg = messages(diags)
    for expected in ("up_lef", "foco duplo", "ombro", "deve começar no ponto focal", "sem regra de conversão"):
        assert expected in msg, expected
    assert len(errors(diags)) == 4


def test_broken_entity_does_not_cascade_into_reference_errors(data):
    data["entities"][1].pop("kind")        # a lança perde o kind
    data["entities"][1]["box"] = "x"       # e a geometria
    diags, _ = validate_data(data)
    # asserts que citam a lança não geram erros de "referência inexistente" em cascata
    assert not any("referência a algo que não existe" in d.message and "spear" in str(d) for d in errors(diags))


def test_count_without_glossary_warns(data):
    data["glossary"].pop("ally")
    diags, scene = validate_data(data)
    assert scene is not None
    assert any("glossário" in d.message and d.level == "warning" for d in diags)
