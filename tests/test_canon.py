import pytest
import yaml

from scenelang import canon

A = """
scene: x
canvas: {ratio: "16:9", pixel_grid: 64}
entities:
  - {id: a, kind: prop, box: [0.1, 0.2, 0.3, 0.4], desc: "ação"}
  - {id: b, kind: prop, box: [0.5, 0.5, 0.2, 0.2], desc: "b"}
"""
B = """
entities:
  - {desc: "ação", box: [0.1, 0.2, 0.3, 0.4], kind: prop, id: a}
  - {desc: "b", box: [0.5, 0.5, 0.2, 0.2], id: b, kind: prop}
canvas: {pixel_grid: 64, ratio: "16:9"}
scene: x
"""


def h(t, **kw):
    return canon.scene_hash(yaml.safe_load(t), **kw)


def test_ordem_das_chaves_em_qualquer_nivel_nao_muda_o_hash():
    assert h(A) == h(B)
    assert len(h(A)) == 64


def test_diferencas_semanticas_mudam_o_hash():
    assert h(A) != h(A.replace("0.3, 0.4", "0.3, 0.41"))
    assert h(A) != h(A.replace('desc: "b"', 'desc: "c"'))


def test_ordem_das_listas_e_significativa():
    d = yaml.safe_load(A)
    e = yaml.safe_load(A)
    e["entities"].reverse()
    assert canon.scene_hash(d) != canon.scene_hash(e)


def test_inteiro_e_float_equivalentes_valem_o_mesmo():
    assert canon.scene_hash({"a": 1}) == canon.scene_hash({"a": 1.0})
    assert canon.scene_hash({"a": True}) != canon.scene_hash({"a": 1})
    assert canon.scene_hash({"a": None}) != canon.scene_hash({"a": 0})


def test_historico_e_correcoes_ficam_fora_do_hash_semantico():
    d = yaml.safe_load(A)
    base = canon.scene_hash(d)
    d["history"] = [{"rodada": 1}]
    d["corrections"] = ["x"]
    assert canon.scene_hash(d) == base
    assert canon.scene_hash(d, include_transient=True) != base


def test_estruturas_aninhadas_e_unicode():
    a = {"x": {"b": [{"z": 1, "y": {"q": 2, "p": 3}}], "a": "ç→日"}}
    b = {"x": {"a": "ç→日", "b": [{"y": {"p": 3, "q": 2}, "z": 1}]}}
    assert canon.scene_hash(a) == canon.scene_hash(b)
    assert "ç→日" in canon.dumps(a)


def test_valores_invalidos_sao_rejeitados_nao_mascarados():
    with pytest.raises(canon.CanonError):
        canon.scene_hash({"a": float("nan")})
    with pytest.raises(canon.CanonError):
        canon.scene_hash({"a": object()})
    with pytest.raises(canon.CanonError):
        canon.scene_hash({1: "a", "1": "b"})


def test_hash_antigo_tinha_o_defeito_que_motivou_o_canonico():
    import hashlib

    def old(d):
        return hashlib.sha256(repr(sorted(d.items(), key=lambda kv: kv[0])).encode("utf-8")).hexdigest()
    assert old(yaml.safe_load(A)) != old(yaml.safe_load(B))   # mesma cena, hash antigo diferente
