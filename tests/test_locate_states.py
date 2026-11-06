import pytest

pytest.importorskip("PIL")
pytest.importorskip("scipy")
from PIL import Image, ImageDraw

from scenelang import locate as LC
from scenelang.validate import load_text

T = """
scene: estados
canvas: {shape: rect, ratio: "4:3"}
grid: {kind: thirds}
style: "pixel art"
intent: {emotion: calma, story: três peças, focal: a}
entities:
  - {id: a, kind: prop, label: a bola vermelha, desc: bola, plane: foreground, box: [0.05, 0.3, 0.2, 0.4], signature: ["#d00000"]}
  - {id: b, kind: prop, label: a bola azul, desc: bola, plane: foreground, box: [0.40, 0.3, 0.2, 0.4], signature: ["#0000d0"]}
  - {id: c, kind: prop, label: a bola verde, desc: bola, plane: foreground, box: [0.75, 0.3, 0.2, 0.4], signature: ["#00a000"]}
  - {id: d, kind: prop, label: a bola cinza, desc: bola, plane: foreground, box: [0.4, 0.05, 0.1, 0.1]}
asserts: ["left_of(a, b)", "left_of(b, c)", "left_of(a, c)"]
"""
W, H = 160, 120


def scene():
    d, s, _ = load_text(T)
    assert s is not None, [str(x) for x in d]
    return s


def canvas():
    im = Image.new("RGB", (W, H), "#ffffff")
    return im, ImageDraw.Draw(im)


def rect(d, box, fill):
    x, y, w, h = box
    d.rectangle([x * W, y * H, (x + w) * W - 1, (y + h) * H - 1], fill=fill)


def by_id(items):
    return {i.id: i for i in items}


def good():
    im, d = canvas()
    rect(d, (0.05, 0.3, 0.2, 0.4), "#d00000")
    rect(d, (0.40, 0.3, 0.2, 0.4), "#0000d0")
    rect(d, (0.75, 0.3, 0.2, 0.4), "#00a000")
    return im


def test_tudo_no_lugar_e_localizada_com_origem_assinatura():
    r = by_id(LC.locate_detailed(scene(), good()))
    assert all(r[k].status == LC.LOCALIZADA and r[k].source == "assinatura" and r[k].confidence >= 0.5 for k in "abc")
    assert LC.mirror_verdict(LC.usable(list(r.values())))[0] == "ok"


def test_entidade_sem_assinatura_nem_caixa_e_evidencia_insuficiente_nunca_ausente():
    d = by_id(LC.locate_detailed(scene(), good()))["d"]
    assert d.status == LC.INSUFICIENTE and d.source == "nenhuma" and d.measured is None


def test_cor_ausente_nao_prova_ausencia():
    im, dr = canvas()
    rect(dr, (0.05, 0.3, 0.2, 0.4), "#d00000")        # b e c não aparecem na cor da assinatura
    r = by_id(LC.locate_detailed(scene(), im))
    assert r["b"].status == LC.INSUFICIENTE and "trocado" in r["b"].reason
    assert r["b"].status != LC.NAO_LOCALIZADA


def test_so_quem_olhou_a_imagem_pode_dizer_que_o_item_nao_aparece():
    r = by_id(LC.locate_detailed(scene(), good(), {"b": None}))
    assert r["b"].status == LC.NAO_LOCALIZADA and r["b"].source == "informada" and r["b"].measured is None


def test_caixa_informada_vale_mais_que_a_cor():
    r = by_id(LC.locate_detailed(scene(), good(), {"a": [0.6, 0.3, 0.2, 0.4]}))
    assert r["a"].source == "informada" and r["a"].measured[0] == 0.6 and r["a"].confidence == 0.9


def test_cor_espalhada_pela_imagem_e_ambigua():
    im, d = canvas()
    for x in (0.0, 0.3, 0.6, 0.85):
        rect(d, (x, 0.05, 0.12, 0.9), "#d00000")         # a mesma cor em quatro faixas: caixa enorme
    r = by_id(LC.locate_detailed(scene(), im))
    assert r["a"].status == LC.AMBIGUA
    assert LC.usable(list(r.values())) == []


def test_dois_blocos_distantes_da_mesma_cor_sao_ambiguos():
    im, d = canvas()
    rect(d, (0.02, 0.3, 0.12, 0.3), "#d00000")
    rect(d, (0.80, 0.3, 0.12, 0.3), "#d00000")
    assert by_id(LC.locate_detailed(scene(), im))["a"].status == LC.AMBIGUA


def test_assinaturas_parecidas_nao_confirmam_nenhuma_das_duas():
    t = T.replace('"#0000d0"', '"#d00010"')
    d, s, _ = load_text(t)
    im, dr = canvas()
    rect(dr, (0.05, 0.3, 0.2, 0.4), "#d00000")
    rect(dr, (0.40, 0.3, 0.2, 0.4), "#d00010")
    r = by_id(LC.locate_detailed(s, im))
    assert r["a"].status in (LC.AMBIGUA, LC.INSUFICIENTE) and r["b"].status in (LC.AMBIGUA, LC.INSUFICIENTE)
    assert not LC.usable([r["a"], r["b"]])


def test_pouco_da_area_achada_e_parcial():
    im, d = canvas()
    rect(d, (0.05, 0.3, 0.08, 0.1), "#d00000")        # ~10% da área declarada
    r = by_id(LC.locate_detailed(scene(), im))
    assert r["a"].status == LC.PARCIAL and "área declarada" in r["a"].reason


def test_item_cortado_pela_borda_e_parcial_quando_o_declarado_estava_dentro():
    r = by_id(LC.locate_detailed(scene(), good(), {"c": [0.9, 0.3, 0.1, 0.4]}))
    assert r["c"].status == LC.PARCIAL and "borda" in r["c"].reason


def test_parcial_e_ambigua_nao_votam_no_espelhamento_nem_nos_asserts():
    items = LC.locate_detailed(scene(), good(), {"a": [0.9, 0.3, 0.1, 0.4]})     # a: cortada na borda direita (declarada à esquerda!)
    assert by_id(items)["a"].status == LC.PARCIAL
    use = LC.usable(items)
    assert {i.id for i in use} == {"b", "c"}
    res, skipped = LC.recheck_asserts(scene(), {i.id: i.measured for i in use})
    assert [r.raw for r in res] == ["left_of(b, c)"] and set(skipped) == {"left_of(a, b)", "left_of(a, c)"}


def test_espelhamento_incerto_diz_quantas_ficaram_de_fora():
    items = LC.locate_detailed(scene(), good(), {"a": None})
    v, detail = LC.mirror_verdict(items)
    assert v == "incerto" and "menos de 3" in detail          # b e c por cor: 2 localizadas, pouco para decidir
    items = LC.locate_detailed(scene(), good(), {"a": None, "b": None})
    v, detail = LC.mirror_verdict(items)
    assert v == "incerto" and "sem medição confiável" in detail


def test_cena_espelhada_e_detectada_com_tres_localizadas():
    im, d = canvas()
    rect(d, (0.75, 0.3, 0.2, 0.4), "#d00000")
    rect(d, (0.40, 0.3, 0.2, 0.4), "#0000d0")
    rect(d, (0.05, 0.3, 0.2, 0.4), "#00a000")
    v, _ = LC.mirror_verdict(LC.usable(LC.locate_detailed(scene(), im)))
    assert v == "espelhada"


def test_origem_desconhecida_e_tratada_como_a_mais_fraca():
    s = scene()
    items = LC.compare(s, {"a": (0.05, 0.3, 0.2, 0.4), "b": (0.4, 0.3, 0.2, 0.4)})
    assert {i.source for i in items} == {"desconhecida"}
    assert LC.mirror_verdict(items)[0] == "incerto"        # com 2 entidades e origem não confirmada, exige 3


def test_statuses_e_sources_sao_do_vocabulario_fechado():
    for i in LC.locate_detailed(scene(), good(), {"d": None}):
        assert i.status in LC.STATUSES and i.source in LC.SOURCES


def test_relatorio_do_correct_lista_estado_e_o_que_nao_foi_medido():
    from scenelang import correct as CR
    m = CR.measure_full(scene(), good(), {"a": None})
    rep = CR.report(scene(), m.findings, m.items, "x.png", None, m.located, m.skipped_asserts)
    st = {e["id"]: e["estado"] for e in rep["entidades"]}
    assert st["a"] == LC.NAO_LOCALIZADA and st["d"] == LC.INSUFICIENTE and len(rep["entidades"]) == 4
    assert rep["nao_medidos"]["asserts"] and any(e["id"] == "a" for e in rep["nao_medidos"]["entidades"])
