"""Espaço de trabalho do projeto (`scenelang project`): onde cada tela mora, o que já foi medido e o que falta.

projeto/
├── projeto.yaml          índice: nome, objetivo, camadas e telas (o LLM lê este arquivo primeiro)
├── LEIA-ME-LLM.md        o ciclo de trabalho e as regras, em uma página
├── telas/<id>.yaml       uma cena por tela ou feature (a fonte de verdade)
├── refs/<id>/            imagens de referência geradas de cada tela
└── relatorios/<id>/rodada-NN/   relatório de medição, cena corrigida e prompt da próxima rodada

O estado (validada? asserts? rodadas? desatualizada?) é DERIVADO dos arquivos a cada `status`; nada é guardado em dobro,
então o índice não tem como mentir sobre o que existe em disco.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import yaml
from PIL import Image

INDEX = "projeto.yaml"
SLUG = re.compile(r"^[a-z][a-z0-9_]*$")
KEYS = {"projeto", "versao", "objetivo", "camadas", "telas"}
SCREEN_KEYS = {"id", "arquivo", "camada", "nota"}
LAYER_KEYS = {"id", "desc"}
DIRS = ("telas", "refs", "relatorios")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")
META_FORMAT = "scenelang.rodada/1"
DATASET_FORMAT = "scenelang.dataset/1"

STUB = """scene: "{title}"
canvas: {{ratio: "16:9"}}
style: "descreva o estilo visual"
intent:
  emotion: "descreva a emoção"
  story: "descreva o que acontece"
  focal: {focal}
entities:
  - id: {focal}
    kind: prop
    label: o elemento principal
    desc: descreva o elemento principal
    plane: midground
    box: [0.35, 0.3, 0.3, 0.4]
    brightness: max
"""

READ_ME = """# Como trabalhar neste projeto (para o LLM)

1. Leia `projeto.yaml`: ele lista as telas, as camadas e onde cada uma mora.
2. Rode `scenelang project status .` e comece pelo "próximo passo" da primeira tela que não está em dia.
3. A **fonte de verdade é o YAML** em `telas/`. As imagens em `refs/` são referência e podem divergir dele.

## Ciclo de uma tela
1. Escreva ou edite `telas/<id>.yaml`.
2. `scenelang validate telas/<id>.yaml` e `scenelang check telas/<id>.yaml` (sem imagem).
3. `scenelang pack telas/<id>.yaml --out-dir <pasta>` gera o prompt e o guia; a pessoa gera a imagem.
4. `scenelang project round . <id> <imagem> [--boxes caixas.json]` mede, guarda a rodada e prepara o prompt seguinte.
5. Repita até os asserts passarem ou até medir que o gerador não obedece (isso também é resultado).

## Regras
- Não afirme que algo funciona sem ter medido; diga o que foi medido e o que não foi.
- Não repita no YAML o que já está num componente ou noutra tela: referencie.
- Uma rodada nova só depois de mudar a cena ou o prompt; sem mudança, não há o que medir de novo.
- Registre o que falhou. Falha medida é dado, não erro a esconder.
"""


class ProjectError(Exception):
    pass


def _read_index(root: Path) -> dict:
    p = root / INDEX
    if not p.is_file():
        raise ProjectError(f"não achei {INDEX} em {root}; rode `scenelang project init {root}`")
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ProjectError(f"{INDEX} não é YAML válido: {e}") from e
    if not isinstance(data, dict):
        raise ProjectError(f"{INDEX} deve ser um mapa")
    return data


def _write_index(root: Path, data: dict) -> None:
    (root / INDEX).write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False), encoding="utf-8")


def init(root: str | Path, name: str | None = None, goal: str = "") -> list[Path]:
    root = Path(root)
    if (root / INDEX).exists():
        raise ProjectError(f"{root / INDEX} já existe; não sobrescrevo um projeto")
    root.mkdir(parents=True, exist_ok=True)
    made = []
    for d in DIRS:
        (root / d).mkdir(exist_ok=True)
        (root / d / ".gitkeep").touch()
        made.append(root / d)
    data = {"projeto": name or root.resolve().name, "versao": 1, "objetivo": goal or "descreva o objetivo do projeto",
            "camadas": [], "telas": []}
    _write_index(root, data)
    (root / "LEIA-ME-LLM.md").write_text(READ_ME, encoding="utf-8")
    return [root / INDEX, root / "LEIA-ME-LLM.md", *made]


def add_screen(root: str | Path, sid: str, layer: str | None = None, note: str = "") -> Path:
    root = Path(root)
    data = _read_index(root)
    if not SLUG.match(sid):
        raise ProjectError(f"id de tela inválido: {sid!r} (minúsculas, dígitos e _, começando por letra)")
    telas = data.setdefault("telas", []) or []
    if any(isinstance(t, dict) and t.get("id") == sid for t in telas):
        raise ProjectError(f"a tela {sid!r} já está no índice")
    path = root / "telas" / f"{sid}.yaml"
    if path.exists():
        raise ProjectError(f"{path} já existe; registre-o à mão no índice ou escolha outro id")
    if layer is not None and layer not in {c.get("id") for c in data.get("camadas") or [] if isinstance(c, dict)}:
        raise ProjectError(f"camada desconhecida: {layer!r}; declare-a antes (`project layer`)")
    (root / "telas").mkdir(exist_ok=True)
    path.write_text(STUB.format(title=sid.replace("_", " "), focal="principal"), encoding="utf-8")
    entry = {"id": sid, "arquivo": f"telas/{sid}.yaml"}
    if layer:
        entry["camada"] = layer
    if note:
        entry["nota"] = note
    telas.append(entry)
    data["telas"] = telas
    _write_index(root, data)
    return path


def add_layer(root: str | Path, lid: str, desc: str = "") -> None:
    root = Path(root)
    data = _read_index(root)
    if not SLUG.match(lid):
        raise ProjectError(f"id de camada inválido: {lid!r}")
    camadas = data.get("camadas") or []
    if any(isinstance(c, dict) and c.get("id") == lid for c in camadas):
        raise ProjectError(f"a camada {lid!r} já existe")
    camadas.append({"id": lid, "desc": desc} if desc else {"id": lid})
    data["camadas"] = camadas
    _write_index(root, data)


def _rounds(root: Path, sid: str) -> list[Path]:
    base = root / "relatorios" / sid
    return sorted(p for p in base.glob("rodada-*") if p.is_dir()) if base.is_dir() else []


def _last_report(rounds: list[Path]) -> dict | None:
    import json

    for r in reversed(rounds):
        f = r / "relatorio.json"
        if f.is_file():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                return None
    return None


def index_problems(data: dict, root: Path) -> list[str]:
    """Problemas do próprio índice (formato, duplicatas, referências soltas)."""
    out: list[str] = []
    for k in data:
        if k not in KEYS:
            out.append(f"campo desconhecido no índice: {k!r}")
    layers = data.get("camadas") or []
    telas = data.get("telas") or []
    if not isinstance(layers, list) or not isinstance(telas, list):
        return out + ["`camadas` e `telas` devem ser listas"]
    lids = []
    for i, c in enumerate(layers):
        if not isinstance(c, dict) or not isinstance(c.get("id"), str) or not SLUG.match(c["id"]):
            out.append(f"camadas[{i}]: precisa de `id` em minúsculas")
            continue
        if c["id"] in lids:
            out.append(f"camada repetida: {c['id']!r}")
        lids.append(c["id"])
        out += [f"camadas[{i}]: campo desconhecido {k!r}" for k in c if k not in LAYER_KEYS]
    seen, files = [], set()
    for i, t in enumerate(telas):
        if not isinstance(t, dict) or not isinstance(t.get("id"), str) or not SLUG.match(t["id"]):
            out.append(f"telas[{i}]: precisa de `id` em minúsculas")
            continue
        if t["id"] in seen:
            out.append(f"tela repetida: {t['id']!r}")
        seen.append(t["id"])
        out += [f"telas[{i}]: campo desconhecido {k!r}" for k in t if k not in SCREEN_KEYS]
        if t.get("camada") is not None and t["camada"] not in lids:
            out.append(f"tela {t['id']!r}: camada desconhecida {t['camada']!r}")
        files.add(str(Path(t.get("arquivo") or f"telas/{t['id']}.yaml")))
    for p in sorted((root / "telas").glob("*.yaml")) if (root / "telas").is_dir() else []:
        if str(p.relative_to(root)) not in files:
            out.append(f"{p.relative_to(root)} está em telas/ mas não está no índice")
    return out


def screen_status(root: Path, t: dict) -> dict:
    from . import api

    sid = t["id"]
    rel = Path(t.get("arquivo") or f"telas/{sid}.yaml")
    path = root / rel
    st: dict = {"id": sid, "camada": t.get("camada"), "arquivo": str(rel), "existe": path.is_file()}
    rounds = _rounds(root, sid)
    refs = [p for p in (root / "refs" / sid).glob("*") if p.suffix.lower() in IMAGE_EXT] if (root / "refs" / sid).is_dir() else []
    st.update(rodadas=len(rounds), refs=len(refs))
    if not path.is_file():
        st.update(valida=False, proximo=f"criar {rel} (ou remover a tela do índice)")
        return st
    text = path.read_text(encoding="utf-8")
    v = api.validate(text)
    st.update(valida=v["ok"], erros=len(v["errors"]), avisos=len(v["warnings"]))
    if not v["ok"]:
        first = v["errors"][0] if v["errors"] else {}
        st["proximo"] = f"corrigir a validação: {first.get('path', '$')} {first.get('message', '')}".strip()
        return st
    c = api.check_layout(text)
    asserts = c.get("asserts") or []
    st.update(asserts=len(asserts), asserts_ok=sum(1 for a in asserts if a["ok"]))
    rep = _last_report(rounds)
    if rep:
        med = rep.get("medicoes") or []
        st.update(medicoes=len(med), medicoes_ok=sum(1 for m in med if m.get("ok")),
                  nao_medidos=len((rep.get("nao_medidos") or {}).get("asserts") or []))
        # desatualizada = a cena de hoje não é a que foi medida (hash canônico: ignora data de arquivo e formatação)
        from . import canon

        scene, _err = api._scene(text)
        old = rep.get("hash_cena_completo")
        st["desatualizada"] = bool(old and scene is not None and canon.scene_hash(scene.data) != old)
    if asserts and st["asserts_ok"] < st["asserts"]:
        st["proximo"] = f"{st['asserts'] - st['asserts_ok']} assert(s) falham no layout: rode `scenelang check {rel}`"
    elif not refs and not rounds:
        st["proximo"] = f"gerar a imagem (`scenelang pack {rel} --out-dir ...`) e guardá-la com `project round`"
    elif rep is None:
        st["proximo"] = "medir a imagem de referência com `project round`"
    elif st.get("desatualizada"):
        st["proximo"] = "a cena mudou depois da última medição: gerar nova imagem e medir de novo"
    elif st.get("medicoes_ok", 0) < st.get("medicoes", 0):
        st["proximo"] = "aplicar as correções do prompt_next.txt da última rodada e gerar de novo"
    elif st.get("nao_medidos"):
        st["proximo"] = (f"o medido passa, mas {st['nao_medidos']} assert(s) ficaram sem medir: "
                         "informe `--boxes` para quem falta ou declare `signature`/`verify` na cena")
    else:
        st["proximo"] = "em dia"
    return st


def status(root: str | Path) -> dict:
    root = Path(root)
    data = _read_index(root)
    problems = index_problems(data, root)
    telas = [t for t in (data.get("telas") or []) if isinstance(t, dict) and isinstance(t.get("id"), str)] if isinstance(data.get("telas"), list) else []
    shown, seen = [], set()
    for t in telas:
        if t["id"] in seen:
            continue
        seen.add(t["id"])
        shown.append(screen_status(root, t))
    em_dia = bool(shown) and not problems and all(s.get("proximo") == "em dia" for s in shown)
    return {"projeto": data.get("projeto"), "objetivo": data.get("objetivo"), "problemas": problems, "telas": shown, "em_dia": em_dia}


def record_round(root: str | Path, sid: str, image: str | Path, boxes: dict | None = None, label: str | None = None,
                 prompt_file: str | Path | None = None, generator: str | None = None,
                 arm: str | None = None, seed: int | None = None, annotation: str | Path | None = None) -> dict:
    """Mede a imagem de uma tela e guarda tudo: cópia em refs/, relatório e prompt seguinte em relatorios/."""
    from . import api

    root = Path(root)
    data = _read_index(root)
    tela = next((t for t in data.get("telas") or [] if isinstance(t, dict) and t.get("id") == sid), None)
    if tela is None:
        raise ProjectError(f"tela desconhecida: {sid!r}")
    scene_path = root / (tela.get("arquivo") or f"telas/{sid}.yaml")
    if not scene_path.is_file():
        raise ProjectError(f"não achei {scene_path}")
    image = Path(image)
    if not image.is_file():
        raise ProjectError(f"não achei a imagem {image}")
    if prompt_file is not None and not Path(prompt_file).is_file():      # antes de medir: não deixar rodada pela metade
        raise ProjectError(f"não achei o arquivo de prompt {prompt_file}")
    recon, boxes_da_anotacao = None, False
    if annotation is not None:      # medição independente: o anotador descreveu a imagem sem ver a cena
        import json as _json

        from . import reconcile as RC
        from .validate import load_text as _lt
        try:
            raw = _json.loads(Path(annotation).read_text(encoding="utf-8"))
            sc = _lt(scene_path.read_text(encoding="utf-8"))[1]
            if sc is None:
                raise ProjectError("a cena da tela tem erros; corrija antes de reconciliar")
            recon = RC.reconcile(sc, raw)
        except (OSError, ValueError) as e:       # ReconcileError e JSON inválido são ValueError
            raise ProjectError(f"anotação inválida: {e}") from e
        if boxes is None:
            if not recon["caixas"]:
                raise ProjectError("anotação inválida: nenhum objeto anotado casou com as entidades da cena (nomes sem palavra em comum); "
                                   "confira os nomes ou passe --boxes")
            boxes, boxes_da_anotacao = {k: v for k, v in recon["caixas"].items()}, True
    n = len(_rounds(root, sid)) + 1
    out = root / "relatorios" / sid / f"rodada-{n:02d}"
    res = api.correct_round(scene_path.read_text(encoding="utf-8"), str(image), str(out), boxes)
    if not res.get("ok") and "findings" not in res:
        if out.is_dir() and not any(out.iterdir()):
            out.rmdir()
        raise ProjectError("não consegui medir: " + "; ".join(e.get("message", str(e)) for e in res.get("errors", [])))
    refs = root / "refs" / sid
    refs.mkdir(parents=True, exist_ok=True)
    tag = f"-{re.sub(r'[^a-z0-9_]+', '_', label.lower())}" if label else ""
    dest = refs / f"rodada-{n:02d}{tag}{image.suffix.lower()}"
    shutil.copyfile(image, dest)
    # o que foi medido fica autocontido: a cena e o prompt DAQUELA rodada, a imagem (com hash) e de onde vieram as caixas
    import hashlib
    import json

    text = scene_path.read_text(encoding="utf-8")
    (out / "cena.yaml").write_text(text, encoding="utf-8")
    if prompt_file is not None:
        pf = Path(prompt_file)
        if not pf.is_file():
            raise ProjectError(f"não achei o arquivo de prompt {pf}")
        prompt, origem = pf.read_text(encoding="utf-8"), "informado"
    else:                       # sem o prompt real, grava o compilado e DIZ que é suposição
        prompt, origem = api.compile_scene(text, "prose").get("output", ""), "compilado_da_cena_assumido"
    (out / "prompt.txt").write_text(prompt, encoding="utf-8")
    if boxes:
        (out / "caixas.json").write_text(json.dumps(boxes, ensure_ascii=False, indent=2), encoding="utf-8")
    if recon is not None:
        (out / "reconciliacao.json").write_text(json.dumps(recon, ensure_ascii=False, indent=2), encoding="utf-8")
    with Image.open(image) as im:
        size = list(im.size)
    (out / "rodada.json").write_text(json.dumps({
        "formato": META_FORMAT, "tela": sid, "rodada": n, "rotulo": label,
        "imagem": str(dest.relative_to(root)), "imagem_sha256": hashlib.sha256(image.read_bytes()).hexdigest(), "imagem_tamanho": size,
        "caixas": "anotacao_independente" if boxes_da_anotacao else ("informadas" if boxes else "nenhuma"),
        "prompt_origem": origem, "gerador": generator, "braco": arm, "seed": seed,
        "anotador": recon["anotador"] if recon else None, "anotacao_cega": recon["cego"] if recon else None}, ensure_ascii=False, indent=2), encoding="utf-8")
    res["rodada"] = n
    if recon is not None:
        res["reconciliacao"] = recon
    res["imagem_guardada"] = str(dest)
    res["pasta"] = str(out)
    return res


def export_dataset(root: str | Path) -> tuple[list[dict], list[str]]:
    """Um registro autocontido por rodada medida: cena, prompt, imagem (hash), medições, correções e o prompt seguinte.

    Rodadas sem `rodada.json` (feitas antes desta versão) são puladas e listadas em `avisos`.
    """
    import json

    root = Path(root)
    data = _read_index(root)
    records, warns = [], []
    for t in data.get("telas") or []:
        if not isinstance(t, dict) or not isinstance(t.get("id"), str):
            continue
        sid = t["id"]
        for r in _rounds(root, sid):
            meta_f, rep_f = r / "rodada.json", r / "relatorio.json"
            if not (meta_f.is_file() and rep_f.is_file()):
                warns.append(f"{r.relative_to(root)}: sem rodada.json/relatorio.json (rodada antiga ou incompleta); pulada")
                continue
            meta, rep = json.loads(meta_f.read_text(encoding="utf-8")), json.loads(rep_f.read_text(encoding="utf-8"))
            nxt = r / "prompt_next.txt"
            records.append({
                "formato": DATASET_FORMAT, "projeto": data.get("projeto"), "tela": sid, "camada": t.get("camada"),
                "rodada": meta["rodada"], "rotulo": meta.get("rotulo"), "gerador": meta.get("gerador"),
                "braco": meta.get("braco"), "seed": meta.get("seed"),
                "cena_hash": rep.get("hash_cena_completo"), "cena_yaml": (r / "cena.yaml").read_text(encoding="utf-8"),
                "prompt": (r / "prompt.txt").read_text(encoding="utf-8"), "prompt_origem": meta.get("prompt_origem", "desconhecida"),
                "imagem": {"caminho": meta["imagem"], "sha256": meta["imagem_sha256"], "tamanho": meta["imagem_tamanho"]},
                "anotacao": {"caixas": meta.get("caixas"), "anotador": meta.get("anotador"), "cego": meta.get("anotacao_cega"),
                             "observacao": "caixas 'informadas' vêm de quem olhou a imagem (pode conhecer a cena); 'anotacao_independente' vêm de uma anotação feita sem a cena; nenhuma é de um detector"},
                "reconciliacao": json.loads((r / "reconciliacao.json").read_text(encoding="utf-8")) if (r / "reconciliacao.json").is_file() else None,
                "medicoes": [{k: m.get(k) for k in ("check", "ok", "detail", "source", "confidence", "classe")} for m in rep.get("medicoes") or []],
                "nao_medidos": rep.get("nao_medidos"),
                "correcoes": rep.get("correcoes"),
                "prompt_seguinte": nxt.read_text(encoding="utf-8") if nxt.is_file() else None,
            })
    return records, warns


MIN_N = 5


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalo de Wilson para uma proporção k/n (n pequeno é o caso normal aqui; o intervalo mostra o quanto isso vale)."""
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (max(0.0, c - h), min(1.0, c + h))


def report(root: str | Path, sid: str) -> dict:
    """Por restrição e por braço: em quantas rodadas passou (k de n), com intervalo de Wilson. Uma imagem por braço não mede variação."""
    import json

    root = Path(root)
    data = _read_index(root)
    if not any(isinstance(t, dict) and t.get("id") == sid for t in data.get("telas") or []):
        raise ProjectError(f"tela desconhecida: {sid!r}")
    arms: dict[str, dict] = {}
    for r in _rounds(root, sid):
        meta_f, rep_f = r / "rodada.json", r / "relatorio.json"
        if not (meta_f.is_file() and rep_f.is_file()):
            continue
        meta, rep = json.loads(meta_f.read_text(encoding="utf-8")), json.loads(rep_f.read_text(encoding="utf-8"))
        arm = meta.get("braco") or "(sem braço)"
        a = arms.setdefault(arm, {"rodadas": 0, "seeds": [], "restricoes": {}})
        a["rodadas"] += 1
        a["seeds"].append(meta.get("seed"))
        seen = set()
        items = [(m.get("check"), m.get("ok")) for m in rep.get("medicoes") or []]
        rf = r / "reconciliacao.json"
        if rf.is_file():
            items += [("[anotação] " + x["raw"], x["ok"]) for x in json.loads(rf.read_text(encoding="utf-8")).get("asserts") or []]
        for check, ok in items:
            if check is None or ok not in (True, False) or check in seen:
                continue
            seen.add(check)
            c = a["restricoes"].setdefault(check, {"k": 0, "n": 0})
            c["n"] += 1
            c["k"] += 1 if ok else 0
    for a in arms.values():
        for c in a["restricoes"].values():
            lo, hi = wilson(c["k"], c["n"])
            c["taxa"], c["ic95"] = round(c["k"] / c["n"], 3), [round(lo, 3), round(hi, 3)]
            c["n_insuficiente"] = c["n"] < MIN_N
        a["repetido"] = a["rodadas"] > 1
    return {"tela": sid, "min_n": MIN_N, "bracos": arms}


def report_text(rep: dict) -> str:
    lines = [f"tela {rep['tela']}: restrição passou em k de n rodadas, por braço (IC 95% de Wilson)"]
    if not rep["bracos"]:
        return lines[0] + "\n(nenhuma rodada medida)"
    for arm, a in sorted(rep["bracos"].items()):
        lines.append(f"\n[{arm}] {a['rodadas']} rodada(s)" + ("" if a["repetido"] else "  · UMA rodada: não mede variação"))
        for check, c in a["restricoes"].items():
            flag = "  (n pequeno: não conclua)" if c["n_insuficiente"] else ""
            lines.append(f"  {c['k']}/{c['n']}  IC [{c['ic95'][0]:.2f}, {c['ic95'][1]:.2f}]  {check}{flag}")
    return "\n".join(lines)
