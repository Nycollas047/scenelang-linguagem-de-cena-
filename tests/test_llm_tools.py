"""Ferramentas para uso por LLM: normalização, --fix, cartilha, modelos, API JSON."""
from __future__ import annotations

import json

import pytest
import yaml

from scenelang import api, normalize, templates
from scenelang.cli import main
from scenelang.fixes import apply_fixes, parse_path
from scenelang.validate import load_text


@pytest.mark.parametrize("name", templates.names())
def test_templates_are_valid_without_warnings(name):
    diags, scene, _ = load_text(templates.get(name))
    assert scene is not None and not diags, [str(d) for d in diags]


def test_short_forms_are_normalized():
    d = yaml.safe_load(templates.get("emblem"))
    d["canvas"] = "1:1"
    d["style"] = "vetor"
    d.pop("grid")
    d["entities"][0]["kind"] = "luz"
    d["entities"][0]["plane"] = "fundo"
    d["entities"][1].pop("label", None)
    out, notes = normalize.apply_defaults(d)
    assert out["canvas"] == {"shape": "rect", "ratio": "1:1"} and out["style"] == {"base": "vetor"}
    assert out["grid"] == {"kind": "golden"} and out["entities"][0]["kind"] == "light_source"
    assert out["entities"][0]["plane"] == "background" and notes


def test_background_mood_wind_verify_aliases():
    d = yaml.safe_load(templates.get("splash"))
    d["background"] = {"mode": "chroma_key"}
    d["atmosphere"]["mood"] = "epic"
    d["verify"] = ["grid_aligned"]
    out, _ = normalize.apply_defaults(d)
    assert out["background"]["mode"] == "chromakey" and out["atmosphere"]["mood"] == {"name": "epic"}
    assert out["atmosphere"]["wind"]["strength"] == "high" and out["verify"] == ["grid_aligned()"]


def test_parse_path():
    assert parse_path("$.entities[2].character.hair.texture") == ["entities", 2, "character", "hair", "texture"]


def test_fix_applies_vocabulary_and_field_typos():
    text = templates.get("splash").replace("kind: creature", "kind: creatur").replace("camera:", "camra:")
    res = api.fix(text)
    assert any("creatur" in a for a in res["applied"]) and any("camra" in a for a in res["applied"])
    assert res["ok"], res["errors"]


def test_fix_leaves_unsafe_errors_alone():
    text = templates.get("splash").replace("ratio: \"16:9\"", "ratio: \"abc\"")
    res = api.fix(text)
    assert not res["ok"] and res["applied"] == []


def test_api_validate_and_compile_are_json_serializable():
    text = templates.get("sprite")
    v = api.validate(text)
    assert v["ok"]
    c = api.compile_scene(text, "prose")
    assert c["ok"] and "ILUSTRAÇÃO" not in c["output"].upper()[:0] and c["output"]
    json.dumps([v, c, api.vocab(), api.plan(text)])
    assert not api.compile_scene(text, "nope")["ok"]


def test_primer_is_short_and_lists_templates():
    p = api.primer()
    assert len(p.splitlines()) <= 110 and "scenelang new" in p
    for n in templates.names():
        assert n in p


def test_cli_new_primer_vocab_fix(tmp_path, capsys):
    out = tmp_path / "s.yaml"
    assert main(["new", "sprite", "--out", str(out)]) == 0
    assert main(["validate", str(out)]) == 0
    broken = tmp_path / "b.yaml"
    broken.write_text(out.read_text(encoding="utf-8").replace("stylized", "stylised"), encoding="utf-8")
    assert main(["validate", str(broken)]) == 1
    assert main(["validate", str(broken), "--fix", "--out", str(tmp_path / "ok.yaml")]) == 0
    capsys.readouterr()
    assert main(["vocab", "--json"]) == 0
    assert "entity.kind" in json.loads(capsys.readouterr().out)
    assert main(["primer"]) == 0
