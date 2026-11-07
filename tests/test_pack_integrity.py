import shutil

import pytest

pytest.importorskip("PIL")
if not shutil.which("rsvg-convert"):
    pytest.skip("rsvg-convert ausente", allow_module_level=True)
from pathlib import Path

import yaml
from PIL import Image

from scenelang import canon
from scenelang import color as C
from scenelang import pack as PK
from scenelang.validate import load_text

EX = Path(__file__).parent.parent / "examples"


def scene_of(text):
    d, s, _ = load_text(text)
    assert s is not None, [str(x) for x in d]
    return s


def many(n, overlap=False):
    ents = []
    for i in range(n):
        x = (i % 6) * 0.15 + (0.03 if overlap else 0.0) * (i % 2)
        y = (i // 6) * 0.2 + 0.02
        ents.append({"id": f"e{i:02d}", "kind": "prop", "label": f"objeto {i}", "desc": f"objeto {i}", "plane": "foreground",
                     "box": [round(x, 3), round(y, 3), 0.14 if not overlap else 0.2, 0.18]})
    return yaml.safe_dump({"scene": "muitas", "canvas": {"ratio": "4:3"}, "style": "x", "intent": {"emotion": "a", "story": "b", "focal": "e00"},
                           "entities": ents}, allow_unicode=True, sort_keys=False)


@pytest.mark.parametrize("n", [3, 12, 25, 40])
def test_cores_do_seg_sao_distintas_para_muitas_entidades(n):
    cols = PK.seg_colors([f"e{i}" for i in range(n)])
    rgb = [C.parse_color(c) for c in cols.values()]
    assert len(set(cols.values())) == n
    worst = min(C.delta_e(a, b) for i, a in enumerate(rgb) for b in rgb[i + 1:])
    assert worst >= 12 and all(C.delta_e(a, C.parse_color(PK.BACKGROUND)) >= 12 for a in rgb)
    if n <= 25:
        assert worst >= PK.MIN_SEG_DELTA_E


def test_cores_do_seg_nao_dependem_da_ordem_de_declaracao():
    assert PK.seg_colors(["x", "y", "z"]) == PK.seg_colors(["z", "y", "x"])
    assert PK.seg_colors(["solo"]) == PK.seg_colors(["solo"])          # determinístico entre chamadas


def test_ids_duplicados_sao_erro_nao_cor_repetida():
    with pytest.raises(PK.PackError):
        PK.seg_colors(["a", "a"])


def test_seg_marca_sobreposicao_com_cor_propria_e_a_legenda_tem_id_e_cor(tmp_path):
    s = scene_of(many(8, overlap=True))
    res = PK.pack_result(s, many(8, overlap=True), tmp_path, None, None, 512, "seg")
    info = res["manifest"]["guia"]
    assert info["sobreposicoes"] and all("cor" in o for o in info["sobreposicoes"])
    ent_colors = {e["cor"] for e in info["entidades"]}
    assert all(o["cor"] not in ent_colors for o in info["sobreposicoes"])
    assert {e["id"] for e in info["entidades"]} == {e.id for e in s.entities}
    assert "Legenda do guia" in (tmp_path / "prompt_com_guia.txt").read_text(encoding="utf-8")


def test_entidade_coberta_e_entidade_fora_do_guia_viram_aviso_nao_silencio(tmp_path):
    t = (EX / "guardia.yaml").read_text(encoding="utf-8")
    res = PK.pack_result(scene_of(t), t, tmp_path, "guide")
    assert any("não é desenhado no guia" in w for w in res["warnings"])      # sky/terrain
    skipped = [e for e in res["manifest"]["guia"]["entidades"] if not e["incluida"]]
    assert skipped and all(e["motivo"] for e in skipped)
    with pytest.raises(PK.PackError):
        PK.pack_result(scene_of(t), t, tmp_path / "estrito", "guide", strict=True)
    assert not list((tmp_path / "estrito").glob("*.png"))


def test_rotulos_nao_colidem_mesmo_com_caixas_sobrepostas():
    s = scene_of(many(8, overlap=True))
    order = PK.draw_order(s)
    rects = PK.place_labels(order, 512, 384)
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            assert not (a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3])


@pytest.mark.parametrize("only", [None, "text", "guide", "single"])
@pytest.mark.parametrize("style", ["blocks", "seg"])
def test_ida_e_volta_cena_pack_unpack_cena(tmp_path, only, style):
    t = (EX / "guardia.yaml").read_text(encoding="utf-8") + "\n# nota com acento ç, seta → e japonês 日本\n"
    s = scene_of(t)
    res = PK.pack_result(s, t, tmp_path, only, None, 640, style)
    src = tmp_path / "cena_unica.png" if only == "single" else tmp_path
    r = PK.unpack_checked(src)
    assert r["ok"], r["problems"]
    assert r["yaml"] == t
    assert canon.scene_hash(scene_of(r["yaml"]).data) == canon.scene_hash(s.data) == res["manifest"]["hash_cena"]
    if only == "single":
        assert [p.name for p in tmp_path.iterdir()] == ["cena_unica.png"]          # um arquivo só, de verdade


def test_unpack_detecta_adulteracao(tmp_path):
    t = (EX / "guardia.yaml").read_text(encoding="utf-8")
    PK.pack_result(scene_of(t), t, tmp_path, None, None, 512)
    assert PK.unpack_checked(tmp_path)["ok"]
    (tmp_path / "prompt.txt").write_text("outro texto", encoding="utf-8")
    r = PK.unpack_checked(tmp_path)
    assert not r["ok"] and any("prompt.txt mudou" in p for p in r["problems"])
    (tmp_path / "cena.yaml").write_text(t.replace("guardia", "guardiao", 1), encoding="utf-8")
    assert any("hash" in p or "mudou" in p for p in PK.unpack_checked(tmp_path)["problems"])


def test_png_sem_metadados_e_reportado(tmp_path):
    p = tmp_path / "x.png"
    Image.new("RGB", (8, 8)).save(p)
    r = PK.unpack_checked(p)
    assert not r["ok"] and "metadados" in r["problems"][0]


def test_texto_do_painel_nao_e_cortado_e_a_proporcao_e_avisada(tmp_path):
    t = (EX / "guardia.yaml").read_text(encoding="utf-8")
    res = PK.pack_result(scene_of(t), t, tmp_path, "single", None, 480)
    W, H = res["manifest"]["dimensoes"]["cena_unica.png"]
    assert Image.open(tmp_path / "cena_unica.png").size == (W, H)
    assert any("proporção" in w for w in res["warnings"]) == (max(W, H) / min(W, H) > PK.DIM_LIMITS["max_aspect"])
    # quebra por largura medida: nenhuma linha passa da largura útil
    f = PK._font(15)
    for ln in PK._wrap("palavra " * 300 + "x" * 400, f, W - 48):
        assert f.getlength(ln) <= W - 48 + 1


def test_dimensoes_extremas_geram_aviso():
    assert PK.check_dimensions(100, 100) and PK.check_dimensions(5000, 1000) and PK.check_dimensions(1000, 4000)
    assert PK.check_dimensions(1024, 1024) == []


def test_estilos_planejados_dao_erro_explicito():
    s = scene_of(many(3))
    for st in PK.PLANNED_GUIDE_STYLES:
        with pytest.raises(PK.PackError, match="não está implementado"):
            PK.guide_render(s, 256, False, st)
    with pytest.raises(PK.PackError, match="desconhecido"):
        PK.guide_render(s, 256, False, "xyz")
    assert all(e["geometria"] == "caixa" for e in PK.guide_info(s, "seg")["entidades"])
