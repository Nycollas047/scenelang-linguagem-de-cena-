"""Tecidos e escamas dentro da camada de materiais."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scenelang.compile import to_prose
from scenelang.validate import validate_data

EX = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture()
def data():
    d = yaml.safe_load((EX / "pixel_heroi_planejada.yaml").read_text(encoding="utf-8"))
    d["materials"] = {
        "seda": {"fabric": "silk", "weave": "brocade", "drape": "flowing", "color": "#2850d2"},
        "dragao": {"scales": {"pattern": "overlapping", "size": "medium", "edge": "serrated", "sheen": "high",
                              "gradient": {"from": "#14502d", "to": "#d4a528"}, "coverage": ["back", "tail"]}},
    }
    d["entities"][0]["parts"] = {"cape": "seda", "skin": "dragao"}
    return d


def msgs(diags, level):
    return " | ".join(f"{d.path} {d.message} {d.hint or ''}" for d in diags if d.level == level)


def test_fabric_and_scales_need_no_explicit_base(data):
    diags, scene = validate_data(data)
    assert not msgs(diags, "error")
    prose = to_prose(scene)
    for frag in ("tecido de seda", "brocado", "caimento fluido", "sobrepostas como telhas", "bordas serrilhadas",
                 "em degradê de", "cobrindo o dorso, a cauda"):
        assert frag in prose


def test_spec_without_base_fabric_or_scales_is_an_error(data):
    data["materials"]["vazio"] = {"finish": "matte"}
    assert "base" in msgs(validate_data(data)[0], "error")


def test_closed_vocabularies_suggest(data):
    data["materials"]["seda"]["fabric"] = "silke"
    assert "silk" in msgs(validate_data(data)[0], "error")
    data["materials"]["dragao"]["scales"]["pattern"] = "overlap"
    assert "overlapping" in msgs(validate_data(data)[0], "error")


def test_contradictions_warn(data):
    data["materials"]["seda"]["fabric"] = "canvas"
    assert "canvas" in msgs(validate_data(data)[0], "warning")
    data["materials"]["dragao"]["scales"].update({"pattern": "granular", "size": "huge"})
    assert "granulares" in msgs(validate_data(data)[0], "warning")


def test_gradient_shape_is_checked(data):
    data["materials"]["dragao"]["scales"]["gradient"] = {"from": "#14502d"}
    assert "from: cor, to: cor" in msgs(validate_data(data)[0], "error")
