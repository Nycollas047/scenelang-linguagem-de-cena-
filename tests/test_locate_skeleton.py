
import pytest

pytest.importorskip("PIL")
pytest.importorskip("scipy")
from PIL import Image, ImageDraw

from scenelang import locate as LC
from scenelang import skeleton
from scenelang.render import render_svg
from scenelang.validate import load_text

SCENE = """
scene: dois
canvas: {shape: rect, ratio: "16:9"}
grid: {kind: thirds}
style: "anime"
intent: {emotion: calma, story: duas peças, focal: a}
entities:
  - id: a
    kind: prop
    label: a bola vermelha
    desc: bola vermelha
    plane: foreground
    box: [0.05, 0.3, 0.2, 0.4]
    signature: ["#d00000"]
  - id: b
    kind: prop
    label: a bola azul
    desc: bola azul
    plane: foreground
    box: [0.70, 0.3, 0.2, 0.4]
    signature: ["#0000d0"]
asserts:
  - left_of(a, b)
"""


def make(a_x, b_x):
    im = Image.new("RGB", (320, 180), "#f0f0f0")
    d = ImageDraw.Draw(im)
    d.rectangle([a_x * 320, 54, (a_x + 0.2) * 320, 126], fill="#d00000")
    d.rectangle([b_x * 320, 54, (b_x + 0.2) * 320, 126], fill="#0000d0")
    return im


def run(im):
    _, scene, _ = load_text(SCENE)
    found = LC.locate_by_signature(scene, im)
    items = LC.compare(scene, found, {k: "assinatura" for k in found})
    return scene, found, items


def test_locate_ok_e_asserts_passam():
    scene, found, items = run(make(0.05, 0.70))
    assert abs(found["a"][0] - 0.05) < 0.02
    assert LC.mirror_verdict(items)[0] == "ok"
    res, _ = LC.recheck_asserts(scene, found)
    assert all(r.ok for r in res)


def test_locate_detecta_espelhamento_e_assert_falha():
    scene, found, items = run(make(0.70, 0.05))
    assert LC.mirror_verdict(items)[0] == "espelhada"
    res, _ = LC.recheck_asserts(scene, found)
    assert any(not r.ok for r in res)


def test_locate_boxes_informadas_e_assert_pulado():
    scene, _, _ = run(make(0.05, 0.70))
    res, skipped = LC.recheck_asserts(scene, {"a": (0.1, 0.3, 0.2, 0.4)})
    assert skipped and not res


def test_signature_invalida_e_erro():
    diags, _, _ = load_text(SCENE.replace('["#d00000"]', '["notacolor"]', 1))
    assert any(d.level == "error" and "signature" in d.path for d in diags)


def test_form_lista_entidades():
    _, scene, _ = load_text(SCENE)
    assert "`a`" in LC.form(scene) and "`b`" in LC.form(scene)


def test_skeleton_cotovelo_dobrado_aproxima_punho_do_ombro():
    reto = skeleton.points({"joints": {}})
    dobrado = skeleton.points({"joints": {"right_shoulder": {"flex": 90}, "right_elbow": 120}})

    def d(P):
        a, b = P["right_shoulder"], P["right_wrist"]
        return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5

    assert d(dobrado) < d(reto)


def test_render_desenha_esqueleto():
    d, scene, _ = load_text(SCENE.replace("kind: prop\n    label: a bola vermelha", "kind: character\n    label: a bola vermelha")
                            .replace("    signature: [\"#d00000\"]", "    pose: {joints: {right_elbow: 90}}"))
    assert 'class="pose solids"' in render_svg(scene)


def test_solidos_tem_caixas_cilindros_e_legenda():
    pose = {"body_yaw": 30, "joints": {"right_elbow": 90, "left_knee": 40}}
    svg = skeleton.solids_svg(pose, (0, 0, 300, 400))
    assert "<ellipse" in svg and "<polygon" in svg and "stroke-dasharray" in svg
    sheet = skeleton.sheet_svg(pose, "x")
    assert "caixa alta e fina" in sheet and sheet.count('class="pose solids"') == 3


def test_cilindro_apontando_para_camera_fica_mais_aberto():
    # braço para a frente (flex 90): a elipse da ponta tem mais abertura que o braço caído
    caido = skeleton.solids_svg({"joints": {}}, (0, 0, 300, 400))
    frente = skeleton.solids_svg({"joints": {"right_shoulder": {"flex": 90}}}, (0, 0, 300, 400))
    assert caido != frente
