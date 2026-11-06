import json

import pytest

pytest.importorskip("PIL")
pytest.importorskip("scipy")
from PIL import Image

from scenelang import canon
from scenelang import correct as CR
from scenelang.correction import MAX_ATTEMPTS, RULES, CorrectionHistory, Finding, Rule, plan, register, rule_for
from scenelang.validate import load_text

SCENE = """
scene: motor
canvas: {shape: rect, ratio: "4:3", pixel_grid: 64}
grid: {kind: thirds}
style: "pixel art"
intent: {emotion: calma, story: duas peças, focal: a}
palette: {mode: fixed, colors: {a: "#d00000", b: "#0000d0"}}
entities:
  - {id: a, kind: prop, label: a bola vermelha, desc: bola, plane: foreground, box: [0.05, 0.3, 0.2, 0.4], signature: ["#d00000"]}
  - {id: b, kind: prop, label: a bola azul, desc: bola, plane: foreground, box: [0.70, 0.3, 0.2, 0.4], signature: ["#0000d0"]}
asserts: ["left_of(a, b)", "visible(a)"]
verify: ["max_colors(2)", "grid_aligned(32)"]
"""


def load(text=SCENE):
    d, s, _ = load_text(text)
    assert s is not None, [str(x) for x in d]
    return s


def F(check, kind="verify", source="imagem", ok=False, detail="x"):
    return Finding(kind, check, ok, detail, source)


def test_todo_verificador_da_linguagem_tem_regra():
    from scenelang.verify import NAMES
    for n in NAMES:
        assert rule_for(F(f"{n}(1)")) is not None, f"verificador {n} sem regra de correção"


def test_falha_sem_regra_fica_nao_resolvida_e_nao_vira_instrucao():
    p = plan(load(), [F("inventado(3)")], [])
    assert not p.applied and p.unresolved[0].failure == "inventado(3)"
    assert "sem regra" in p.unresolved[0].reason


def test_evidencia_fraca_por_cor_nao_altera_o_prompt():
    f = Finding("layout", "left_of(a, b)", False, "x 0.9 > 0.1", "assinatura")
    p = plan(load(), [f], [])
    assert not p.applied and p.deferred and "evidência insuficiente" in p.deferred[0].reason
    f2 = Finding("layout", "left_of(a, b)", False, "x", "informada")
    assert plan(load(), [f2], []).applied


def test_instrucao_repetida_escala_e_depois_declara_nao_resolvida():
    s = load()
    f = F("max_colors(2)")
    texts, hist = [], CorrectionHistory()
    for _ in range(MAX_ATTEMPTS + 1):
        p = plan(s, [f], [], hist)
        if not p.applied:
            break
        texts.append(p.applied[0].text)
        hist.add(None, "i.png", "h", p, ["max_colors(2)"])
    assert len(texts) == 2 and texts[0] != texts[1]          # a regra tem duas versões; a segunda é mais explícita
    assert p.unresolved and "mesma instrução" in p.unresolved[0].reason and "snap" in p.unresolved[0].suggestion


def test_limite_de_tentativas_declara_nao_resolvida_mesmo_com_versoes_sobrando():
    h = CorrectionHistory([{"rodada": i, "reprovados": ["max_colors(2)"]} for i in range(1, MAX_ATTEMPTS + 1)])
    p = plan(load(), [F("max_colors(2)")], [], h)
    assert not p.applied and "persiste" in p.unresolved[0].reason and p.unresolved[0].attempts == MAX_ATTEMPTS


def test_falha_resolvida_zera_as_tentativas():
    h = CorrectionHistory([{"rodada": 1, "reprovados": ["max_colors(2)"]}, {"rodada": 2, "reprovados": []}])
    assert h.attempts("max_colors(2)") == 0


def test_regra_nova_nao_exige_mudar_o_motor():
    @register
    class Dummy(Rule):
        name, kind, checks = "dummy", "verify", ("dummy_check",)

        def build(self, ctx, f, attempt):
            return "faça o dummy" if attempt == 0 else "faça o dummy com mais clareza"
    try:
        p = plan(load(), [F("dummy_check(1)")], [])
        assert p.applied[0].rule == "dummy" and p.applied[0].auto_scene
    finally:
        RULES.pop()


def test_limite_por_rodada_adia_o_excedente_por_prioridade():
    s = load()
    fs = [F("max_colors(2)"), F("grid_aligned(32)"), F("palette_match(10, 0.9)")]
    p = plan(s, fs, [], max_corrections=2)
    assert len(p.applied) == 2 and len(p.deferred) == 1 and "limite" in p.deferred[0].reason


def test_correcoes_trazem_evidencia_confianca_prioridade_e_efeitos():
    c = plan(load(), [F("palette_match(10, 0.9)", detail="27% dentro")], []).applied[0]
    assert c.evidence == "27% dentro" and c.confidence >= 0.9 and c.priority and c.post_fix and c.side_effects


def test_historico_compacta_sem_perder_contagens():
    h = CorrectionHistory([{"rodada": i, "imagem": f"{i}.png", "reprovados": ["max_colors(2)"] + (["grid_aligned(32)"] if i % 2 else []),
                            "tags": ["estilo"] if i == 2 else []} for i in range(1, 21)])
    before = h.failed_count("max_colors(2)")
    h.compact(keep_last=5)
    assert len(h.entries) == 6 and h.entries[0]["resumo"] and h.entries[0]["rodadas"] == [1, 15]
    assert h.failed_count("max_colors(2)") == before == 20
    assert h.failed_count("grid_aligned(32)") == 10
    assert h.entries[0]["tags"] == ["estilo"] and len(h.entries[0]["imagens"]) == 15
    again = [dict(e) for e in h.entries]
    assert CorrectionHistory(again).compact(keep_last=5).to_list() == h.to_list()   # idempotente
    assert h.next_round == 21 and h.attempts("max_colors(2)") == 20


def test_historico_da_v05_continua_valido():
    h = CorrectionHistory([{"rodada": 1, "imagem": "a.png", "reprovados": ["max_colors(2)"], "tags": []}])
    assert h.attempts("max_colors(2)") == 1 and h.next_round == 2


def test_rodadas_seguidas_nao_crescem_alem_do_limite_e_corrigem_com_escalada(tmp_path):
    s = load()
    img = Image.new("RGB", (64, 48), "#808080")
    scene = s
    for _ in range(10):
        findings, items = CR.measure(scene, img, {"a": [0.7, 0.3, 0.2, 0.4], "b": [0.05, 0.3, 0.2, 0.4]})
        new, pl = CR.next_scene_plan(scene, findings, items, "x.png", keep_rounds=3)
        import yaml
        d, scene, _ = load_text(yaml.safe_dump(new, allow_unicode=True))
        assert scene is not None
    assert len(scene.data["history"]) <= 4
    rep = CR.report(scene, findings, items, "x.png")
    json.dumps(rep)
    assert rep["nao_resolvidas"] or rep["correcoes"]
    assert rep["hash_algoritmo"] == canon.ALGORITHM and len(rep["hash_cena_completo"]) == 64


def test_hash_do_relatorio_ignora_historico_e_ordem_de_chaves():
    s = load()
    f, i = CR.measure(s, Image.new("RGB", (64, 48), "white"), None)
    first = CR.report(s, f, i)["hash_cena"]
    new, _ = CR.next_scene(s, f, i, "x.png")          # adiciona history e corrections
    import yaml
    _, s2, _ = load_text(yaml.safe_dump({k: new[k] for k in reversed(list(new))}, allow_unicode=True, sort_keys=False))
    assert CR.report(s2, f, i)["hash_cena"] == first   # mesma cena semântica: o histórico e a ordem das chaves não contam
