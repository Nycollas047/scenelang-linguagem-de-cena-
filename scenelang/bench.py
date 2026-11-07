"""Estrutura de benchmark: SceneLang × prompt convencional.

Este módulo NÃO chama nenhum gerador de imagem. Ele faz o que se mede offline (tokens de entrada estimados, tempo de
compilação, fidelidade declarada) e guarda, execução a execução, o que só existe depois de gerar (tokens de saída,
chamadas, tentativas, custo, imagem). Campo não informado fica `null` e aparece como «—» no relatório: nada é inventado.

Modos comparados:
  convencional  prompt escrito à mão (`--baseline`); sem ele, uma linearização SINTÉTICA da cena, marcada como tal
  completa      SceneLang compilada em prosa (com prioridades e reforços)
  compacta      SceneLang compilada em `compact` (menos tokens, perdas declaradas)
  incremental   só o que mudou da cena anterior (`--previous`); exige a imagem anterior como entrada do gerador
  com_guia      prosa + guia de composição em imagem (os tokens da imagem dependem do modelo e não entram na estimativa)

Taxa de sucesso das restrições = fração das medições de confiança ≥ 0,6 (verificadores em pixels, asserts e espelhamento
com caixas informadas) que passaram. Medição só por cor de assinatura (confiança 0,5) NÃO conta.
Contagem de tokens: `tiktoken` (o200k_base) se estiver instalado; senão ⌈caracteres ÷ 3,5⌉, uma estimativa.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

from . import canon
from . import compile as CP
from . import loss as LS

MODES = ("convencional", "completa", "compacta", "incremental", "com_guia")
MIN_CONFIDENCE = 0.6


def count_tokens(text: str) -> dict:
    try:
        import tiktoken
        return {"tokens": len(tiktoken.get_encoding("o200k_base").encode(text)), "method": "tiktoken:o200k_base"}
    except Exception:       # tiktoken ausente ou sem acesso ao vocabulário: a estimativa por caracteres é declarada
        return {"tokens": math.ceil(len(text) / 3.5), "method": "estimativa: ⌈caracteres ÷ 3,5⌉"}


def synthetic_baseline(scene) -> str:
    """Linearização ingênua (estilo + história + `desc` de cada entidade). NÃO é um prompt escrito por uma pessoa."""
    d = scene.data
    bits = [str(d["style"] if isinstance(d["style"], str) else d["style"].get("base", ""))]
    story = (d.get("intent") or {}).get("story")
    if story:
        bits.append(story)
    bits += [e.desc.rstrip(".") for e in scene.entities]
    return ", ".join(b for b in bits if b) + "."


def plan(scene_text: str, out_dir: str | Path, baseline: str | None = None, previous_text: str | None = None) -> dict:
    """Grava os prompts de cada modo e as métricas offline em `plano.json`; cria `execucoes.jsonl` vazio."""
    from .validate import load_text

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    diags, scene, _ = load_text(scene_text)
    if scene is None:
        raise ValueError("cena inválida: " + "; ".join(str(d) for d in diags if d.level == "error")[:300])
    modes: dict[str, dict] = {}

    def add(name: str, builder, backend: str | None = None, extra: dict | None = None):
        t0 = time.perf_counter()
        text = builder()
        ms = (time.perf_counter() - t0) * 1000
        (out / f"prompt_{name}.txt").write_text(text, encoding="utf-8")
        row = {"arquivo": f"prompt_{name}.txt", "caracteres": len(text), **{f"entrada_{k}": v for k, v in count_tokens(text).items()},
               "tempo_compilacao_ms": round(ms, 3), "disponivel": True}
        if backend:
            items = LS.report(scene, backend)
            row["fidelidade_declarada"] = LS.fidelity(items)
            row["perdas"] = LS.summary(items)
        row.update(extra or {})
        modes[name] = row

    add("convencional", lambda: baseline if baseline is not None else synthetic_baseline(scene),
        extra={"baseline_sintetica": baseline is None,
               "aviso": "linearização automática, não um prompt humano: substitua com --baseline para uma comparação honesta" if baseline is None else ""})
    add("completa", lambda: CP.to_prose(scene), "prose")
    add("compacta", lambda: CP.to_compact(scene), "compact")
    if previous_text:
        pd, prev, _ = load_text(previous_text)
        if prev is None:
            raise ValueError("cena anterior inválida")
        add("incremental", lambda: CP.delta_prompt(prev, scene), "prose",
            extra={"exige": "imagem anterior como entrada do gerador", "nada_mudou": canon.scene_hash(prev.data) == canon.scene_hash(scene.data)})
    else:
        modes["incremental"] = {"disponivel": False, "motivo": "sem --previous (cena da rodada anterior)"}
    add("com_guia", lambda: CP.to_prose(scene), "prose",
        extra={"imagem_de_entrada": True, "aviso": "o guia (`scenelang pack`) vai como imagem; os tokens dela dependem do modelo e não estão na estimativa"})
    doc = {"cena": scene.name, "hash_cena": canon.scene_hash(scene.data), "modos": modes,
           "pendente_de_avaliacao_externa": ["tokens de saída", "número de chamadas", "tentativas até satisfazer as restrições", "custo",
                                             "taxa de sucesso das restrições (precisa da imagem gerada)", "correções necessárias"]}
    (out / "plano.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "execucoes.jsonl").touch()
    return doc


def record(out_dir: str | Path, mode: str, run_id: str, scene_text: str | None = None, image: str | None = None, boxes: dict | None = None,
           tokens_out: int | None = None, calls: int | None = None, attempts: int | None = None, cost_usd: float | None = None,
           latency_s: float | None = None, corrections: int | None = None, notes: str = "") -> dict:
    """Registra UMA geração. Com `scene_text` e `image`, mede as restrições em código (sem juiz subjetivo)."""
    if mode not in MODES:
        raise ValueError(f"modo desconhecido: {mode!r} (use {', '.join(MODES)})")
    rec: dict = {"modo": mode, "execucao": run_id, "tokens_saida": tokens_out, "chamadas": calls, "tentativas": attempts, "custo_usd": cost_usd,
                 "latencia_s": latency_s, "correcoes": corrections, "notas": notes, "imagem": image, "restricoes": None}
    if image and scene_text:
        from PIL import Image

        from . import correct as CR
        from .validate import load_text

        _, scene, _ = load_text(scene_text)
        if scene is None:
            raise ValueError("cena inválida")
        m = CR.measure_full(scene, Image.open(image), boxes)
        usable = [f for f in m.findings if f.confidence >= MIN_CONFIDENCE]
        rec["restricoes"] = {"medidas": len(usable), "ok": sum(f.ok for f in usable), "desconsideradas_por_confianca": len(m.findings) - len(usable),
                             "taxa": round(sum(f.ok for f in usable) / len(usable), 4) if usable else None,
                             "falhas": [f.check for f in usable if not f.ok]}
        if corrections is None:
            pl = CR.plan_round(scene, m.findings, m.items)
            rec["correcoes"] = len(pl.applied)
            rec["correcoes_origem"] = "plano de correção calculado pelo scenelang (não foi aplicado a um gerador)"
    with open(Path(out_dir) / "execucoes.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def _mean(vals):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def report(out_dir: str | Path, price_in: float | None = None, price_out: float | None = None) -> dict:
    """Agrega por modo. Preços (USD por 1 milhão de tokens) só entram se forem informados; custo medido (`custo_usd`) tem preferência."""
    out = Path(out_dir)
    plan_ = json.loads((out / "plano.json").read_text(encoding="utf-8"))
    runs = [json.loads(line) for line in (out / "execucoes.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = {}
    for mode in MODES:
        pm = plan_["modos"].get(mode, {})
        rs = [r for r in runs if r["modo"] == mode]
        tin = pm.get("entrada_tokens")
        cost = []
        for r in rs:
            if r.get("custo_usd") is not None:
                cost.append(r["custo_usd"])
            elif price_in is not None and tin is not None and (price_out is None or r.get("tokens_saida") is not None):
                cost.append((tin * price_in + (r.get("tokens_saida") or 0) * (price_out or 0)) / 1e6)
        taxas = [r["restricoes"]["taxa"] for r in rs if r.get("restricoes") and r["restricoes"]["taxa"] is not None]
        rows[mode] = {"disponivel": pm.get("disponivel", False), "tokens_entrada": tin, "metodo_tokens": pm.get("entrada_method"),
                      "tempo_compilacao_ms": pm.get("tempo_compilacao_ms"), "fidelidade_declarada": pm.get("fidelidade_declarada"),
                      "execucoes": len(rs), "tokens_saida_medio": _mean([r["tokens_saida"] for r in rs]), "chamadas_medias": _mean([r["chamadas"] for r in rs]),
                      "tentativas_medias": _mean([r["tentativas"] for r in rs]), "custo_medio_usd": _mean(cost),
                      "taxa_sucesso_media": _mean(taxas), "correcoes_medias": _mean([r["correcoes"] for r in rs]),
                      "baseline_sintetica": pm.get("baseline_sintetica")}
    base = rows["convencional"]["tokens_entrada"]
    for mode, r in rows.items():
        r["tokens_entrada_vs_convencional"] = round(r["tokens_entrada"] / base, 3) if base and r["tokens_entrada"] else None
    return {"cena": plan_["cena"], "modos": rows, "execucoes_totais": len(runs),
            "pendente_de_avaliacao_externa": plan_["pendente_de_avaliacao_externa"]}


def markdown(rep: dict) -> str:
    def f(v, fmt="{}"):
        return "—" if v is None else fmt.format(v)
    lines = [f"# Benchmark — {rep['cena']}", "", "| modo | tokens entrada | vs convencional | fidelidade declarada | execuções | tentativas | chamadas | taxa de sucesso | custo médio (USD) |",
             "|---|---|---|---|---|---|---|---|---|"]
    for m, r in rep["modos"].items():
        if not r["disponivel"]:
            lines.append(f"| {m} | — | — | — | — | — | — | — | — |")
            continue
        lines.append(f"| {m}{' (sintético)' if r['baseline_sintetica'] else ''} | {f(r['tokens_entrada'])} | {f(r['tokens_entrada_vs_convencional'], '{:.2f}×')} | {f(r['fidelidade_declarada'])} | "
                     f"{r['execucoes']} | {f(r['tentativas_medias'])} | {f(r['chamadas_medias'])} | {f(r['taxa_sucesso_media'], '{:.0%}')} | {f(r['custo_medio_usd'], '{:.4f}')} |")
    lines += ["", "«—» = não medido. Ainda depende de avaliação externa: " + "; ".join(rep["pendente_de_avaliacao_externa"]) + "."]
    return "\n".join(lines) + "\n"
