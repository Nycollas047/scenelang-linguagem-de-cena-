"""Testes das camadas novas: cor, guias, chromakey, atmosfera, materiais, verificadores e plano."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from scenelang import color as C
from scenelang import fx, guides
from scenelang import plan as plan_mod
from scenelang import verify as V
from scenelang.compile import to_json, to_prose, to_regions
from scenelang.validate import validate_data

ROOT = Path(__file__).resolve().parent.parent
PIXEL = ROOT / "examples" / "pixel_heroi.yaml"

PROPOSAL = {
    "palette": {"main": [230, 120, 40], "gold": [240, 190, 60], "brown": [120, 70, 40]},
    "guides": {"head_top": 0.08, "chin": 0.29, "shoulder": 0.3425, "waist": 0.542, "knee": 0.735, "baseline": 0.92},
}


@pytest.fixture()
def data() -> dict:
    return yaml.safe_load(PIXEL.read_text(encoding="utf-8"))


@pytest.fixture()
def planned(data) -> dict:
    return plan_mod.apply_plan(data, PROPOSAL)


def errors(diags):
    return [d for d in diags if d.level == "error"]


def messages(diags):
    return " | ".join(str(d) for d in diags)


# ------------------------------------------------------------------ cor
@pytest.mark.parametrize("spec,expected", [
    ("#f80", (255, 136, 0)), ("#1b1b26", (27, 27, 38)), ({"rgb": [1, 2, 3]}, (1, 2, 3)),
    ({"cmyk": [0, 100, 100, 0]}, (255, 0, 0)), ({"hsl": [120, 100, 50]}, (0, 255, 0)),
])
def test_color_formats(spec, expected):
    assert C.parse_color(spec) == expected


@pytest.mark.parametrize("bad", ["verde", {"rgb": [1, 2]}, {"cmyk": [0, 0, 0, 120]}, {"x": 1}, 42])
def test_color_errors(bad):
    with pytest.raises(C.ColorError):
        C.parse_color(bad)


def test_color_metrics():
    assert C.contrast_ratio((0, 0, 0), (255, 255, 255)) == pytest.approx(21.0, abs=0.1)
    assert C.delta_e((10, 10, 10), (10, 10, 10)) == 0
    assert C.delta_e((0, 255, 0), (255, 0, 255)) > 100
    assert C.rgb_to_cmyk((255, 255, 255)) == (0, 0, 0, 0)


def test_harmony():
    assert C.check_harmony([(240, 130, 30), (245, 215, 50), (200, 30, 40)], "analogous")[0]
    assert C.check_harmony([(240, 130, 30), (40, 90, 210)], "complementary")[0]
    assert not C.check_harmony([(240, 130, 30), (40, 90, 210), (50, 160, 70)], "complementary")[0]
    assert C.check_harmony([(240, 130, 30), (50, 160, 70)], "monochromatic")[0] is False


def test_pixel_example_is_valid(data):
    diags, scene = validate_data(data)
    assert scene is not None and not diags


def test_named_color_reference_and_errors(data):
    data["palette"]["colors"]["outline"] = "@naoexiste"
    assert "cor nomeada inexistente" in messages(errors(validate_data(data)[0]))
    data["palette"]["colors"]["outline"] = {"rgb": [300, 0, 0]}
    assert "fora de" in messages(errors(validate_data(data)[0]))


# ------------------------------------------------------------- paleta do modelo
def test_plan_request_lists_what_the_model_must_answer(data):
    _, scene = validate_data(data)
    req = plan_mod.plan_request(scene)
    assert req["palette"]["faltam_escolher"] == 3
    assert req["palette"]["cores_fixas_nao_mudar"]["outline"] == "#1b1b26"
    assert req["guides"]["linhas"][0] == "head_top" and req["guides"]["cabecas_de_altura"] == 4.0


def test_valid_proposal_is_accepted(planned):
    diags, scene = validate_data(planned)
    assert scene is not None, messages(diags)


def test_proposal_cannot_change_fixed_color(planned):
    planned["palette"]["proposal"]["outline"] = {"rgb": [255, 255, 255]}
    assert "mudou uma cor fixa" in messages(errors(validate_data(planned)[0]))


def test_proposal_checks_count_harmony_and_distance(planned):
    p = copy.deepcopy(planned)
    p["palette"]["proposal"]["extra"] = {"rgb": [10, 10, 200]}
    assert "esperado 5" in messages(errors(validate_data(p)[0]))
    p = copy.deepcopy(planned)
    p["palette"]["proposal"]["main"] = {"rgb": [40, 90, 210]}   # azul: fora da análoga laranja
    assert "harmonia" in messages(errors(validate_data(p)[0]))
    p = copy.deepcopy(planned)
    p["palette"]["proposal"]["gold"] = {"rgb": [231, 121, 41]}  # quase igual a 'main'
    assert "parecidas demais" in messages(errors(validate_data(p)[0]))


def test_cmyk_space_proposal(data):
    data["palette"]["space"] = "cmyk"
    new = plan_mod.apply_plan(data, {"palette": {"main": [0, 60, 90, 5], "gold": [0, 30, 90, 0], "brown": [40, 70, 90, 30]}})
    assert new["palette"]["proposal"]["main"] == {"cmyk": [0, 60, 90, 5]}
    assert not errors(validate_data(new)[0])


def test_prose_asks_model_to_pick_then_states_chosen_colors(data, planned):
    _, s1 = validate_data(data)
    assert "escolha 3 cor(es) base" in to_prose(s1)
    _, s2 = validate_data(planned)
    assert "cores escolhidas" in to_prose(s2) and "escolha 3" not in to_prose(s2)
    assert "no máximo 16 cores" in to_prose(s2)


# ----------------------------------------------------------------------- guias
def test_canon_fractions_are_ordered():
    for heads in (2, 4, 7.5, 8):
        fr = guides.canonical_fractions(heads)
        seq = [fr[n] for n in guides.LINE_ORDER]
        assert seq == sorted(seq) and seq[0] == 0 and seq[-1] == 1


def test_guides_from_canon_and_prose(data):
    data["guides"]["mode"] = "fixed"
    diags, scene = validate_data(data)
    assert scene is not None, messages(diags)
    lines = guides.guide_lines(scene)
    assert lines["head_top"] == pytest.approx(0.08) and lines["baseline"] == pytest.approx(0.92)
    prose = to_prose(scene)
    assert "4 cabeças de altura" in prose and "25% da altura" in prose and "grade de 32×32" in prose


def test_guide_proposal_validation(planned):
    p = copy.deepcopy(planned)
    p["guides"]["proposal"]["chin"] = 0.34            # cabeça de 31% da altura; para 4 cabeças o certo é 25%
    assert "cânone pede" in messages(errors(validate_data(p)[0]))
    p = copy.deepcopy(planned)
    p["guides"]["proposal"]["waist"] = 0.2            # fora de ordem
    assert "saem da ordem" in messages(errors(validate_data(p)[0]))
    p = copy.deepcopy(planned)
    p["guides"]["proposal"]["foo"] = 0.5
    assert "vocabulário fechado" in messages(errors(validate_data(p)[0]))


def test_guides_misc_errors(data):
    data["guides"]["subject"] = "ninguem"
    data["guides"]["canon"] = "gigante"
    data["canvas"]["pixel_grid"] = 2
    msg = messages(errors(validate_data(data)[0]))
    assert "entidade inexistente" in msg and "cânone inválido" in msg and "pixel_grid" in msg


# --------------------------------------------------------------------- chromakey
def test_key_is_auto_chosen_away_from_mentioned_colors(data):
    # a cavaleira tem capa azul e a pele é quente: a chave não pode ser azul nem laranja
    key = fx.key_color(data)
    assert key in [(0, 255, 0), (255, 0, 255)]
    assert C.delta_e(key, C.name_to_rgb("azul")) > 60


def test_explicit_key_close_to_palette_warns(data):
    data["background"]["key"] = {"rgb": [255, 170, 140]}   # quase a cor da pele
    diags, _ = validate_data(data)
    assert any("vai vazar" in d.message for d in diags if d.level == "warning")


def test_translucent_and_effects_warn_with_chroma(data):
    data["entities"][0]["translucent"] = True
    assert any("translúcida" in d.message for d in validate_data(data)[0])
    data["entities"][0]["translucent"] = False
    data["entities"].append({"id": "spark", "kind": "effect", "label": "faíscas", "desc": "faíscas", "plane": "foreground", "box": [0.1, 0.1, 0.05, 0.05]})
    assert any("recorta mal" in d.message for d in validate_data(data)[0])
    data["background"]["alpha"] = "difference"
    assert not any("recorta mal" in d.message for d in validate_data(data)[0])


def test_difference_alpha_prompts_use_black_and_white(data):
    data["background"]["alpha"] = "difference"
    _, scene = validate_data(data)
    assert "preto (#000000)" in to_prose(scene, "black")
    assert "branco (#ffffff)" in to_prose(scene, "white")


def test_background_prose_has_rules(data):
    _, scene = validate_data(data)
    prose = to_prose(scene)
    assert "FUNDO: Fundo de chroma key" in prose and "sem degradê" in prose and "bordas nítidas" in prose


# -------------------------------------------------------------------- atmosfera
def test_atmosphere_prose_and_wind_propagation(data):
    _, scene = validate_data(data)
    prose = to_prose(scene)
    assert "ATMOSFERA: Clima emocional sereno" in prose
    assert "soprando para a direita" in prose and "do ponto de vista de quem vê" in prose
    assert "Com o vento, a capa flui para a direita." in prose


def test_wind_conflict_is_an_error(data):
    data["entities"][0]["wind_parts"] = {"cape": "left"}
    msg = messages(errors(validate_data(data)[0]))
    assert "contra o vento" in msg


def test_wind_parts_without_wind_warn(data):
    del data["atmosphere"]["wind"]
    assert any("não define atmosphere.wind" in d.message for d in validate_data(data)[0])


def test_calm_mood_with_storm_warns(data):
    data["atmosphere"].update({"weather": "storm", "mood": {"name": "serene", "level": "high"}})
    assert any("contraditório" in d.message for d in validate_data(data)[0])


def test_atmosphere_vocabulary_errors(data):
    data["atmosphere"]["mood"]["name"] = "feliz"
    data["atmosphere"]["wind"]["direction"] = "norte"
    msg = messages(errors(validate_data(data)[0]))
    assert "'feliz'" in msg and "'norte'" in msg


def test_rain_leans_with_wind(data):
    data["atmosphere"]["weather"] = "rain"
    _, scene = validate_data(data)
    assert "chuva, inclinada para a direita" in to_prose(scene)


# --------------------------------------------------------------------- materiais
def test_material_phrases_and_detail_budget(data):
    prose = to_prose(validate_data(data)[1])
    assert "metal polido, quase novo, grão fino, brilho forte" in prose
    assert "textura e detalhe máximos no ponto focal" in prose


def test_material_errors_and_contradictions(data):
    data["materials"]["aco_polido"]["wear"] = "high"
    assert any("contraditório" in d.message for d in validate_data(data)[0])
    data["materials"]["aco_polido"]["base"] = "plastico"
    assert "'plastico'" in messages(errors(validate_data(data)[0]))
    data["entities"][0]["parts"]["armor"] = "inexistente"
    assert "material inexistente" in messages(errors(validate_data(data)[0]))


def test_double_max_detail_is_an_error(data):
    data["detail"]["background"] = "max"
    assert "detalhe máximo duplo" in messages(errors(validate_data(data)[0]))
    data["detail"]["background"] = "low"
    data["entities"][0]["detail"] = "max"
    assert "detalhe máximo duplo" in messages(errors(validate_data(data)[0]))


# ----------------------------------------------------------------------- lock
def test_lock_names_and_prose(data):
    data["lock"] = ["knight", "palette"]
    diags, scene = validate_data(data)
    assert scene is not None
    assert "Mantenha exatamente igual à versão anterior: a cavaleira; a paleta de cores." in to_prose(scene)
    data["lock"] = ["knigth"]
    assert "nada com esse nome" in messages(errors(validate_data(data)[0]))


# ------------------------------------------------------------ outros backends
def test_json_and_regions_include_new_layers(planned):
    _, scene = validate_data(planned)
    js = __import__("json").loads(to_json(scene))
    assert "fundo" in js and "atmosfera" in js and "guias" in js
    reg = __import__("json").loads(to_regions(scene))
    assert "chroma key" in reg["global_prompt"] and "vento" in reg["global_prompt"]


# ------------------------------------------------------------------ verify DSL
@pytest.mark.parametrize("raw", ["max_colors()", "foo(1)", "symmetric(horizontal)", "grid_aligned(-1)", "max_colors 16", "margin(1, 2)"])
def test_verify_syntax_errors(raw, data):
    data["verify"] = [raw]
    assert errors(validate_data(data)[0])


def test_verify_requires_matching_layers(data):
    del data["guides"]
    data["verify"] = ["fit_guides(0.04)"]
    assert "exige a camada guides" in messages(errors(validate_data(data)[0]))
    data["background"]["mode"] = "scene"
    data["verify"] = ["chroma_clean()"]
    assert "exige background.mode: chromakey" in messages(errors(validate_data(data)[0]))


# ----------------------------------------------------- verificadores sobre imagem
np = pytest.importorskip("numpy")
Image = pytest.importorskip("PIL.Image")


def make_sprite(scene, scale=16, flawed=None):
    """Sprite 32×32 simétrico sobre a chave, dentro das guias propostas."""
    key = fx.key_color(scene.data)
    cells = np.zeros((32, 32, 3), "uint8")
    cells[:] = key
    skin, orange, ink = (255, 178, 140), (230, 120, 40), (27, 27, 38)
    cells[3:10, 12:20] = skin
    cells[10:25, 10:22] = orange
    cells[25:30, 12:16] = ink
    cells[25:30, 16:20] = ink
    if flawed == "asym":
        cells[12:20, 10:14] = ink
    if flawed == "spill":
        cells[12:22, 11:21] = (40, 225, 40)   # verde vazando para dentro do corpo
    img = Image.fromarray(cells).resize((32 * scale, 32 * scale), Image.NEAREST)
    return img


def results(scene, img):
    return {r.raw: r for r in V.run(scene, img)}


def test_clean_sprite_passes_all_verifiers(planned):
    _, scene = validate_data(planned)
    res = results(scene, make_sprite(scene))
    bad = {k: v.detail for k, v in res.items() if not v.ok}
    assert not bad, bad
    assert len(res) == 7


def test_blurred_image_fails_pixel_checks(planned):
    from PIL import ImageFilter
    _, scene = validate_data(planned)
    img = make_sprite(scene, scale=16).resize((512, 512), Image.BILINEAR).filter(ImageFilter.GaussianBlur(5))
    res = results(scene, img)
    assert not res["grid_aligned(32)"].ok


def test_asymmetry_and_spill_are_detected(planned):
    _, scene = validate_data(planned)
    assert not results(scene, make_sprite(scene, flawed="asym"))["symmetric(vertical, 0.8)"].ok
    spill = results(scene, make_sprite(scene, flawed="spill"))
    assert not spill["no_spill()"].ok
    assert not spill["palette_match(10)"].ok


def test_wrong_palette_and_too_many_colors(planned):
    _, scene = validate_data(planned)
    img = make_sprite(scene)
    arr = np.asarray(img).copy()
    arr[200:260, 200:330] = (10, 160, 200)         # cor fora da paleta
    res = results(scene, Image.fromarray(arr))
    assert res["palette_match(10)"].score < 1
    scene.data["verify"] = ["max_colors(2)"]
    assert not V.run(scene, img)[0].ok


def test_fit_guides_detects_a_misplaced_sprite(planned):
    _, scene = validate_data(planned)
    img = make_sprite(scene)
    shifted = Image.new("RGB", img.size, fx.key_color(scene.data))
    shifted.paste(img, (0, 80))                    # desce 80 px: pés passam do baseline
    assert not results(scene, shifted)["fit_guides(0.04)"].ok


def test_chroma_unclean_background_is_detected(planned):
    _, scene = validate_data(planned)
    arr = np.asarray(make_sprite(scene)).copy()
    arr[:60, :] = (120, 120, 120)                  # faixa cinza no topo
    assert not results(scene, Image.fromarray(arr))["chroma_clean()"].ok


def test_cutout_chroma_makes_background_transparent(planned):
    _, scene = validate_data(planned)
    out = V.cutout_chroma(scene, make_sprite(scene))
    a = np.asarray(out)[..., 3]
    assert a[5, 5] == 0 and a[350, 256] == 255     # canto = fundo; corpo = sujeito
    assert out.mode == "RGBA"


def test_cutout_difference_recovers_translucency():
    # pixel com cor (200, 50, 50) e alfa 0,5 sobre preto e sobre branco
    on_black = Image.new("RGB", (4, 4), (100, 25, 25))
    on_white = Image.new("RGB", (4, 4), (227, 152, 152))
    out = np.asarray(V.cutout_difference(on_black, on_white))
    assert abs(int(out[0, 0, 3]) - 127) <= 2
    assert abs(int(out[0, 0, 0]) - 200) <= 3
    with pytest.raises(ValueError):
        V.cutout_difference(on_black, Image.new("RGB", (5, 5)))
