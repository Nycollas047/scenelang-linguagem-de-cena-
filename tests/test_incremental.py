import copy
import random

import pytest
import yaml

from scenelang import cache as CA
from scenelang import canon, deps
from scenelang import compile as CP
from scenelang import patch as PA
from scenelang.validate import load_text

T = """
scene: inc
canvas: {ratio: "4:3"}
grid: thirds
style: "pixel art"
intent: {emotion: calma, story: um sapo e uma fogueira, focal: sapo}
palette: {mode: fixed, colors: {a: "#112233", b: "#445566"}}
lights:
  - {role: key, color: laranja, source: fogueira, hits: [sapo]}
entities:
  - {id: sapo, kind: character, label: o sapo, desc: sapo verde, plane: foreground, box: [0.30, 0.4, 0.3, 0.45]}
  - {id: fogueira, kind: prop, label: a fogueira, desc: fogueira acesa, plane: foreground, box: [0.65, 0.6, 0.2, 0.25]}
  - {id: lua, kind: prop, label: a lua, desc: lua cheia, plane: background, box: [0.7, 0.05, 0.15, 0.15]}
asserts: ["left_of(sapo, fogueira)", "above(lua, fogueira)", "visible(sapo)"]
verify: ["max_colors(16)"]
"""


def data(t=T):
    return yaml.safe_load(t)


def scene_of(d):
    diags, s, _ = load_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False))
    assert s is not None, [str(x) for x in diags if x.level == "error"]
    return s


# ---- patch ----------------------------------------------------------------------------------------------
def test_patch_set_remove_add_append_reorder():
    d = data()
    new = PA.apply_patch(d, [
        {"op": "set", "path": "entities.sapo.box", "value": [0.2, 0.4, 0.3, 0.45]},
        {"op": "remove", "path": "entities.lua"},
        {"op": "add", "path": "entities", "value": {"id": "pedra", "kind": "prop", "label": "a pedra", "desc": "pedra", "plane": "midground", "box": [0, 0.8, 0.1, 0.1]}},
        {"op": "append", "path": "asserts", "value": "left_of(pedra, sapo)"},
        {"op": "reorder", "path": "entities", "value": ["pedra", "sapo", "fogueira"]},
        {"op": "set", "path": "style", "value": "pixel art 16 bits"},
    ])
    assert [e["id"] for e in new["entities"]] == ["pedra", "sapo", "fogueira"]
    assert new["entities"][1]["box"][0] == 0.2 and new["asserts"][-1] == "left_of(pedra, sapo)" and new["style"] == "pixel art 16 bits"
    assert d["entities"][0]["box"][0] == 0.30                       # a original não é tocada


@pytest.mark.parametrize("ops,msg", [
    ([{"op": "set", "path": "entities.nao_existe.box", "value": 1}], "não há entidade"),
    ([{"op": "remove", "path": "entities.sapo.nada"}], "não existe"),
    ([{"op": "add", "path": "entities", "value": {"id": "sapo"}}], "já existe"),
    ([{"op": "add", "path": "entities", "value": {"x": 1}}], "com `id`"),
    ([{"op": "reorder", "path": "entities", "value": ["sapo"]}], "mesmos ids"),
    ([{"op": "zzz", "path": "a"}], "inválido"),
])
def test_patch_invalido_e_erro_com_caminho_nao_silencio(ops, msg):
    with pytest.raises(PA.PatchError, match=msg):
        PA.apply_patch(data(), ops)


def test_diff_e_apply_sao_inversos_em_edicoes_aleatorias():
    rnd = random.Random(7)
    base = data()
    for _ in range(60):
        new = copy.deepcopy(base)
        for _ in range(rnd.randint(1, 4)):
            c = rnd.choice(["box", "desc", "drop", "add", "style", "order", "assert"])
            ents = new["entities"]
            if c == "box" and ents:
                rnd.choice(ents)["box"] = [round(rnd.random() * 0.5, 2), 0.1, 0.2, 0.2]
            elif c == "desc" and ents:
                rnd.choice(ents)["desc"] = f"d{rnd.randint(0, 99)}"
            elif c == "drop" and len(ents) > 1:
                ents.pop(rnd.randrange(len(ents)))
            elif c == "add":
                ents.append({"id": f"n{rnd.randint(0, 999)}", "kind": "prop", "label": "n", "desc": "n", "plane": "midground", "box": [0, 0, .1, .1]})
            elif c == "style":
                new["style"] = f"s{rnd.randint(0, 9)}"
            elif c == "order":
                rnd.shuffle(ents)
            elif c == "assert":
                new["asserts"] = list(new.get("asserts", [])) + [f"visible(x{rnd.randint(0, 9)})"]
        ids = [e["id"] for e in new["entities"]]
        if len(ids) != len(set(ids)):
            continue
        ops = PA.diff(base, new)
        assert canon.canonical(PA.apply_patch(base, ops)) == canon.canonical(new), ops
    assert PA.diff(base, copy.deepcopy(base)) == []


def test_diff_so_gera_o_necessario():
    d, n = data(), data()
    n["entities"][0]["box"] = [0.31, 0.4, 0.3, 0.45]
    assert PA.diff(d, n) == [{"op": "set", "path": "entities.sapo.box", "value": [0.31, 0.4, 0.3, 0.45]}]


# ---- dependências ----------------------------------------------------------------------------------------
def test_grafo_aponta_asserts_luzes_e_referencias_entre_entidades():
    g = deps.graph(data())
    assert g["asserts"]["left_of(sapo, fogueira)"] == ["fogueira", "sapo"] and g["sections"]["lights"] == ["fogueira", "sapo"]
    d = data()
    d["entities"][2]["at"] = "sapo.head"
    assert deps.graph(d)["entities"]["lua"] == ["sapo"]


def test_delta_so_reavalia_o_que_a_edicao_toca():
    a, b = data(), data()
    b["entities"][2]["box"] = [0.6, 0.05, 0.15, 0.15]                     # só a lua
    dl = deps.delta(a, b)
    assert dl.changed == ["lua"] and set(dl.unchanged) == {"sapo", "fogueira"} and not dl.sections
    assert dl.impacted_asserts == ["above(lua, fogueira)"]                # os outros asserts não são tocados
    assert dl.impacted_verify == ["max_colors(16)"]                       # verificador global: depende de qualquer mudança visual


def test_delta_historico_e_correcoes_nao_sao_mudanca():
    a, b = data(), data()
    b["history"] = [{"rodada": 1}]
    b["corrections"] = ["x"]
    assert deps.delta(a, b).empty


def test_delta_mudar_canvas_reavalia_todos_os_asserts_e_remover_entidade_afeta_quem_a_cita():
    a, b = data(), data()
    b["canvas"]["ratio"] = "16:9"
    assert deps.delta(a, b).sections == ["canvas"] and len(deps.delta(a, b).impacted_asserts) == 3
    c = data()
    c["entities"].pop(1)
    dl = deps.delta(a, c)
    assert dl.removed == ["fogueira"] and set(dl.impacted_asserts) == {"left_of(sapo, fogueira)", "above(lua, fogueira)"}


def test_verify_com_escopo_de_entidade_so_depende_dela():
    a, b = data(), data()
    a["verify"] = b["verify"] = ["palette_match(10, 0.9, sapo)"]
    b["entities"][2]["desc"] = "lua laranja"
    assert deps.delta(a, b).impacted_verify == []
    b["entities"][0]["desc"] = "sapo azul"
    assert deps.delta(a, b).impacted_verify == ["palette_match(10, 0.9, sapo)"]


# ---- prompt incremental ----------------------------------------------------------------------------------
def test_prompt_incremental_so_fala_do_que_mudou_e_e_menor_que_o_completo():
    a, b = data(), data()
    b["entities"][0]["desc"] = "sapo verde de chapéu roxo"
    sa, sb = scene_of(a), scene_of(b)
    p = CP.delta_prompt(sa, sb)
    assert "Mantenha exatamente igual" in p and "a fogueira" in p and "a lua" in p
    assert "Altere o sapo" in p and "chapéu roxo" in p
    assert "fogueira acesa" not in p and "lua cheia" not in p              # entidades iguais não são redescritas
    assert len(p) < len(CP.to_prose(sb)) * 0.7


def test_prompt_incremental_vazio_se_nada_mudou_e_cobre_remocao_e_acrescimo():
    a = data()
    assert CP.delta_prompt(scene_of(a), scene_of(copy.deepcopy(a))) == ""
    b = data()
    b["entities"].pop(2)
    b["asserts"] = [x for x in b["asserts"] if "lua" not in x]
    b["entities"].append({"id": "pedra", "kind": "prop", "label": "a pedra", "desc": "pedra cinza", "plane": "midground", "box": [0, 0.8, 0.1, 0.1]})
    p = CP.delta_prompt(scene_of(a), scene_of(b))
    assert "Remova: a lua" in p and "Acrescente a pedra" in p and "pedra cinza" in p


def test_prompt_incremental_inclui_secao_global_alterada():
    a, b = data(), data()
    b["style"] = "aquarela"
    assert "aquarela" in CP.delta_prompt(scene_of(a), scene_of(b))


# ---- cache -----------------------------------------------------------------------------------------------
def test_cache_acerta_com_texto_igual_e_erra_com_qualquer_mudanca():
    c = CA.Cache()
    CA.load_cached(T, c)
    CA.load_cached(T, c)
    assert c.stats()["namespaces"]["load"] == {"hits": 1, "misses": 1}
    CA.load_cached(T.replace("sapo verde", "sapo azul"), c)
    assert c.stats()["namespaces"]["load"]["misses"] == 2


def test_chave_de_compilacao_ignora_historico_mas_nao_correcoes_nem_backend():
    d = data()
    k = CA.compile_key(d, "prose")
    assert CA.compile_key({**d, "history": [{"rodada": 1}]}, "prose") == k
    assert CA.compile_key({**d, "corrections": ["x"]}, "prose") != k
    assert CA.compile_key(d, "json") != k and CA.compile_key(d, "prose", "1024") != k
    d2 = copy.deepcopy(d)
    d2["entities"][0]["desc"] = "outro"
    assert CA.compile_key(d2, "prose") != k


def test_cena_com_extends_nao_entra_no_cache_de_leitura():
    c = CA.Cache()
    CA.load_cached(T + "extends: nao_existe.yaml\n", c)
    CA.load_cached(T + "extends: nao_existe.yaml\n", c)
    assert c.stats()["entries"] == 0


def test_cache_tem_limite_de_tamanho():
    c = CA.Cache(maxsize=3)
    for i in range(10):
        c.memo("x", str(i), lambda i=i: i)
    assert c.stats()["entries"] == 3


# ---- cache de medição, API e CLI -------------------------------------------------------------------------
def test_medicao_repetida_vem_do_cache_e_so_muda_quando_algo_relevante_muda():
    pytest.importorskip("PIL")
    pytest.importorskip("scipy")
    from PIL import Image

    from scenelang import correct as CR
    CA.DEFAULT.clear()
    s = scene_of(data())
    img = Image.new("RGB", (64, 48), "#202020")
    m1 = CR.measure_full(s, img)
    m2 = CR.measure_full(s, img)
    assert m2 is m1 and CA.DEFAULT.stats()["namespaces"]["measure"] == {"hits": 1, "misses": 1}
    d = data()
    d["history"] = [{"rodada": 1}]
    d["corrections"] = ["algo"]
    assert CR.measure_full(scene_of(d), img) is m1                                      # histórico/correções não mudam a medição
    d2 = data()
    d2["asserts"] = ["left_of(fogueira, sapo)"]
    assert CR.measure_full(scene_of(d2), img) is not m1                                  # assert diferente: remede
    assert CR.measure_full(s, Image.new("RGB", (64, 48), "#202021")) is not m1           # outra imagem: remede
    assert CR.measure_full(s, img, {"sapo": [0, 0, 1, 1]}) is not m1                     # outras caixas informadas: remede


def test_api_diff_patch_delta():
    from scenelang import api
    a = T
    b = T.replace("sapo verde", "sapo verde de chapéu")
    r = api.diff_scenes(a, b)
    assert r["changed"] == ["sapo"] and r["patch"] == [{"op": "set", "path": "entities.sapo.desc", "value": "sapo verde de chapéu"}]
    p = api.patch_scene(a, r["patch"])
    assert p["ok"] and "chapéu" in p["text"]
    assert not api.patch_scene(a, [{"op": "remove", "path": "entities.zzz"}])["ok"]
    dp = api.delta_prompt(a, p["text"])
    assert dp["ok"] and dp["chars"] < dp["full_chars"] and "Altere o sapo" in dp["prompt"]


def test_cli_diff_patch_delta(tmp_path, capsys):
    import json
    from scenelang.cli import main
    a, b = tmp_path / "a.yaml", tmp_path / "b.yaml"
    a.write_text(T, encoding="utf-8")
    b.write_text(T.replace("lua cheia", "lua minguante"), encoding="utf-8")
    assert main(["diff", str(a), str(b)]) == 0 and json.loads(capsys.readouterr().out)["changed"] == ["lua"]
    ops = tmp_path / "ops.json"
    ops.write_text(json.dumps([{"op": "set", "path": "entities.lua.desc", "value": "lua minguante"}]), encoding="utf-8")
    out = tmp_path / "n.yaml"
    assert main(["patch", str(a), str(ops), "--out", str(out)]) == 0 and "minguante" in out.read_text(encoding="utf-8")
    capsys.readouterr()
    assert main(["delta-prompt", str(a), str(b)]) == 0
    assert "Altere a lua" in capsys.readouterr().out
