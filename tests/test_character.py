"""Camada de personagem: validação, frases neutras, cores de pele na escolha da chave."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scenelang import palette as PAL
from scenelang.compile import to_prose
from scenelang.validate import validate_data

EX = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture()
def data():
    d = yaml.safe_load((EX / "pixel_heroi_planejada.yaml").read_text(encoding="utf-8"))
    d["entities"][0]["character"] = {
        "age_group": "adult", "heritage": "afro-brasileira",
        "skin": {"tone": 8, "undertone": "warm", "marks": ["freckles"]},
        "hair": {"texture": "coily", "length": "medium", "color": "#1c1410", "style": "tranças finas"},
        "eyes": {"color": "marrom", "shape": "almond"},
        "face": {"shape": "oval", "nose": "broad", "lips": "full", "jaw": "defined"},
        "body": {"build": "athletic", "height": "tall", "shoulders": "broad", "waist": "narrow", "limbs": "long",
                 "posture": "upright"},
        "features": {"hands": "mãos largas"},
    }
    return d


def errs(diags):
    return " | ".join(f"{d.path} {d.message} {d.hint or ''} {d.accepted or ''}" for d in diags if d.level == "error")


def test_valid_character_compiles_neutral_sentences(data):
    diags, scene = validate_data(data)
    assert not errs(diags)
    prose = to_prose(scene)
    for frag in ("herança afro-brasileira", "escala Monk", "subtom quente", "sardas", "crespo", "tranças finas",
                 "lábios carnudos", "ombros largos", "postura ereta", "As mãos: mãos largas", "Subtom quente".lower()):
        assert frag in prose


def test_heritage_does_not_infer_traits(data):
    c = data["entities"][0]["character"]
    del c["skin"], c["hair"], c["face"], c["eyes"]
    base = to_prose(validate_data(yaml.safe_load((EX / "pixel_heroi_planejada.yaml").read_text(encoding="utf-8")))[1])
    prose = to_prose(validate_data(data)[1])
    assert "herança afro-brasileira" in prose and "Monk" not in prose
    assert prose.count("cabelo") == base.count("cabelo") and prose.count("pele") == base.count("pele")


def test_enum_errors_suggest(data):
    data["entities"][0]["character"]["hair"]["texture"] = "coil"
    assert "coily" in errs(validate_data(data)[0])
    data["entities"][0]["character"]["skin"]["tone"] = 11
    assert "1 a 10" in errs(validate_data(data)[0])


def test_character_only_on_character_kind(data):
    data["entities"][0]["kind"] = "prop"
    assert "kind: character" in errs(validate_data(data)[0])


def test_skin_exact_color_wins_and_warns(data):
    data["entities"][0]["character"]["skin"] = {"tone": 3, "color": {"cmyk": [10, 30, 45, 0]}}
    diags, scene = validate_data(data)
    assert any("vale a cor exata" in d.message for d in diags)
    assert "pele de cor" in to_prose(scene).lower()


def test_skin_enters_reference_colors(data):
    del data["entities"][0]["character"]["skin"]
    n0 = len(PAL.reference_colors(data))
    data["entities"][0]["character"]["skin"] = {"tone": 5}
    assert len(PAL.reference_colors(data)) == n0 + 1


def test_bald_with_style_warns(data):
    data["entities"][0]["character"]["hair"] = {"length": "bald", "style": "coque"}
    assert "careca" in " ".join(d.message for d in validate_data(data)[0])


def test_unknown_key_is_reported(data):
    data["entities"][0]["character"]["skin"]["tint"] = 3
    assert "tint" in errs(validate_data(data)[0])


def test_facial_hair_felt_eye_anchor_and_heritage_prefix(data):
    c = data["entities"][0]["character"]
    c["facial_hair"] = {"type": "beard", "length": "long", "color": "grisalho"}
    c["heritage"] = "herança indígena brasileira"
    data["entities"][0]["parts"] = {"hat": {"fabric": "felt"}}
    data["intent"]["focal"] = f"{data['entities'][0]['id']}.eye"
    diags, scene = validate_data(data)
    assert not errs(diags), errs(diags)
    prose = to_prose(scene)
    assert "Barba longa" in prose and "feltro" in prose and prose.count("herança herança") == 0


def test_bad_hair_color_lists_accepted_names(data):
    data["entities"][0]["character"]["hair"]["color"] = "arco-íris"
    assert "grisalho" in errs(validate_data(data)[0])
