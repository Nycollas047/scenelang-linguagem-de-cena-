"""Invariantes que valem para TODOS os exemplos do repositório: servem de regressão para qualquer exemplo novo."""
from pathlib import Path

import pytest
import yaml

from scenelang import canon
from scenelang import compile as CP
from scenelang import deps
from scenelang import loss as LS
from scenelang import patch as PA
from scenelang.validate import load_text

EXAMPLES = sorted((Path(__file__).parent.parent / "examples").glob("*.yaml"))


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_hash_nao_depende_da_ordem_das_chaves_nem_do_formato_yaml(path):
    d = yaml.safe_load(path.read_text(encoding="utf-8"))
    h = canon.scene_hash(d)
    again = yaml.safe_load(yaml.safe_dump(d, allow_unicode=True, sort_keys=True))        # chaves reordenadas
    flow = yaml.safe_load(yaml.safe_dump(d, allow_unicode=True, default_flow_style=True))  # outro formato
    assert canon.scene_hash(again) == canon.scene_hash(flow) == h


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_compila_em_todos_os_backends_sem_chave_sem_destino(path):
    diags, scene, _ = load_text(path.read_text(encoding="utf-8"), base_dir=path.parent)
    if scene is None:
        pytest.skip("exemplo depende de arquivo externo ou é inválido de propósito")
    for b, fn in CP.BACKENDS.items():
        assert fn(scene).strip()
        assert not [i for i in LS.report(scene, b) if i.level == "unsupported"], b


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_diff_da_cena_consigo_mesma_e_vazio_e_patch_reconstroi(path):
    d = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert PA.diff(d, d) == [] and deps.delta(d, d).empty
    e = yaml.safe_load(path.read_text(encoding="utf-8"))
    e["style"] = "outro estilo"
    assert canon.canonical(PA.apply_patch(d, PA.diff(d, e))) == canon.canonical(e)
