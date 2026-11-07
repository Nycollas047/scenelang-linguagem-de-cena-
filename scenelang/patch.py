"""Patches (deltas) sobre a cena: alterar uma parte sem reescrever o resto.

Caminhos separados por ponto; entidades são endereçadas pelo `id`: `entities.sapo.box`, `style.mix.pixel`. Listas comuns usam
índice numérico (`asserts.0`). Operações:
  {"op": "set",     "path": "entities.sapo.box", "value": [..]}   cria ou troca
  {"op": "remove",  "path": "entities.sapo.signature"}            apaga a chave (ou a entidade, ou o item da lista)
  {"op": "add",     "path": "entities", "value": {id: ..., ...}}  acrescenta uma entidade (id novo)
  {"op": "append",  "path": "asserts", "value": "left_of(a, b)"}  acrescenta a uma lista
  {"op": "reorder", "path": "entities", "value": ["a", "b"]}      nova ordem de desenho
`diff(old, new)` gera o patch mínimo; `apply_patch(old, diff(old, new))` reconstrói `new` (equivalência canônica).
Erros viram `PatchError` com o caminho: nada é ignorado em silêncio.
"""
from __future__ import annotations

import copy

from . import canon


class PatchError(ValueError):
    pass


def _entity_index(lst: list, key: str, path: str) -> int:
    for i, e in enumerate(lst):
        if isinstance(e, dict) and str(e.get("id")) == key:
            return i
    raise PatchError(f"{path}: não há entidade com id {key!r}")


def _step(node, key: str, path: str, create: bool = False):
    if isinstance(node, dict):
        if key not in node:
            if not create:
                raise PatchError(f"{path}: a chave {key!r} não existe")
            node[key] = {}
        return node[key], key
    if isinstance(node, list):
        if key.isdigit() and int(key) < len(node):
            return node[int(key)], int(key)
        return node[_entity_index(node, key, path)], _entity_index(node, key, path)
    raise PatchError(f"{path}: não dá para entrar em {type(node).__name__}")


def _walk(data, parts: list[str], path: str, create: bool = False):
    node = data
    for i, k in enumerate(parts[:-1]):
        node, _ = _step(node, k, ".".join(parts[:i + 1]), create)
    return node


def apply_patch(data: dict, ops: list[dict]) -> dict:
    out = copy.deepcopy(data)
    for n, op in enumerate(ops):
        kind, path = op.get("op"), str(op.get("path", ""))
        where = f"op {n} ({kind} {path})"
        parts = [p for p in path.split(".") if p]
        if kind not in ("set", "remove", "add", "append", "reorder") or not parts:
            raise PatchError(f"{where}: operação ou caminho inválido")
        parent = _walk(out, parts, path, create=kind == "set")
        last = parts[-1]
        if kind == "set":
            if isinstance(parent, dict):
                parent[last] = copy.deepcopy(op["value"])
            elif isinstance(parent, list):
                idx = int(last) if last.isdigit() else _entity_index(parent, last, path)
                parent[idx] = copy.deepcopy(op["value"])
            else:
                raise PatchError(f"{where}: destino não é mapa nem lista")
        elif kind == "remove":
            if isinstance(parent, dict):
                if last not in parent:
                    raise PatchError(f"{where}: a chave {last!r} não existe")
                del parent[last]
            else:
                idx = int(last) if last.isdigit() else _entity_index(parent, last, path)
                del parent[idx]
        else:
            lst, _ = _step(parent, last, path)
            if not isinstance(lst, list):
                raise PatchError(f"{where}: o destino não é uma lista")
            if kind == "add":
                v = op["value"]
                if not isinstance(v, dict) or "id" not in v:
                    raise PatchError(f"{where}: `add` pede uma entidade com `id`")
                if any(isinstance(e, dict) and e.get("id") == v["id"] for e in lst):
                    raise PatchError(f"{where}: já existe uma entidade com id {v['id']!r}")
                lst.append(copy.deepcopy(v))
            elif kind == "append":
                lst.append(copy.deepcopy(op["value"]))
            else:
                ids = [str(e.get("id")) for e in lst if isinstance(e, dict)]
                if sorted(ids) != sorted(map(str, op["value"])):
                    raise PatchError(f"{where}: a nova ordem precisa ter exatamente os mesmos ids {ids}")
                by = {str(e.get("id")): e for e in lst}
                lst[:] = [by[str(i)] for i in op["value"]]
    return out


def _diff(old, new, path: str, ops: list) -> None:
    if canon.canonical(old) == canon.canonical(new):
        return
    if isinstance(old, dict) and isinstance(new, dict):
        for k in old:
            if k not in new:
                ops.append({"op": "remove", "path": f"{path}.{k}" if path else k})
        for k in new:
            sub = f"{path}.{k}" if path else k
            if k not in old:
                ops.append({"op": "set", "path": sub, "value": copy.deepcopy(new[k])})
            else:
                _diff(old[k], new[k], sub, ops)
        return
    ents = path.endswith("entities") or path == "entities"
    if ents and isinstance(old, list) and isinstance(new, list) and all(isinstance(e, dict) and "id" in e for e in old + new):
        oi, ni = {str(e["id"]): e for e in old}, {str(e["id"]): e for e in new}
        for i in oi:
            if i not in ni:
                ops.append({"op": "remove", "path": f"{path}.{i}"})
        for i, e in ni.items():
            if i not in oi:
                ops.append({"op": "add", "path": path, "value": copy.deepcopy(e)})
            else:
                _diff(oi[i], e, f"{path}.{i}", ops)
        expected = [i for i in oi if i in ni] + [i for i in ni if i not in oi]     # o que `remove` + `add` já produzem
        if list(ni) != expected:
            ops.append({"op": "reorder", "path": path, "value": list(ni)})
        return
    ops.append({"op": "set", "path": path, "value": copy.deepcopy(new)})


def diff(old: dict, new: dict) -> list[dict]:
    ops: list[dict] = []
    _diff(old, new, "", ops)
    return ops
