"""Ficha de avaliação e laço de correção.

O modelo que gera o texto não vê a imagem. Então cada `assert` vira uma pergunta
objetiva que uma pessoa (ou um modelo de visão) responde olhando a imagem gerada.
As respostas "não" viram reforço de prioridade na próxima compilação, o que
repete, de forma mecânica, o ajuste feito à mão entre os prompts 2 e 3.
"""
from __future__ import annotations

import copy

import yaml

from . import phrases as P
from . import vocab as V
from .assertions import parse_assert
from .model import Scene

YES = {"sim", "s", "yes", "y", "true", "ok", "1"}
NO = {"nao", "não", "n", "no", "false", "0"}

HINTS = {
    "facing": "repita a direção em frase visual (do ponto de vista de quem vê) na descrição da entidade",
    "above": "descreva a posição relativa com palavras e nomeie as duas partes na mesma frase",
    "below": "descreva a posição relativa com palavras e nomeie as duas partes na mesma frase",
    "left_of": "reforce esquerda/direita da tela e mova as caixas se o modelo ignorar",
    "right_of": "reforce esquerda/direita da tela e mova as caixas se o modelo ignorar",
    "near": "aproxime o elemento do ponto da grade e cite a região na descrição",
    "inside": "peça a hierarquia explicitamente: o pequeno 'sobre' o grande",
    "count": "escreva o número por extenso e dê um traço distintivo a cada item",
    "visible": "peça corpo inteiro e quadro aberto; rebaixe objetos que cortam o enquadramento",
    "brightest": "rebaixe brilho e saturação dos demais elementos na descrição deles",
    "focal_single": "mantenha brightness: max em um só elemento e rebaixe os outros",
}


def build_form(scene: Scene, rodada: int = 1) -> str:
    items = []
    for i, raw in enumerate(scene.data.get("asserts", []), 1):
        a = parse_assert(raw)
        items.append({"id": f"a{i}", "assert": raw, "pergunta": P.assert_texts(scene, a)[1], "ok": None, "tag": None})
    header = (
        f"# Ficha de avaliação — cena: {scene.name}\n"
        "# Olhe a imagem gerada e responda cada item com ok: sim ou ok: nao.\n"
        f"# Em caso de 'nao', escolha uma tag: {', '.join(V.REJECTION_TAGS)}.\n"
    )
    body = yaml.safe_dump({"cena": scene.name, "rodada": rodada, "itens": items}, allow_unicode=True, sort_keys=False)
    return header + body


def apply_answers(scene: Scene, answers_text: str, lock_passed: bool = False) -> tuple[dict, list[dict]]:
    """Retorna (cena atualizada como dicionário, relatório dos itens reprovados)."""
    form = yaml.safe_load(answers_text) or {}
    asserts = scene.data.get("asserts", [])
    new = copy.deepcopy(scene.data)
    boost = list(new.get("priority_boost", []))
    failed: list[dict] = []
    passed: list[str] = []
    unanswered = 0
    for item in form.get("itens", []):
        raw = item.get("assert")
        ok = item.get("ok")
        if raw not in asserts:
            raise ValueError(f"item da ficha não existe na cena: {raw!r}")
        if ok is None or str(ok).strip().lower() == "":
            unanswered += 1
            continue
        word = str(ok).strip().lower()
        if word in YES or ok is True:
            passed.append(raw)
            continue
        if word in NO or ok is False:
            tag = item.get("tag")
            if tag is not None and tag not in V.REJECTION_TAGS:
                raise ValueError(f"tag fora do vocabulário: {tag!r} (aceitas: {', '.join(V.REJECTION_TAGS)})")
            a = parse_assert(raw)
            failed.append({"assert": raw, "tag": tag, "dica": HINTS[a.name]})
            if raw not in boost:
                boost.append(raw)
            continue
        raise ValueError(f"resposta inválida em {raw!r}: {ok!r} (use sim ou nao)")
    if failed:
        new["priority_boost"] = boost
    if lock_passed:
        failed_raw = {f["assert"] for f in failed}
        locked = list(new.get("lock", []))
        for raw in passed:
            for arg in parse_assert(raw).args:
                name = arg.split(".")[0]
                if name in scene.by_id and name not in locked and raw not in failed_raw:
                    locked.append(name)
        # o que falhou não pode ficar travado
        failed_names = {arg.split(".")[0] for raw in failed_raw for arg in parse_assert(raw).args}
        locked = [n for n in locked if n not in failed_names]
        if locked:
            new["lock"] = locked
    hist = list(new.get("history", []))
    hist.append({"rodada": form.get("rodada", len(hist) + 1),
                 "reprovados": [f["assert"] for f in failed],
                 "tags": [f["tag"] for f in failed if f["tag"]],
                 "sem_resposta": unanswered})
    new["history"] = hist
    return new, failed


def dump_scene(data: dict) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100)
