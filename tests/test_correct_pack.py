import json

import pytest

pytest.importorskip("PIL")
pytest.importorskip("scipy")
from PIL import Image, ImageDraw

from scenelang import correct as CR
from scenelang import pack as PK
from scenelang.compile import to_prose
from scenelang.validate import load_text

SCENE = """
scene: dois
canvas: {shape: rect, ratio: "4:3"}
grid: {kind: thirds}
style: "pixel art"
intent: {emotion: calma, story: duas peças, focal: a}
entities:
  - id: a
    kind: prop
    label: a bola vermelha
    desc: bola vermelha
    plane: foreground
    box: [0.05, 0.3, 0.2, 0.4]
  - id: b
    kind: prop
    label: a bola azul
    desc: bola azul
    plane: foreground
    box: [0.70, 0.3, 0.2, 0.4]
  - id: c
    kind: character
    label: o boneco
    desc: boneco
    plane: midground
    box: [0.4, 0.3, 0.2, 0.6]
    pose: {body_yaw: 20, joints: {right_elbow: 90}}
asserts:
  - left_of(a, b)
  - visible(a)
verify:
  - max_colors(2)
"""


def load():
    d, scene, _ = load_text(SCENE)
    assert scene is not None, [str(x) for x in d]
    return scene


def img():
    im = Image.new("RGB", (160, 120), "#ffffff")
    d = ImageDraw.Draw(im)
    d.rectangle([112, 36, 144, 84], fill="#d00000")   # "a" à direita: errado
    d.rectangle([8, 36, 40, 84], fill="#0000d0")
    return im


def test_correct_gera_frases_afirmativas_para_cada_falha():
    scene = load()
    boxes = {"a": [0.70, 0.3, 0.2, 0.4], "b": [0.05, 0.3, 0.2, 0.4], "c": [0.4, 0.3, 0.2, 0.6]}
    findings, items = CR.measure(scene, img(), boxes)
    assert any(f.kind == "layout" and not f.ok for f in findings)
    corr = CR.corrections(scene, findings, items)
    assert any("esquerda" in c and "bola azul" in c for c in corr)
    assert any("espelhada" in c for c in corr)
    assert any("no máximo 2 cores" in c for c in corr)


def test_next_scene_valida_e_o_prompt_leva_as_correcoes():
    scene = load()
    boxes = {"a": [0.70, 0.3, 0.2, 0.4], "b": [0.05, 0.3, 0.2, 0.4]}
    findings, items = CR.measure(scene, img(), boxes)
    new, corr = CR.next_scene(scene, findings, items, "x.png")
    import yaml

    d, s2, _ = load_text(yaml.safe_dump(new, allow_unicode=True))
    assert s2 is not None and not [x for x in d if x.level == "error"]
    assert "CORREÇÕES DA VERSÃO ANTERIOR" in to_prose(s2)
    assert new["history"][-1]["rodada"] == 1 and "left_of(a, b)" in new["priority_boost"]


def test_relatorio_e_estruturado():
    scene = load()
    findings, items = CR.measure(scene, img(), {"a": [0.7, 0.3, 0.2, 0.4], "b": [0.05, 0.3, 0.2, 0.4]})
    rep = CR.report(scene, findings, items, "x.png")
    json.dumps(rep)
    assert rep["ok"] is False and rep["medicoes"] and rep["entidades"][0]["fonte"] == "informada"


def test_correcoes_invalidas_sao_erro():
    d, _, _ = load_text(SCENE + "\ncorrections: 5\n")
    assert any(x.level == "error" and "corrections" in x.path for x in d)


def test_pack_unico_leva_prompt_e_cena_nos_metadados(tmp_path):
    scene = load()
    made = PK.pack(scene, SCENE, tmp_path, "single")
    assert [p.name for p in made] == ["cena_unica.png"] and not (tmp_path / "guia.png").exists()
    meta = PK.unpack(tmp_path / "cena_unica.png")
    assert "guia de composição" in meta["scenelang-prompt"] and "left_of(a, b)" in meta["scenelang-yaml"]
    assert Image.open(tmp_path / "cena_unica.png").height > 768


def test_pack_completo_gera_texto_guia_e_prompt_com_guia(tmp_path):
    made = {p.name for p in PK.pack(load(), SCENE, tmp_path)}
    assert {"prompt.txt", "guia.png", "prompt_com_guia.txt", "cena_unica.png"} <= made
    assert (tmp_path / "prompt_com_guia.txt").read_text(encoding="utf-8").startswith("A imagem anexa")
    assert not (tmp_path / "prompt.txt").read_text(encoding="utf-8").startswith("A imagem anexa")


def test_guia_nao_tem_rotulos_por_padrao_e_so_desenha_figura_com_pose():
    svg, _, _ = PK.guide_svg(load())
    assert "<text" not in svg and svg.count('class="pose mannequin"') == 1
    assert "a bola vermelha" in PK.guide_svg(load(), labels=True)[0]
