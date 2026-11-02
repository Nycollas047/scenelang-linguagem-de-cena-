"""Testes de herança, bibliotecas, varreduras e travas."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from scenelang import variants as V
from scenelang.cli import main
from scenelang.compile import to_prose
from scenelang.evalform import apply_answers, build_form
from scenelang.validate import load_file, validate_data

ROOT = Path(__file__).resolve().parent.parent
EX = ROOT / "examples"


def errors(diags):
    return [d for d in diags if d.level == "error"]


def test_merge_rules():
    base = {"a": {"x": 1, "y": 2}, "l": [1, 2], "entities": [{"id": "a", "v": 1}, {"id": "b", "v": 2}], "drop": 1}
    over = {"a": {"y": 3}, "l": [9], "entities": [{"id": "a", "w": 5}, {"id": "b", "remove": True}, {"id": "c"}], "drop": None}
    out = V.merge(base, over)
    assert out["a"] == {"x": 1, "y": 3}
    assert out["l"] == [9]
    assert out["entities"] == [{"id": "a", "v": 1, "w": 5}, {"id": "c"}]
    assert "drop" not in out
    assert base["a"]["y"] == 2          # a base não é alterada


def test_extends_and_import_example_is_valid_and_self_contained():
    diags, scene, data = load_file(EX / "pixel_heroi_noite.yaml")
    assert scene is not None, [str(d) for d in diags]
    assert "extends" not in data and "import" not in data
    assert data["scene"] == "Cavaleira da Lua (noite)"
    assert data["entities"][0]["parts"]["armor"] == "bronze_gasto"      # sobrescreveu
    assert data["entities"][0]["parts"]["cape"] == "capa_lona"          # herdou
    assert "bronze_gasto" in data["materials"] and "aco_polido" in data["materials"]
    prose = to_prose(scene)
    assert "mysterious" not in prose and "misterioso" in prose
    assert "Mantenha exatamente igual à versão anterior: a cavaleira; a câmera e o enquadramento." in prose
    assert "metal arranhado" in prose


def test_scene_wins_over_library(tmp_path):
    lib = tmp_path / "lib.yaml"
    lib.write_text("colors: {ink: '#000000', extra: '#ffffff'}\n", encoding="utf-8")
    scene = tmp_path / "s.yaml"
    scene.write_text("import: [lib.yaml]\ncolors: {ink: '#111111'}\n", encoding="utf-8")
    data = V.resolve(yaml.safe_load(scene.read_text()), tmp_path)
    assert data["colors"] == {"ink": "#111111", "extra": "#ffffff"}


def test_extends_cycle_and_missing_file(tmp_path):
    (tmp_path / "a.yaml").write_text("extends: b.yaml\n", encoding="utf-8")
    (tmp_path / "b.yaml").write_text("extends: a.yaml\n", encoding="utf-8")
    diags, scene, _ = load_file(tmp_path / "a.yaml")
    assert scene is None and "ciclo" in str(diags[0])
    (tmp_path / "c.yaml").write_text("extends: nao_existe.yaml\n", encoding="utf-8")
    diags, scene, _ = load_file(tmp_path / "c.yaml")
    assert scene is None and "não consegui abrir" in str(diags[0])


def test_set_path_by_entity_id_and_errors():
    d = {"entities": [{"id": "knight", "brightness": "normal"}], "atmosphere": {"wind": {"strength": "low"}}}
    V.set_path(d, "entities.knight.brightness", "max")
    V.set_path(d, "atmosphere.wind.strength", "high")
    V.set_path(d, "atmosphere.weather", "rain")             # cria a última chave
    assert d["entities"][0]["brightness"] == "max" and d["atmosphere"]["wind"]["strength"] == "high"
    assert d["atmosphere"]["weather"] == "rain"
    for bad in ("entities.ninguem.brightness", "foo.bar.baz", "entities.knight"):
        with pytest.raises(V.VariantError):
            V.set_path(d, bad, 1)


def test_make_sweep_parses_values():
    path, items = V.make_sweep({"a": {"n": 0}}, "a.n=1,2,3")
    assert path == "a.n" and [d["a"]["n"] for _, d in items] == [1, 2, 3]
    for bad in ("a.n", "a.n=1"):
        with pytest.raises(V.VariantError):
            V.make_sweep({"a": {"n": 0}}, bad)


def test_kendall_tau():
    assert V.kendall_tau([1, 2, 3], [1, 2, 3]) == 1
    assert V.kendall_tau([1, 2, 3], [3, 2, 1]) == -1
    assert 0 < V.kendall_tau([1, 2, 3], [1, 3, 2]) < 1


def test_sweep_cli_and_score(tmp_path, capsys):
    out = tmp_path / "sw"
    assert main(["sweep", str(EX / "pixel_heroi.yaml"), "--axis", "atmosphere.wind.strength=low,normal,high", "--out", str(out)]) == 0
    assert (out / "1_low.txt").exists() and (out / "3_high.yaml").exists()
    texts = [(out / f).read_text(encoding="utf-8") for f in ("1_low.txt", "2_normal.txt", "3_high.txt")]
    assert "vento fraco" in texts[0] and "vento moderado" in texts[1] and "vento forte" in texts[2]
    form_path = out / "ficha_eixo.yaml"
    assert main(["sweep-score", str(form_path)]) == 2                # ainda não preenchida
    form = yaml.safe_load(form_path.read_text(encoding="utf-8"))
    form["ordem_observada"] = [1, 2, 3]
    form_path.write_text(yaml.safe_dump(form), encoding="utf-8")
    assert main(["sweep-score", str(form_path)]) == 0
    form["ordem_observada"] = [3, 2, 1]
    form_path.write_text(yaml.safe_dump(form), encoding="utf-8")
    assert main(["sweep-score", str(form_path)]) == 1
    assert "sem controle" in capsys.readouterr().out


def test_sweep_skips_invalid_variants(tmp_path, capsys):
    out = tmp_path / "sw"
    rc = main(["sweep", str(EX / "pixel_heroi.yaml"), "--axis", "atmosphere.wind.strength=low,tornado", "--out", str(out)])
    assert rc == 0
    assert "inválida" in capsys.readouterr().err and (out / "1_low.txt").exists() and not (out / "2_tornado.txt").exists()


def test_lock_passed_locks_only_what_passed():
    diags, scene, data = load_file(EX / "guardia.yaml")
    form = yaml.safe_load(build_form(scene))
    for it in form["itens"]:
        it["ok"] = "nao" if it["assert"].startswith("near(spear.tip") else "sim"
        it["tag"] = "proporção" if it["ok"] == "nao" else None
    new, failed = apply_answers(scene, yaml.safe_dump(form, allow_unicode=True), lock_passed=True)
    assert len(failed) == 1
    assert "spear" not in new["lock"]                  # o que falhou não trava
    assert "warrior" in new["lock"] and "colossus" in new["lock"]
    diags, sc = validate_data(new)
    assert sc is not None and not errors(diags)
    assert "Mantenha exatamente igual" in to_prose(sc)


def test_all_examples_validate():
    for f in sorted(EX.glob("*.yaml")):
        if f.name.startswith(("biblioteca", "plano_")):
            continue
        diags, scene, _ = load_file(f)
        assert scene is not None, (f.name, [str(d) for d in diags])
