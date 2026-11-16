"""Rodadas com anotação independente, braços/seeds e relatório de variação."""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from scenelang import project as PJ
from scenelang import reconcile as RC

from test_project import _cena_dois_blocos, _novo

ROOT = Path(__file__).resolve().parent.parent


def _setup(tmp_path):
    d = _novo(tmp_path)
    PJ.add_screen(d, "t")
    _cena_dois_blocos(d)
    t = d / "telas" / "t.yaml"
    s = t.read_text(encoding="utf-8").replace("asserts:\n", "asserts:\n  - count(prop) == 2\n")
    t.write_text(s.replace("label: o a,", "label: a caixa azul,").replace("label: o b,", "label: a caixa vermelha,"), encoding="utf-8")
    img = tmp_path / "x.png"
    Image.new("RGB", (200, 200), "gray").save(img)
    return d, img


def _ann(tmp_path, objs, name="a.json", cego=True):
    p = tmp_path / name
    p.write_text(json.dumps({"formato": RC.FORMAT, "anotador": "t", "cego": cego,
                             "objetos": [{"nome": n, "caixa": b} for n, b in objs]}), encoding="utf-8")
    return p


def test_round_with_annotation_measures_and_flags_extras(tmp_path):
    d, img = _setup(tmp_path)
    ann = _ann(tmp_path, [("caixa azul", [0.1, 0.4, 0.2, 0.2]), ("caixa vermelha", [0.6, 0.4, 0.2, 0.2]), ("caixa azul", [0.4, 0.1, 0.1, 0.1])])
    res = PJ.record_round(d, "t", img, annotation=ann, arm="A", seed=7)
    out = d / "relatorios" / "t" / "rodada-01"
    rec = json.loads((out / "reconciliacao.json").read_text(encoding="utf-8"))
    assert [a["ok"] for a in rec["asserts"] if "count" in a["raw"]] == [False]
    assert len(rec["extras"]) == 1 and res["reconciliacao"]["cego"] is True
    meta = json.loads((out / "rodada.json").read_text(encoding="utf-8"))
    assert meta["caixas"] == "anotacao_independente" and meta["braco"] == "A" and meta["seed"] == 7 and meta["anotacao_cega"] is True
    recs, _ = PJ.export_dataset(d)
    assert recs[0]["braco"] == "A" and recs[0]["seed"] == 7 and recs[0]["reconciliacao"]["extras"] and recs[0]["anotacao"]["cego"] is True


def test_explicit_boxes_win_over_annotation_boxes_but_label_stays_honest(tmp_path):
    d, img = _setup(tmp_path)
    ann = _ann(tmp_path, [("caixa azul", [0.1, 0.4, 0.2, 0.2]), ("caixa vermelha", [0.6, 0.4, 0.2, 0.2])])
    PJ.record_round(d, "t", img, {"a": [0.1, 0.4, 0.2, 0.2], "b": [0.6, 0.4, 0.2, 0.2]}, annotation=ann)
    meta = json.loads((d / "relatorios" / "t" / "rodada-01" / "rodada.json").read_text(encoding="utf-8"))
    assert meta["caixas"] == "informadas"


def test_annotation_with_no_match_is_a_clear_error(tmp_path):
    d, img = _setup(tmp_path)
    with pytest.raises(PJ.ProjectError, match="nenhum objeto anotado casou"):
        PJ.record_round(d, "t", img, annotation=_ann(tmp_path, [("elefante", [0.1, 0.1, 0.2, 0.2])]))
    assert not list((d / "relatorios").glob("*/rodada-*"))


def test_bad_annotation_leaves_no_round(tmp_path):
    d, img = _setup(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text("{nope", encoding="utf-8")
    for p in (bad, tmp_path / "ausente.json", _ann(tmp_path, [("x", [0, 0, 5, 5])], "fora.json")):
        with pytest.raises(PJ.ProjectError, match="anotação inválida"):
            PJ.record_round(d, "t", img, annotation=p)
    assert not list((d / "relatorios").glob("*/rodada-*")) and not list((d / "refs").glob("*/*"))


def test_wilson_basics():
    assert PJ.wilson(0, 0) == (0.0, 1.0)
    lo, hi = PJ.wilson(3, 3)
    assert hi == 1.0 and 0.4 < lo < 0.5          # 3/3 NÃO é "100% garantido"
    lo, hi = PJ.wilson(50, 100)
    assert 0.39 < lo < 0.41 and 0.59 < hi < 0.61


def test_report_groups_by_arm_and_warns_on_small_n(tmp_path):
    d, img = _setup(tmp_path)
    good = _ann(tmp_path, [("caixa azul", [0.1, 0.4, 0.2, 0.2]), ("caixa vermelha", [0.6, 0.4, 0.2, 0.2])], "g.json")
    extra = _ann(tmp_path, [("caixa azul", [0.1, 0.4, 0.2, 0.2]), ("caixa vermelha", [0.6, 0.4, 0.2, 0.2]), ("caixa azul", [0.4, 0.1, 0.1, 0.1])], "e.json")
    PJ.record_round(d, "t", img, annotation=good, arm="A", seed=1)
    PJ.record_round(d, "t", img, annotation=extra, arm="A", seed=2)
    PJ.record_round(d, "t", img, annotation=good, arm="B", seed=1)
    rep = PJ.report(d, "t")
    a, b = rep["bracos"]["A"], rep["bracos"]["B"]
    cnt = "[anotação] count(prop) == 2"
    assert (a["restricoes"][cnt]["k"], a["restricoes"][cnt]["n"]) == (1, 2) and a["repetido"] and a["seeds"] == [1, 2]
    assert (b["restricoes"][cnt]["k"], b["restricoes"][cnt]["n"]) == (1, 1) and not b["repetido"]
    assert all(c["n_insuficiente"] for arm in rep["bracos"].values() for c in arm["restricoes"].values())
    txt = PJ.report_text(rep)
    assert "1/2" in txt and "não mede variação" in txt and "n pequeno" in txt


def test_report_unknown_screen_and_empty(tmp_path):
    d, _ = _setup(tmp_path)
    with pytest.raises(PJ.ProjectError):
        PJ.report(d, "x")
    assert "nenhuma rodada" in PJ.report_text(PJ.report(d, "t"))


def test_cli_report_and_round_flags(tmp_path):
    d, img = _setup(tmp_path)
    ann = _ann(tmp_path, [("caixa azul", [0.1, 0.4, 0.2, 0.2]), ("caixa vermelha", [0.6, 0.4, 0.2, 0.2])])
    r = subprocess.run([sys.executable, "-m", "scenelang", "project", "round", str(d), "t", str(img), "--arm", "A", "--seed", "3",
                        "--annotations", str(ann)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    assert "medição independente" in r.stdout
    r = subprocess.run([sys.executable, "-m", "scenelang", "project", "report", str(d), "t"], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0 and "[A]" in r.stdout, r.stderr
    r = subprocess.run([sys.executable, "-m", "scenelang", "project", "report", str(d)], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 2
