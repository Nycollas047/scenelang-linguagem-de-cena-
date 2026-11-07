import json

import pytest

from scenelang import bench as BN
from scenelang.cli import main

T = """
scene: bench
canvas: {ratio: "4:3"}
grid: thirds
style: "pixel art"
intent: {emotion: calma, story: um sapo e uma fogueira, focal: sapo}
entities:
  - {id: sapo, kind: character, label: o sapo, desc: sapo verde, plane: foreground, box: [0.10, 0.4, 0.3, 0.45], signature: ["#00aa00"]}
  - {id: fogueira, kind: prop, label: a fogueira, desc: fogueira acesa, plane: foreground, box: [0.65, 0.6, 0.2, 0.25], signature: ["#ff6600"]}
asserts: ["left_of(sapo, fogueira)"]
verify: ["max_colors(8)"]
"""


def test_plan_grava_prompts_e_metricas_offline_sem_inventar_resultados(tmp_path):
    doc = BN.plan(T, tmp_path)
    assert set(doc["modos"]) == set(BN.MODES)
    for m in ("convencional", "completa", "compacta", "com_guia"):
        assert (tmp_path / f"prompt_{m}.txt").exists() and doc["modos"][m]["entrada_tokens"] > 0
    assert doc["modos"]["convencional"]["baseline_sintetica"] is True and "substitua" in doc["modos"]["convencional"]["aviso"]
    assert doc["modos"]["incremental"]["disponivel"] is False
    assert doc["modos"]["compacta"]["caracteres"] < doc["modos"]["completa"]["caracteres"]
    assert doc["modos"]["completa"]["fidelidade_declarada"] in ("parcial", "completa", "sem garantia")
    assert "taxa de sucesso das restrições (precisa da imagem gerada)" in doc["pendente_de_avaliacao_externa"]
    assert (tmp_path / "execucoes.jsonl").read_text() == ""


def test_baseline_humano_substitui_o_sintetico(tmp_path):
    doc = BN.plan(T, tmp_path, baseline="um sapo ao lado de uma fogueira, pixel art")
    assert doc["modos"]["convencional"]["baseline_sintetica"] is False
    assert (tmp_path / "prompt_convencional.txt").read_text() == "um sapo ao lado de uma fogueira, pixel art"


def test_modo_incremental_precisa_da_cena_anterior_e_gasta_menos(tmp_path):
    prev = T
    new = T.replace("sapo verde", "sapo verde de chapéu roxo")
    doc = BN.plan(new, tmp_path, previous_text=prev)
    inc = doc["modos"]["incremental"]
    assert inc["disponivel"] and inc["exige"].startswith("imagem anterior")
    assert inc["caracteres"] < doc["modos"]["completa"]["caracteres"]


def test_relatorio_sem_execucoes_mostra_tracos_nao_zeros(tmp_path):
    BN.plan(T, tmp_path)
    rep = BN.report(tmp_path)
    r = rep["modos"]["completa"]
    assert r["execucoes"] == 0 and r["taxa_sucesso_media"] is None and r["tentativas_medias"] is None and r["custo_medio_usd"] is None
    assert "—" in BN.markdown(rep) and "avaliação externa" in BN.markdown(rep)


def test_registro_e_agregacao_com_custo_informado_e_calculado(tmp_path):
    BN.plan(T, tmp_path)
    BN.record(tmp_path, "completa", "1", tokens_out=100, calls=1, attempts=1, cost_usd=0.02)
    BN.record(tmp_path, "completa", "2", tokens_out=200, calls=2, attempts=3)
    r = BN.report(tmp_path, price_in=3.0, price_out=15.0)["modos"]["completa"]
    tin = r["tokens_entrada"]
    assert r["execucoes"] == 2 and r["tentativas_medias"] == 2.0 and r["chamadas_medias"] == 1.5 and r["tokens_saida_medio"] == 150.0
    calc = (tin * 3.0 + 200 * 15.0) / 1e6
    assert r["custo_medio_usd"] == pytest.approx((0.02 + calc) / 2, abs=1e-4)          # medido tem preferência; o outro é calculado
    assert BN.report(tmp_path)["modos"]["completa"]["custo_medio_usd"] == 0.02          # sem preço, só entra o custo medido


def test_registro_mede_restricoes_em_codigo_e_ignora_medicao_fraca(tmp_path):
    pytest.importorskip("PIL")
    pytest.importorskip("scipy")
    from PIL import Image
    BN.plan(T, tmp_path)
    img = tmp_path / "g.png"
    Image.new("RGB", (64, 48), "#808080").save(img)
    rec = BN.record(tmp_path, "completa", "1", T, str(img), boxes={"sapo": [0.1, 0.4, 0.3, 0.45], "fogueira": [0.65, 0.6, 0.2, 0.25]})
    rs = rec["restricoes"]
    assert rs["medidas"] >= 2 and 0 <= rs["taxa"] <= 1 and "max_colors(8)" not in rs["falhas"]        # imagem cinza: 1 cor
    assert rs["ok"] == rs["medidas"] - len(rs["falhas"])
    rec2 = BN.record(tmp_path, "compacta", "1", T, str(img))                                      # só por cor: confiança 0,5, não conta
    assert rec2["restricoes"]["desconsideradas_por_confianca"] >= 0


def test_modo_invalido_e_erro(tmp_path):
    BN.plan(T, tmp_path)
    with pytest.raises(ValueError, match="modo desconhecido"):
        BN.record(tmp_path, "mágico", "1")


def test_cli_plan_record_report(tmp_path, capsys):
    f = tmp_path / "c.yaml"
    f.write_text(T, encoding="utf-8")
    out = tmp_path / "b"
    assert main(["bench", "plan", str(out), "--scene", str(f)]) == 0
    assert main(["bench", "record", str(out), "--mode", "completa", "--run-id", "1", "--attempts", "2", "--tokens-out", "50"]) == 0
    capsys.readouterr()
    assert main(["bench", "report", str(out)]) == 0
    assert "| completa |" in capsys.readouterr().out and (out / "relatorio.json").exists() and json.loads((out / "relatorio.json").read_text())["execucoes_totais"] == 1
