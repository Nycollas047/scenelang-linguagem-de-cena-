"""v0.8: correções do relatório de campo (pt_ul, grade áurea, hold, concordância, bench) e sintaxe nova."""
from pathlib import Path

import pytest
import yaml

from scenelang import anatomy as AN
from scenelang import pose_presets as PP
from scenelang.compile import BACKENDS, compile_budget
from scenelang.validate import load_text

FIX = Path(__file__).with_name("_forja_fixture.yaml").read_text(encoding="utf-8")


def load(text):
    d, s, data = load_text(text)
    return d, s, data


def errors(d):
    return [x for x in d if x.level == "error"]


def mutate(fn):
    data = yaml.safe_load(FIX)
    fn(data)
    return yaml.safe_dump(data, allow_unicode=True)


# ---- correções do relatório ---------------------------------------------------------------------------------
def test_verify_sem_verificador_nao_abre_imagem():
    from scenelang import verify

    _, s, _ = load(FIX)
    assert verify.run(s, None) == []          # nem numpy nem imagem


def test_svg_to_png_devolve_bool(tmp_path):
    from scenelang.render import svg_to_png

    svg = tmp_path / "a.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>')
    assert isinstance(svg_to_png(svg, tmp_path / "a.png"), bool)


def test_correcao_nao_vaza_id_de_ponto():
    from scenelang.correction.rules import Ctx, PositionRule
    from scenelang.correction.types import Finding

    data = mutate(lambda d: d.__setitem__("asserts", ["near(orb, pt_ul)"]))
    _, s, _ = load(data)
    txt = PositionRule().build(Ctx(s, []), Finding("layout", "near(orb, pt_ul)", False, "x", "imagem", 0.95), 0)
    assert "pt_ul" not in txt and "ponto de interesse superior esquerdo" in txt


def test_grade_aurea_descreve_ponto_em_vez_de_centro():
    from scenelang import phrases as P

    data = mutate(lambda d: d["entities"][2].update({"at": "pt_ul", "size": [0.10, 0.14]}))
    _, s, _ = load(data)
    assert "ponto de interesse superior esquerdo" in P.entity_position(s.by_id["orb"], "golden")


def test_hold_resolve_rotulo_e_coluna_no_feminino():
    from scenelang import pose as PO

    _, s, _ = load(FIX)
    txt = PO.sentence(s, "mage")
    assert "segura/toca o martelo rúnico" in txt and "hammer" not in txt
    assert "a coluna dobrada" in txt and "a coluna dobrado" not in txt
    assert "torcida" in txt


def test_material_concorda_com_genero():
    from scenelang import materials as M

    assert M._agree("áspero", "pedra") == "áspera"
    assert M._agree("polido", "metal") == "polido"


def test_bench_record_usa_cena_do_plano(tmp_path, capsys):
    from scenelang import bench

    bench.plan(FIX, tmp_path)
    assert (tmp_path / "cena.yaml").exists()
    bench.record(tmp_path, "completa", "r1", boxes={})
    assert "sem --scene" not in capsys.readouterr().err


# ---- at relativo ----------------------------------------------------------------------------------------------
def test_at_relativo_calcula_box_e_asserts():
    d, s, data = load(FIX)
    assert not errors(d), d
    assert abs(s.by_id["anvil"].box[0] - (0.14 + 0.20 + 0.02)) < 1e-3          # right_of(mage, gap 0.02)
    assert s.by_id["orb"].box[1] + s.by_id["orb"].box[3] <= s.by_id["anvil"].box[1] + 1e-9   # above(anvil)
    assert "right_of(anvil, mage)" in data["asserts"] and "above(orb, anvil)" in data["asserts"]
    assert all("at" not in e for e in data["entities"])


def test_at_ciclo_e_chave_desconhecida_sao_erros():
    def cyc(d):
        d["entities"][1]["at"] = {"right_of": "orb"}
        d["entities"][2]["at"] = {"above": "anvil"}
    d, s, _ = load(mutate(cyc))
    assert s is None and any("circular" in x.message for x in errors(d))
    d, s, _ = load(mutate(lambda d: d["entities"][1]["at"].update({"perto": "mage"})))
    assert any(x.accepted and "gap" in x.accepted for x in errors(d))
    d, s, _ = load(mutate(lambda d: d["entities"][1].pop("size")))
    assert any("size" in x.path for x in errors(d))


def test_at_exige_exatamente_um_modo():
    d, _, _ = load(mutate(lambda d: d["entities"][1]["at"].update({"above": "mage"})))
    assert any("exatamente um" in x.message for x in errors(d))


# ---- presets de pose -----------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", PP.names())
def test_preset_cabe_no_perfil_humano(name):
    lim = AN.PROFILES["human_adult"].limits
    for j, axes in PP.resolve({"preset": name})["joints"].items():
        for a, v in axes.items():
            lo, hi = lim[j][a]
            assert lo <= v <= hi, (name, j, a, v)


def test_preset_e_sobrescrito_eixo_a_eixo():
    _, s, data = load(FIX)
    j = data["entities"][0]["pose"]["joints"]
    assert j["neck"]["turn"] == -25 and j["neck"]["flex"] == 15       # turn do autor, flex do preset
    assert "preset" not in data["entities"][0]["pose"]


def test_preset_desconhecido_lista_aceitos():
    d, s, _ = load(mutate(lambda d: d["entities"][0]["pose"].update({"preset": "voar"})))
    assert s is None and any("blacksmith_strike" in (x.accepted or []) for x in errors(d))


# ---- auto_asserts ---------------------------------------------------------------------------------------------
def test_auto_asserts_sintetiza_ordem_sem_duplicar():
    _, _, data = load(mutate(lambda d: d.update({"asserts": ["right_of(serpent, hammer)"]})))
    raws = data["asserts"]
    assert len(raws) == len(set(raws))
    assert not any(r.startswith("left_of(hammer, serpent)") for r in raws)      # já coberto pelo right_of invertido


def test_auto_asserts_nome_desconhecido():
    d, s, _ = load(mutate(lambda d: d.update({"auto_asserts": ["tudo"]})))
    assert any("horizontal_order" in (x.accepted or []) for x in errors(d))


# ---- safe_zones -----------------------------------------------------------------------------------------------
def test_zona_invadida_reprova_e_aparece_no_prompt():
    from scenelang.assertions import evaluate_all

    d, s, _ = load(mutate(lambda d: d["entities"][4].update({"box": [0.05, 0.03, 0.2, 0.2]})))
    res = {r.raw: r for r in evaluate_all(s)}
    assert not res["clear_zone(titulo)"].ok and "serpent" in res["clear_zone(titulo)"].detail
    assert "fica livre" in BACKENDS["prose"](s)


def test_zona_valida_formato():
    d, s, _ = load(mutate(lambda d: d["safe_zones"][0].update({"box": [0.9, 0.9, 0.3, 0.3], "rule": "x"})))
    assert len([x for x in errors(d) if "safe_zones" in x.path]) == 2


def test_zone_quiet_mede_ruido():
    np = pytest.importorskip("numpy")
    from PIL import Image

    from scenelang import verify

    data = mutate(lambda d: d.update({"verify": ["zone_quiet(titulo, 0.05)"]}))
    dg, s, _ = load(data)
    assert not errors(dg)
    flat = Image.new("RGB", (200, 100), (10, 10, 10))
    assert verify.run(s, flat)[0].ok
    noisy = Image.fromarray((np.random.RandomState(0).rand(100, 200, 3) * 255).astype("uint8"))
    assert not verify.run(s, noisy)[0].ok


# ---- interações -----------------------------------------------------------------------------------------------
def test_interacoes_viram_frases_em_todos_os_backends():
    _, s, _ = load(FIX)
    assert "A mão direita da forjadora ergue para golpear o martelo rúnico." in BACKENDS["prose"](s)
    assert "ergue para golpear" in BACKENDS["compact"](s)
    assert "ergue para golpear" in BACKENDS["json"](s)
    assert "ergue para golpear" in BACKENDS["regions"](s)


def test_interacao_ref_invalida_e_orient_contraditoria():
    d, s, _ = load(mutate(lambda d: d["interactions"][0].update({"to": "fantasma"})))
    assert any("não existe" in x.message for x in errors(d))
    d, s, _ = load(mutate(lambda d: d["entities"][0].update({"orient": "left"})))
    assert any(x.level == "warning" and "orient" in x.message for x in d)


# ---- orçamento de tokens --------------------------------------------------------------------------------------
def test_orcamento_poda_em_ordem_e_declara_perdas():
    _, s, _ = load(FIX)
    full = compile_budget(s, "prose", 10_000)
    assert full["dropped"] == [] and full["fits"]
    small = compile_budget(s, "prose", 500)
    assert small["tokens"] < full["tokens"] and small["fits"]
    assert small["dropped"][0] == "detalhe_de_textura" or small["dropped"][0] == "ordem_do_olhar"
    assert "PRIORIDADES" in small["text"] and "CENA" in small["text"]          # o essencial fica
    tiny = compile_budget(s, "compact", 20)
    assert not tiny["fits"]
    from scenelang import loss as LS
    assert any("nem podando" in x.message for x in LS.budget_losses(tiny["dropped"], 20, tiny["fits"]))


def test_orcamento_so_prose_e_compact():
    _, s, _ = load(FIX)
    with pytest.raises(ValueError):
        compile_budget(s, "json", 100)
