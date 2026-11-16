"""Medição independente: anotação cega reconciliada com a cena."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scenelang import reconcile as RC
from scenelang.validate import load_file

ROOT = Path(__file__).resolve().parent.parent
SCENE = ROOT / "examples" / "dark_fantasy_chefe.yaml"


@pytest.fixture(scope="module")
def scene():
    return load_file(str(SCENE))[1]


def ann(objs, cego=True):
    return {"formato": RC.FORMAT, "anotador": "teste", "cego": cego, "objetos": [{"nome": n, "caixa": b} for n, b in objs]}


def _by_raw(rec):
    return {a["raw"]: a for a in rec["asserts"]}


def test_extra_pillars_fail_the_count_and_are_listed(scene):
    boxes = [("pilar de pedra quebrado", [0.10, 0.2, 0.08, 0.3]), ("pilar de pedra quebrado", [0.80, 0.2, 0.08, 0.3]),
             ("pilar de pedra", [0.30, 0.3, 0.06, 0.2]), ("pilar de pedra", [0.60, 0.3, 0.06, 0.2]),
             ("cavaleiro de armadura", [0.4, 0.6, 0.1, 0.25])]
    rec = RC.reconcile(scene, ann(boxes))
    c = _by_raw(rec)["count(pillar) == 2"]
    assert not c["ok"] and "4" in c["detail"]
    assert len(rec["extras"]) == 2 and all("pilar" in e["nome"] for e in rec["extras"])


def test_correct_count_passes(scene):
    rec = RC.reconcile(scene, ann([("pilar quebrado", [0.1, 0.2, 0.08, 0.3]), ("pilar quebrado", [0.8, 0.2, 0.08, 0.3])]))
    assert _by_raw(rec)["count(pillar) == 2"]["ok"]
    assert rec["extras"] == []


def test_matching_is_one_to_one_and_reports_missing(scene):
    rec = RC.reconcile(scene, ann([("pilar quebrado", [0.1, 0.2, 0.08, 0.3])]))
    assert [p["entidade"] for p in rec["casamentos"]] == ["pillar_1"] or [p["entidade"] for p in rec["casamentos"]] == ["pillar_2"]
    assert "boss" in rec["ausentes"] and len(rec["casamentos"]) == 1


def test_quantity_field_counts(scene):
    a = ann([("pilar quebrado", [0.1, 0.2, 0.08, 0.3])])
    a["objetos"][0]["quantidade"] = 3
    assert not _by_raw(RC.reconcile(scene, a))["count(pillar) == 2"]["ok"]


def test_non_blind_annotation_is_flagged(scene):
    rec = RC.reconcile(scene, ann([("pilar", [0.1, 0.2, 0.08, 0.3])], cego=False))
    assert rec["cego"] is False and "NÃO cego" in RC.summary(rec)


@pytest.mark.parametrize("bad", [None, [], {}, {"formato": "x"}, {"formato": RC.FORMAT, "objetos": []},
                                 {"formato": RC.FORMAT, "objetos": [{"nome": "a", "caixa": [0, 0, 2, 1]}]},
                                 {"formato": RC.FORMAT, "objetos": [{"nome": "a", "caixa": [0, 0, float("nan"), 1]}]},
                                 {"formato": RC.FORMAT, "objetos": [{"nome": "a", "caixa": [0, 0, 0.1, 0.1], "quantidade": 0}]},
                                 {"formato": RC.FORMAT, "objetos": [{"nome": "", "caixa": [0, 0, 0.1, 0.1]}]}])
def test_invalid_annotation_rejected(scene, bad):
    with pytest.raises(RC.ReconcileError):
        RC.reconcile(scene, copy.deepcopy(bad))


def test_form_example_is_neutral_for_the_test_scene(scene):
    """O exemplo do formulário não pode soprar nomes de entidades da cena (senão a anotação deixa de ser independente)."""
    words = {w for e in scene.entities for w in RC._entity_stems(e)}
    assert not (RC._stems(RC.form_text()) & words)


def test_cli_roundtrip(tmp_path):
    p = tmp_path / "a.json"
    p.write_text(json.dumps(ann([("pilar quebrado", [0.1, 0.2, 0.08, 0.3])] * 4)), encoding="utf-8")
    r = subprocess.run([sys.executable, "-m", "scenelang", "reconcile", str(SCENE), str(p), "--json"], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 1, r.stderr
    assert json.loads(r.stdout)["formato"] == RC.OUT_FORMAT
    f = subprocess.run([sys.executable, "-m", "scenelang", "annotate-form"], capture_output=True, text=True, cwd=ROOT)
    assert f.returncode == 0 and RC.FORMAT in f.stdout
    bad = tmp_path / "b.json"
    bad.write_text("{}", encoding="utf-8")
    assert subprocess.run([sys.executable, "-m", "scenelang", "reconcile", str(SCENE), str(bad)], capture_output=True, text=True, cwd=ROOT).returncode == 2
