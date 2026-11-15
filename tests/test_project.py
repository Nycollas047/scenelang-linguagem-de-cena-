"""Espaço de trabalho do projeto: init, camadas, telas, status derivado e rodadas."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from PIL import Image

from scenelang import project as PJ

ROOT = Path(__file__).resolve().parent.parent


def _novo(tmp_path):
    d = tmp_path / "p"
    PJ.init(d, "demo", "objetivo de teste")
    return d


def test_init_cria_estrutura_e_nao_sobrescreve(tmp_path):
    d = _novo(tmp_path)
    for n in ("projeto.yaml", "LEIA-ME-LLM.md", "telas", "refs", "relatorios"):
        assert (d / n).exists()
    with pytest.raises(PJ.ProjectError, match="já existe"):
        PJ.init(d)


def test_add_tela_registra_e_valida_a_cena_inicial(tmp_path):
    d = _novo(tmp_path)
    PJ.add_layer(d, "shell", "barra superior")
    p = PJ.add_screen(d, "visao_geral", "shell")
    assert p.is_file()
    idx = yaml.safe_load((d / "projeto.yaml").read_text(encoding="utf-8"))
    assert idx["telas"][0] == {"id": "visao_geral", "arquivo": "telas/visao_geral.yaml", "camada": "shell"}
    st = PJ.status(d)
    assert st["telas"][0]["valida"] is True and "gerar a imagem" in st["telas"][0]["proximo"]


@pytest.mark.parametrize("sid", ["Tela", "1tela", "com espaço", "a-b", ""])
def test_id_invalido_e_recusado(tmp_path, sid):
    with pytest.raises(PJ.ProjectError, match="inválido"):
        PJ.add_screen(_novo(tmp_path), sid)


def test_tela_repetida_e_camada_desconhecida(tmp_path):
    d = _novo(tmp_path)
    PJ.add_screen(d, "a")
    with pytest.raises(PJ.ProjectError, match="já está no índice"):
        PJ.add_screen(d, "a")
    with pytest.raises(PJ.ProjectError, match="camada desconhecida"):
        PJ.add_screen(d, "b", "nao_existe")


def test_status_acusa_arquivo_solto_ausente_e_invalido(tmp_path):
    d = _novo(tmp_path)
    PJ.add_screen(d, "boa")
    (d / "telas" / "solta.yaml").write_text("scene: x\n", encoding="utf-8")
    idx = yaml.safe_load((d / "projeto.yaml").read_text(encoding="utf-8"))
    idx["telas"].append({"id": "sumida", "arquivo": "telas/sumida.yaml"})
    (d / "projeto.yaml").write_text(yaml.safe_dump(idx), encoding="utf-8")
    (d / "telas" / "boa.yaml").write_text("scene: x\n", encoding="utf-8")        # inválida de propósito
    st = PJ.status(d)
    assert any("solta.yaml" in p and "não está no índice" in p for p in st["problemas"])
    por_id = {s["id"]: s for s in st["telas"]}
    assert por_id["sumida"]["existe"] is False and "criar" in por_id["sumida"]["proximo"]
    assert por_id["boa"]["valida"] is False and "corrigir a validação" in por_id["boa"]["proximo"]
    assert st["em_dia"] is False


def test_indice_malformado_vira_problema_nao_traceback(tmp_path):
    d = _novo(tmp_path)
    (d / "projeto.yaml").write_text("projeto: x\ntelas: 3\ncamadas: [1]\nextra: 1\n", encoding="utf-8")
    st = PJ.status(d)
    assert st["problemas"] and st["telas"] == []


def test_sem_indice_da_erro_claro(tmp_path):
    with pytest.raises(PJ.ProjectError, match="project init"):
        PJ.status(tmp_path)


def _cena_dois_blocos(d: Path):
    (d / "telas" / "t.yaml").write_text(
        'scene: t\ncanvas: {ratio: "1:1"}\nstyle: x\nintent: {emotion: e, story: s, focal: a}\n'
        "asserts:\n  - left_of(a, b)\nentities:\n"
        "  - {id: a, kind: prop, label: o a, desc: a, plane: midground, box: [0.1, 0.4, 0.2, 0.2], brightness: max}\n"
        "  - {id: b, kind: prop, label: o b, desc: b, plane: midground, box: [0.6, 0.4, 0.2, 0.2]}\n", encoding="utf-8")


def test_round_guarda_imagem_relatorio_e_detecta_cena_desatualizada(tmp_path):
    d = _novo(tmp_path)
    PJ.add_screen(d, "t")
    _cena_dois_blocos(d)
    img = tmp_path / "x.png"
    Image.new("RGB", (200, 200), "gray").save(img)
    res = PJ.record_round(d, "t", img, {"a": [0.1, 0.4, 0.2, 0.2], "b": [0.6, 0.4, 0.2, 0.2]}, label="Braço A")
    assert res["rodada"] == 1
    assert (d / "relatorios" / "t" / "rodada-01" / "relatorio.json").is_file()
    assert (d / "refs" / "t" / "rodada-01-bra_o_a.png").is_file()
    st = PJ.status(d)["telas"][0]
    assert st["rodadas"] == 1 and st["desatualizada"] is False
    # só formatação/data não desatualiza; mudar a cena desatualiza
    (d / "telas" / "t.yaml").write_text((d / "telas" / "t.yaml").read_text(encoding="utf-8").replace("desc: a,", "desc: um a diferente,"), encoding="utf-8")
    st = PJ.status(d)["telas"][0]
    assert st["desatualizada"] is True and "a cena mudou" in st["proximo"]
    res2 = PJ.record_round(d, "t", img, {"a": [0.1, 0.4, 0.2, 0.2], "b": [0.6, 0.4, 0.2, 0.2]})
    assert res2["rodada"] == 2


def test_round_erros_nao_deixam_lixo(tmp_path):
    d = _novo(tmp_path)
    PJ.add_screen(d, "t")
    with pytest.raises(PJ.ProjectError, match="imagem"):
        PJ.record_round(d, "t", tmp_path / "nao_existe.png")
    with pytest.raises(PJ.ProjectError, match="tela desconhecida"):
        PJ.record_round(d, "x", tmp_path / "nao_existe.png")
    assert not list((d / "relatorios").glob("*/rodada-*"))


def test_cli_ciclo_basico(tmp_path):
    def run(*a):
        return subprocess.run([sys.executable, "-m", "scenelang", "project", *a], capture_output=True, text=True, cwd=ROOT)
    d = str(tmp_path / "c")
    assert run("init", d, "--name", "c").returncode == 0
    assert run("add", d, "tela_um").returncode == 0
    r = run("add", d)                                   # falta o id
    assert r.returncode == 2 and "precisa de id" in r.stderr
    r = run("status", d, "--json")
    assert r.returncode == 0 and json.loads(r.stdout)["telas"][0]["id"] == "tela_um"
    assert run("status", str(tmp_path / "nada")).returncode == 2


def test_export_dataset_registro_autocontido(tmp_path):
    d = _novo(tmp_path)
    PJ.add_screen(d, "t")
    _cena_dois_blocos(d)
    img = tmp_path / "x.png"
    Image.new("RGB", (200, 100), "gray").save(img)
    boxes = {"a": [0.1, 0.4, 0.2, 0.2], "b": [0.6, 0.4, 0.2, 0.2]}
    PJ.record_round(d, "t", img, boxes, label="A")
    PJ.record_round(d, "t", img, boxes, label="B")
    recs, warns = PJ.export_dataset(d)
    assert not warns and [r["rodada"] for r in recs] == [1, 2]
    r = recs[0]
    assert r["formato"] == "scenelang.dataset/1" and r["tela"] == "t"
    assert "left_of(a, b)" in r["cena_yaml"] and r["prompt"].strip()
    assert r["imagem"]["tamanho"] == [200, 100] and len(r["imagem"]["sha256"]) == 64
    assert r["anotacao"]["caixas"] == "informadas"
    assert any(m["check"].startswith("left_of") and m["ok"] and m["source"] == "informada" for m in r["medicoes"])
    json.dumps(r)                                        # serializável


def test_export_pula_rodada_antiga_e_avisa(tmp_path):
    d = _novo(tmp_path)
    PJ.add_screen(d, "t")
    (d / "relatorios" / "t" / "rodada-01").mkdir(parents=True)
    recs, warns = PJ.export_dataset(d)
    assert recs == [] and warns and "rodada-01" in warns[0]


def test_cli_export(tmp_path):
    d = tmp_path / "e"
    PJ.init(d)
    PJ.add_screen(d, "t")
    r = subprocess.run([sys.executable, "-m", "scenelang", "project", "export", str(d)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 2 and "--out" in r.stderr
    out = tmp_path / "d.jsonl"
    r = subprocess.run([sys.executable, "-m", "scenelang", "project", "export", str(d), "--out", str(out)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0 and out.read_text() == ""


def test_prompt_real_e_origem_ficam_registrados(tmp_path):
    d = _novo(tmp_path)
    PJ.add_screen(d, "t")
    _cena_dois_blocos(d)
    img = tmp_path / "x.png"
    Image.new("RGB", (100, 100), "gray").save(img)
    box = {"a": [0.1, 0.4, 0.2, 0.2], "b": [0.6, 0.4, 0.2, 0.2]}
    pf = tmp_path / "meu.txt"
    pf.write_text("prompt escrito à mão", encoding="utf-8")
    PJ.record_round(d, "t", img, box, "A", pf, "gerador-x 2026-11")
    PJ.record_round(d, "t", img, box, "B")
    a, b = PJ.export_dataset(d)[0]
    assert a["prompt"] == "prompt escrito à mão" and a["prompt_origem"] == "informado"
    assert a["gerador"] == "gerador-x 2026-11" and b["gerador"] is None
    assert b["prompt_origem"] == "compilado_da_cena_assumido" and b["prompt"] != a["prompt"]
    with pytest.raises(PJ.ProjectError, match="arquivo de prompt"):
        PJ.record_round(d, "t", img, box, "C", tmp_path / "nao.txt")
    assert len(PJ.export_dataset(d)[0]) == 2 and len(list((d / "relatorios" / "t").glob("rodada-*"))) == 2   # nada pela metade
