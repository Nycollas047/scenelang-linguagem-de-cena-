import yaml

from scenelang import loss as LS
from scenelang.validate import ENTITY_KEYS, TOP_KEYS, load_text

BASE = """
scene: x
canvas: {ratio: "4:3", pixel_grid: 64}
grid: golden
style: "pixel art"
intent: {emotion: calma, story: s, focal: a}
palette: {mode: fixed, colors: {a: "#112233", b: "#445566"}}
entities:
  - {id: a, kind: character, desc: "herói", plane: foreground, box: [0.1, 0.1, 0.3, 0.8], signature: ["#112233"],
     pose: {body_yaw: 0, joints: {right_elbow: 90}}}
"""


def sc(text=BASE):
    d, s, _ = load_text(text)
    assert s is not None, [str(x) for x in d]
    return s


def levels(items):
    return {(i.path, i.level) for i in items}


def test_toda_chave_aceita_pelo_validador_tem_destino_declarado():
    missing = [k for k in TOP_KEYS if (LS._ALL, k) not in LS.FATE]
    missing += [f"entities.{k}" for k in ENTITY_KEYS if (LS._ALL, f"entities.{k}") not in LS.FATE and ("prose", f"entities.{k}") not in LS.FATE]
    assert missing == []


def test_chave_sem_destino_e_unsupported_e_bloqueia_o_modo_estrito():
    d = yaml.safe_load(BASE)
    d["campo_novo"] = 1

    class S:
        data = d
    items = LS.report(S(), "prose")
    assert ("$.campo_novo", "unsupported") in levels(items)
    assert LS.fidelity(items) == "sem garantia" and LS.blocking(items)


def test_caixa_e_aproximada_em_prose_e_preservada_em_regions():
    s = sc()
    assert ("$.entities[*].box", "approx") in levels(LS.report(s, "prose"))
    assert ("$.entities[*].box", "preserved") in levels(LS.report(s, "regions"))


def test_pose_palette_grade_dependem_de_intervencao_externa_e_a_fidelidade_nunca_e_completa():
    items = LS.report(sc(), "prose")
    ext = {i.path for i in items if i.level == "external"}
    assert {"$.palette.colors", "$.canvas.pixel_grid", "$.entities[*].pose"} <= ext
    assert LS.fidelity(items) == "parcial"


def test_palette_match_declarado_tira_o_aviso_de_paleta():
    t = BASE + 'verify: ["palette_match(10, 0.8)"]\n'
    assert "$.palette.colors" not in {i.path for i in LS.report(sc(t), "prose") if i.level == "external"}


def test_assinatura_e_historico_sao_meta_nao_perda():
    items = LS.report(sc(BASE + "history: [{rodada: 1}]\n"), "prose")
    lv = {i.path: i.level for i in items}
    assert lv["$.entities[*].signature"] == "meta" and lv["$.history"] == "meta"
    assert not any(i.level in ("lost", "unsupported") for i in items)


def test_fidelidade_completa_so_quando_nada_se_perde_nem_depende_de_fora():
    assert LS.fidelity([LS.Loss("preserved", "$.x", ""), LS.Loss("meta", "$.y", "")]) == "completa"
    for lv in ("approx", "external", "unchecked"):
        assert LS.fidelity([LS.Loss(lv, "$.x", "")]) == "parcial"
    for lv in ("lost", "unsupported"):
        assert LS.fidelity([LS.Loss(lv, "$.x", "")]) == "sem garantia"


def test_summary_conta_por_nivel():
    s = LS.summary(LS.report(sc(), "prose"))
    assert s["preserved"] >= 5 and s["approx"] >= 1 and s["external"] >= 3


def test_nenhum_backend_deixa_chave_conhecida_sem_destino():
    from scenelang.compile import BACKENDS
    s = sc()
    for b in BACKENDS:
        items = LS.report(s, b)
        assert not [i for i in items if i.level == "unsupported"], (b, [str(i) for i in items if i.level == "unsupported"])


def test_compact_declara_o_que_corta():
    t = BASE + "gaze: [a]\nasserts: [\"visible(a)\"]\n"
    lv = {i.path: i.level for i in LS.report(sc(t), "compact")}
    assert lv["$.gaze"] == "lost" and lv["$.asserts"] == "approx"
    assert LS.fidelity(LS.report(sc(t), "compact")) == "sem garantia" and LS.blocking(LS.report(sc(t), "compact"))
    assert {i.path: i.level for i in LS.report(sc(t), "prose")}["$.gaze"] == "preserved"
