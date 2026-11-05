import json

import pytest

from scenelang import loss as LS
from scenelang.compile import to_prose, to_regions
from scenelang.validate import load_text

BASE = """
scene: t
canvas: {shape: rect, ratio: "16:9"}
grid: {kind: golden}
style: "anime"
intent: {emotion: calma, story: uma heroína, focal: hero}
atmosphere: {wind: {direction: right, strength: strong}}
entities:
  - id: hero
    kind: character
    label: a heroína
    desc: heroína de casaco
    plane: foreground
    box: [0.1, 0.2, 0.3, 0.7]
    wind_parts: [hair, coat]
%s
asserts: [visible(hero)]
"""


def load(extra=""):
    return load_text(BASE % extra)


def errs(diags):
    return [d for d in diags if d.level == "error"]


def test_pose_valida_e_vai_para_prosa_e_regioes():
    diags, scene, _ = load("    pose:\n      body_yaw: 90\n      joints: {right_elbow: 90, neck: {turn: 40}}\n      hold: {left_hand: espada}")
    assert not errs(diags)
    assert "cotovelo direito dobrado 90°" in to_prose(scene)
    regs = json.loads(to_regions(scene))["regions"]
    assert "Pose" in regs[0]["prompt"] and "casaco" in regs[0]["prompt"]


@pytest.mark.parametrize("joint,deg", [("right_elbow", 175), ("left_knee", -10), ("neck", 120)])
def test_pose_fora_da_faixa_anatomica_e_erro_com_fix(joint, deg):
    diags, _, _ = load(f"    pose:\n      joints: {{{joint}: {deg}}}")
    e = errs(diags)
    assert len(e) == 1 and e[0].fix and "impossível" in e[0].message


def test_pose_junta_desconhecida_e_eixo_invalido():
    assert errs(load("    pose:\n      joints: {right_elbo: 10}")[0])
    assert errs(load("    pose:\n      joints: {right_elbow: {turn: 10}}")[0])


def test_pose_so_para_personagem():
    diags, _, _ = load_text((BASE % "    pose: {body_yaw: 0}").replace("kind: character", "kind: prop"))
    assert errs(diags)


def test_costas_sem_girar_pescoco_avisa():
    diags, _, _ = load("    pose:\n      body_yaw: 170\n      joints: {neck: {turn: 5}}")
    assert any("rosto" in d.message for d in diags if d.level == "warning")


def test_partes_do_vento_traduzidas():
    _, scene, _ = load()
    assert "o casaco" in to_prose(scene)


def test_loss_parte_sem_traducao_e_estrito():
    diags, scene, _ = load_text((BASE % "").replace("[hair, coat]", "[hair, zzfoo]"))
    items = LS.report(scene, "prose")
    assert any(i.level == "lost" and "zzfoo" in i.message for i in items)
    assert LS.blocking(items)


def test_loss_sem_asserts_bloqueia_e_box_e_aproximado():
    _, scene, _ = load_text((BASE % "").replace("asserts: [visible(hero)]", ""))
    items = LS.report(scene, "prose")
    assert any(i.level == "approx" for i in items)
    assert LS.blocking(items)
    _, ok, _ = load()
    assert not LS.blocking(LS.report(ok, "prose"))


def test_regioes_nao_perdem_intencao_nem_acabamento():
    _, scene, _ = load_text((BASE % "").replace("asserts:", 'finish: "luz volumétrica"\nasserts:'))
    g = json.loads(to_regions(scene))["global_prompt"]
    assert "uma heroína" in g and "luz volumétrica" in g


def test_chave_de_recorte_evita_cor_do_cabelo():
    from scenelang import fx
    from scenelang.palette import reference_colors

    diags, scene, _ = load("    character: {hair: {color: '#00ff00'}}\n")
    assert (0, 255, 0) in reference_colors(scene.data)
    assert fx.pick_key(scene.data) != (0, 255, 0)


def test_palette_match_por_entidade_valida_id():
    from scenelang.verify import parse

    assert parse("palette_match(10, 0.9, hero)").args == [10, 0.9, "hero"]
    d = BASE % ""
    d = d.replace("asserts:", "palette:\n  mode: fixed\n  colors: {a: '#ff0000', b: '#00ff00'}\nverify:\n  - palette_match(10, 0.9, nobody)\nasserts:")
    diags, _, _ = load_text(d)
    assert any("entidade desconhecida" in x.message for x in diags)


@pytest.mark.parametrize("nome,canon", [("Right_Elbow", "right_elbow"), ("right-elbow", "right_elbow"), ("elbow right", "right_elbow"),
                                         ("cotovelo direito", "right_elbow"), ("joelho_esquerdo", "left_knee"), ("pescoço", "neck")])
def test_junta_com_variacao_vira_fix_de_rename(nome, canon):
    from scenelang import api

    text = (BASE % f'    pose: {{joints: {{"{nome}": 40}}}}')
    diags, _, _ = load_text(text)
    e = [d for d in diags if d.level == "error"]
    assert len(e) == 1 and e[0].fix == {"path": e[0].path, "rename": canon}
    assert api.fix(text)["ok"]


def test_giro_do_rosto_e_aviso_de_costas():
    from scenelang.pose import head_yaw

    assert head_yaw({"body_yaw": 150, "joints": {"neck": {"turn": 70}}}) == 80
    assert head_yaw({"body_yaw": 150, "joints": {"neck": {"turn": -70}}}) == -140
    diags, scene, _ = load("    pose:\n      body_yaw: 150\n      joints: {neck: {turn: -70}}")
    assert any("rosto" in d.message for d in diags if d.level == "warning")
    diags, scene, _ = load("    pose:\n      body_yaw: 150\n      joints: {neck: {turn: 70}}")
    assert not any("rosto não aparece" in d.message for d in diags)
    assert "rosto" in to_prose(scene) and "perfil" in to_prose(scene)


def test_fix_guarda_copia_do_original(tmp_path):
    from scenelang.cli import main

    f = tmp_path / "c.yaml"
    f.write_text((BASE % '    pose: {joints: {right_elbow: 175}}'), encoding="utf-8")
    main(["validate", str(f), "--fix"])
    assert (tmp_path / "c.yaml.bak").read_text(encoding="utf-8").count("175") == 1


def test_paleta_desambigua_nomes_repetidos():
    from scenelang import palette

    d = {"palette": {"mode": "fixed", "colors": {"pine": "#1f4d3f", "grass": "#3f7a4e"}}}
    s = palette.sentence(d)
    assert "«pine»" in s and "«grass»" in s
