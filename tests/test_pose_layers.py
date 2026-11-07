import json
import math

import pytest

from scenelang import anatomy as AN
from scenelang import pose as PO
from scenelang import rig as RG
from scenelang import skeleton as SK
from scenelang.validate import load_text

T = """
scene: p
canvas: {ratio: "3:4"}
grid: thirds
style: "ilustração"
intent: {emotion: calma, story: s, focal: h}
entities:
  - {id: h, kind: character, label: o herói, desc: herói, plane: foreground, box: [0.2, 0.1, 0.5, 0.8], pose: %s}
"""


def run(pose: str):
    d, s, _ = load_text(T % pose)
    return d, s


def msgs(d, level):
    return [x.message for x in d if x.level == level]


def test_perfil_padrao_e_o_de_antes():
    assert PO.JOINTS is AN.PROFILES["human_adult"].limits
    assert AN.get_profile(None).range("right_elbow", "flex") == (0, 150)


def test_stylized_aceita_o_que_human_adult_recusa_sem_mudar_a_pose():
    pose = "{body_yaw: 0, joints: {right_elbow: 170}}"
    assert any("impossível" in m for m in msgs(run(pose)[0], "error"))
    d, s = run("{body_yaw: 0, profile: stylized, joints: {right_elbow: 170}}")
    assert s is not None and not msgs(d, "error")
    assert AN.get_profile("stylized").range("right_elbow", "flex") == (0, 188)      # 150 × 1.25


def test_perfil_desconhecido_e_erro_com_a_lista():
    d, s = run("{profile: alien, joints: {}}")
    e = [x for x in d if x.level == "error"][0]
    assert "perfil" in e.message and "human_adult" in e.accepted


def test_perfil_novo_nao_exige_mexer_no_validador():
    AN.register_profile(AN.AnatomyProfile("rigido", "x", {**AN.HUMAN, "right_elbow": {"flex": (0, 10)}}))
    try:
        d, s = run("{profile: rigido, joints: {right_elbow: 50}}")
        assert any("impossível" in m for m in msgs(d, "error"))
    finally:
        AN.PROFILES.pop("rigido")


def test_dentro_das_faixas_nao_garante_anatomia_heuristicas_avisam():
    d, s = run("{body_yaw: 0, joints: {left_hip: 110, left_knee: 0}}")
    assert s is not None and not msgs(d, "error")                     # numericamente válida
    assert any("quase reta" in m for m in msgs(d, "warning"))         # mas duvidosa
    d, _ = run("{joints: {right_shoulder: {abduct: 150, rotate: 50}}}")
    assert any("ombro trava" in m for m in msgs(d, "warning"))
    d, _ = run("{joints: {left_hip: 110, left_knee: 90}}")
    assert not any("quase reta" in m for m in msgs(d, "warning"))     # com joelho dobrado é plausível


@pytest.mark.parametrize("yaw,axis,sign", [(0, 2, 1), (90, 0, 1), (-90, 0, -1), (180, 2, -1)])
def test_referencial_o_nariz_aponta_para_onde_o_body_yaw_diz(yaw, axis, sign):
    p = SK.points({"body_yaw": yaw, "joints": {}})
    d = [p["nose"][i] - p["head"][i] for i in range(3)]
    assert sign * d[axis] > 0.9 * math.hypot(*d)


def test_direita_do_personagem_fica_na_esquerda_da_imagem_de_frente_e_inverte_de_costas():
    front = SK.points({"body_yaw": 0, "joints": {}})
    back = SK.points({"body_yaw": 180, "joints": {}})
    assert front["right_shoulder"][0] < 0 < front["left_shoulder"][0]
    assert back["right_shoulder"][0] > 0 > back["left_shoulder"][0]


def test_flex_do_cotovelo_leva_o_antebraco_para_a_frente_do_personagem():
    for yaw, axis, sign in ((0, 2, 1), (90, 0, 1), (180, 2, -1)):
        p = SK.points({"body_yaw": yaw, "joints": {"right_shoulder": {"flex": 90}}})
        v = [p["right_elbow"][i] - p["right_shoulder"][i] for i in range(3)]
        assert sign * v[axis] > 0.15                                  # braço levantado para a frente, qualquer que seja o giro


def test_rosto_de_costas_e_avisado_em_qualquer_orientacao():
    for yaw in (150, -150, 180):
        d, _ = run("{body_yaw: %d, joints: {}}" % yaw)
        assert any("rosto fica de costas" in m for m in msgs(d, "warning"))
    d, _ = run("{body_yaw: 150, joints: {neck: {turn: 70}}}")
    assert not any("rosto fica de costas" in m for m in msgs(d, "warning"))


def test_frase_usa_os_limites_do_perfil():
    _, s = run("{profile: stylized, joints: {right_elbow: 170}}")
    assert "170°" in PO.sentence(s, "h")


def test_rig_troca_nomes_e_marca_como_nao_calibrado():
    pose = {"body_yaw": 30, "joints": {"left_elbow": 90, "right_shoulder": {"flex": 45, "abduct": 10}, "neck": {"turn": 20}}}
    u = RG.to_rig(pose, "unity_humanoid")
    assert u["bones"]["LeftLowerArm"] == {"flex": 90} and u["bones"]["RightUpperArm"] == {"flex": 45, "abduct": 10} and u["bones"]["Neck"] == {"turn": 20}
    assert u["calibrated"] is False and any("NÃO calibrados" in w for w in u["warnings"])
    m = RG.to_rig(pose, "mixamo")
    assert "mixamorig:LeftForeArm" in m["bones"] and "mixamorig:RightArm" in m["bones"]
    assert RG.to_rig(pose, "scenelang")["calibrated"] is True
    assert u["root"] == {"body_yaw": 30, "axis": "y"} and u["frame"] == AN.FRAME


def test_calibracao_aplica_sinal_e_deslocamento_e_so_entao_marca_calibrado():
    pose = {"joints": {"left_elbow": 90}}
    cal = {"LeftLowerArm": {"flex": {"axis": "x", "sign": -1, "offset": 5}}}
    r = RG.to_rig(pose, "unity_humanoid", cal)
    assert r["bones"]["LeftLowerArm"] == {"x": -85} and r["calibrated"] is True and not r["warnings"]
    parcial = RG.to_rig({"joints": {"left_elbow": 90, "neck": {"turn": 5}}}, "unity_humanoid", cal)
    assert parcial["calibrated"] is False


def test_rig_desconhecido_e_erro_explicito():
    with pytest.raises(KeyError):
        RG.to_rig({}, "blender")


def test_cli_exporta_pose_em_json(tmp_path, capsys):
    from scenelang.cli import main
    f = tmp_path / "c.yaml"
    f.write_text(T % "{body_yaw: 0, joints: {right_elbow: 90}}", encoding="utf-8")
    assert main(["pose", str(f), "h", "--export", "mixamo"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["bones"]["mixamorig:RightForeArm"] == {"flex": 90} and out["calibrated"] is False
    assert main(["pose", str(f), "h"]) == 2


def _d(pose, a, b):
    p = SK.points(pose)
    return [p[b][i] - p[a][i] for i in range(3)]


@pytest.mark.parametrize("joint,axis,a,b,comp,sign", [
    ("left_shoulder", "flex", "left_shoulder", "left_elbow", 2, 1),     # braço sobe para a frente (+z, personagem de frente)
    ("right_shoulder", "flex", "right_shoulder", "right_elbow", 2, 1),
    ("left_hip", "flex", "left_hip", "left_knee", 2, 1),                # coxa sobe para a frente
    ("right_hip", "flex", "right_hip", "right_knee", 2, 1),
    ("left_knee", "flex", "left_knee", "left_ankle", 2, -1),            # joelho dobra: o pé vai para trás
    ("right_knee", "flex", "right_knee", "right_ankle", 2, -1),
    ("left_elbow", "flex", "left_elbow", "left_wrist", 2, 1),           # cotovelo dobra: o antebraço vai para a frente
    ("left_shoulder", "abduct", "left_shoulder", "left_elbow", 0, 1),   # abduzir afasta do corpo: esquerdo → +x
    ("right_shoulder", "abduct", "right_shoulder", "right_elbow", 0, -1),
    ("left_hip", "abduct", "left_hip", "left_knee", 0, 1),
    ("right_hip", "abduct", "right_hip", "right_knee", 0, -1),
])
def test_regressao_sinais_de_flexao_e_abducao_nao_cruzam_nem_invertem(joint, axis, a, b, comp, sign):
    v = _d({"body_yaw": 0, "joints": {joint: {axis: 60}}}, a, b)
    assert sign * v[comp] > 0.05, (joint, axis, v)


def test_regressao_inclinacao_do_pescoco_e_da_coluna_vao_para_a_direita_do_personagem():
    assert _d({"joints": {"neck": {"tilt": 30}}}, "neck", "head")[0] < -0.02       # direita do personagem = -x
    assert _d({"joints": {"spine": {"side": 30}}}, "hip", "neck")[0] < -0.05
    assert _d({"joints": {"neck": {"tilt": -30}}}, "neck", "head")[0] > 0.02


def test_regressao_torcao_para_a_direita_leva_o_ombro_esquerdo_a_frente():
    p = SK.points({"joints": {"spine": {"twist": 40}}})
    assert p["left_shoulder"][2] > 0.05 > -0.05 > p["right_shoulder"][2]


def test_perna_dobrada_de_lado_aponta_para_frente_em_perfil():
    # personagem de perfil olhando para a direita da imagem (+x): coxa à frente = +x
    v = _d({"body_yaw": 90, "joints": {"right_hip": {"flex": 80}}}, "right_hip", "right_knee")
    assert v[0] > 0.1
