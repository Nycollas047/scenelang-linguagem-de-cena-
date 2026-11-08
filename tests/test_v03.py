"""Testes do pacote v0.3: avisos de contradição, snap, despill, folha de variantes."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from scenelang import fx, guides
from scenelang import verify as V
from scenelang.cli import main
from scenelang.compile import to_prose
from scenelang.validate import validate_data

ROOT = Path(__file__).resolve().parent.parent
EX = ROOT / "examples"
np = pytest.importorskip("numpy")
Image = pytest.importorskip("PIL.Image")


@pytest.fixture()
def data():
    return yaml.safe_load((EX / "pixel_heroi_planejada.yaml").read_text(encoding="utf-8"))


def warns(diags):
    return " | ".join(d.message for d in diags if d.level == "warning")


# ---------------------------------------------------------------- avisos
def test_example_scenes_have_no_warnings(data):
    assert not validate_data(data)[0]


def test_palette_description_contradiction_warns(data):
    data["entities"][0]["desc"] = data["entities"][0]["desc"].replace("azul", "vermelha")
    assert "cita a cor 'vermelho'" in warns(validate_data(data)[0])


def test_lint_waits_for_the_model_to_choose_colors():
    d = yaml.safe_load((EX / "pixel_heroi.yaml").read_text(encoding="utf-8"))
    assert not validate_data(d)[0]          # model_picks sem proposta: nada a comparar ainda


def test_symmetric_whole_body_with_wind_warns(data):
    data["verify"] = ["symmetric(vertical, 0.8)"]
    assert "quebra a simetria" in warns(validate_data(data)[0])
    data["verify"] = ["symmetric(vertical, 0.8, legs)"]
    assert "quebra a simetria" not in warns(validate_data(data)[0])


def test_margin_warning(data):
    data["entities"][0]["box"] = [0.25, 0.01, 0.5, 0.9]
    assert "margem" in warns(validate_data(data)[0])


# ---------------------------------------------------------------- guias em células
def test_guides_in_grid_rows(data):
    prose = to_prose(validate_data(data)[1])
    assert "linhas da grade (de 1 a 32, contando do topo)" in prose
    assert "o topo da cabeça na linha 3" in prose and "(pés) na linha 30" in prose
    assert "ficam de fora da simetria" in prose


# ---------------------------------------------------------------- imagens
def sprite(scene, n=64, flawed=False):
    key = fx.key_color(scene.data)
    img = Image.new("RGB", (640, 640), key)
    px = img.load()
    for y in range(40, 600):                   # corpo azul com halo esverdeado nas bordas
        for x in range(200, 440):
            px[x, y] = (40, 90, 210)
    if flawed:
        for y in range(40, 600):
            for x in (198, 199, 440, 441):
                px[x, y] = (30, 200, 60)       # halo parecido com a chave
    return img


def test_snap_makes_real_pixel_art_and_removes_halo(data):
    _, scene = validate_data(data)
    out = V.snap(scene, sprite(scene, flawed=True), grid=32, colors=8, fit=True, scale=4)
    assert out.mode == "RGBA" and out.size == (32 * 4, 32 * 4)
    a = np.asarray(out)[..., 3]
    assert a[0, 0] == 0 and a.max() == 255
    scene.data["verify"] = ["grid_aligned(32)", "no_spill()", "fit_guides(0.04)", "max_colors(8)"]
    rgba_bg = Image.new("RGB", out.size, fx.key_color(scene.data))
    rgba_bg.paste(out, mask=out.split()[3])
    res = {r.raw: r for r in V.run(scene, rgba_bg)}
    assert all(r.ok for r in res.values()), {k: v.detail for k, v in res.items() if not v.ok}


def test_snap_to_palette_uses_only_palette_colors(data):
    _, scene = validate_data(data)
    out = V.snap(scene, sprite(scene), grid=32, to_palette=True, fit=True, scale=1)
    arr = np.asarray(out)
    solid = arr[arr[..., 3] == 255][:, :3]
    allowed = {tuple(c) for c in __import__("scenelang.palette", fromlist=["x"]).all_colors(scene.data).values()}
    assert {tuple(int(v) for v in px) for px in solid} <= allowed


def test_snap_requires_grid_and_guides(data):
    _, scene = validate_data(data)
    scene.data["canvas"].pop("pixel_grid")
    with pytest.raises(ValueError):
        V.snap(scene, sprite(scene))
    scene.data["canvas"]["pixel_grid"] = 32
    scene.data.pop("guides")
    with pytest.raises(ValueError):
        V.snap(scene, sprite(scene), fit=True)


def test_despill_removes_key_tint_from_edges(data):
    _, scene = validate_data(data)
    key = fx.key_color(scene.data)
    img = Image.new("RGB", (60, 60), key)
    px = img.load()
    for y in range(10, 50):
        for x in range(10, 50):
            edge = x in (10, 49) or y in (10, 49)
            px[x, y] = (80, 150, 90) if edge else (200, 120, 60)   # borda esverdeada
    out = np.asarray(V.cutout_chroma(scene, img)).astype(int)
    solid = out[..., 3] > 128
    ring = solid & ~np.pad(solid[2:-2, 2:-2], 2)                      # borda do sujeito
    assert (out[..., 1][ring] <= np.maximum(out[..., 0], out[..., 2])[ring] + 3).all()


def test_despill_nao_conecta_faixa_pelas_bordas_da_imagem():
    fg = np.zeros((8, 2, 3), dtype="float64")
    fg[:] = (20, 200, 30)
    alpha = np.ones((8, 2), dtype="float64")
    alpha[0, 0] = 0
    out = V._despill(fg, alpha, (0, 255, 0))
    assert np.array_equal(out[-1], fg[-1])


def test_symmetric_legs_ignores_wind_parts(data):
    _, scene = validate_data(data)
    key = fx.key_color(scene.data)
    img = Image.new("RGB", (320, 320), key)
    px = img.load()
    for y in range(20, 300):
        for x in range(110, 210):
            px[x, y] = (40, 90, 210)
    for y in range(60, 160):                      # capa só de um lado
        for x in range(210, 300):
            px[x, y] = (20, 35, 90)
    scene.data["verify"] = ["symmetric(vertical, 0.8)", "symmetric(vertical, 0.8, legs)"]
    res = {r.raw: r for r in V.run(scene, img)}
    assert not res["symmetric(vertical, 0.8)"].ok and res["symmetric(vertical, 0.8, legs)"].ok


def test_symmetric_legs_nao_recentra_pernas_assimetricas(data):
    _, scene = validate_data(data)
    key = fx.key_color(scene.data)
    img = Image.new("RGB", (40, 40), key)
    px = img.load()
    for y in range(5, 25):
        for x in range(15, 25):
            px[x, y] = (40, 90, 210)  # torso define o eixo x=20
    for y in range(25, 36):
        for x in range(15, 19):
            px[x, y] = (40, 90, 210)  # só uma perna, deslocada do eixo corporal
    scene.data["verify"] = ["symmetric(vertical, 0.8, legs)"]
    assert not V.run(scene, img)[0].ok


def test_sheet_metrics_and_cli(data, tmp_path, capsys):
    _, scene = validate_data(data)
    key = fx.key_color(scene.data)
    img = Image.new("RGB", (900, 300), key)
    px = img.load()
    for i, w in enumerate((40, 70, 100)):          # três variantes que crescem
        x0 = i * 300 + 100
        for y in range(60, 260):
            for x in range(x0, x0 + w):
                px[x, y] = (40, 90, 210)
    rows = V.sheet_metrics(scene, img, 3)
    assert [r["area"] for r in rows] == sorted(r["area"] for r in rows)
    path = tmp_path / "folha.png"
    img.save(path)
    assert main(["sheet-measure", str(EX / "pixel_heroi_planejada.yaml"), str(path), "--metric", "area"]) == 0
    assert main(["sheet-measure", str(EX / "pixel_heroi_planejada.yaml"), str(path), "--metric", "area", "--decreasing"]) == 1


def test_sheet_prompt(capsys):
    assert main(["sheet-prompt", str(EX / "pixel_heroi_planejada.yaml"), "--axis", "atmosphere.wind.strength=low,normal,high"]) == 0
    out = capsys.readouterr().out
    assert "FOLHA DE VARIANTES: desenhe 3 versões" in out and "3: atmosphere.wind.strength = high" in out
