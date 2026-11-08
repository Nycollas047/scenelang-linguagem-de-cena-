"""Herança (extends), bibliotecas (import) e varreduras (sweep) de cenas.

extends: base.yaml      # herda tudo; o que a cena define sobrescreve (dicionários se mesclam,
                        # listas se substituem, `entities` se mescla por id, `null` apaga uma chave,
                        # e uma entidade com `remove: true` é retirada)
import: [materiais.yaml]   # traz `materials` e `colors` de bibliotecas (a cena vence em conflito)
"""
from __future__ import annotations

import copy
import itertools
from pathlib import Path

import yaml

IMPORTABLE = ("materials", "colors")


class VariantError(ValueError):
    pass


def _merge_entities(base: list, over: list) -> list:
    out = [copy.deepcopy(e) for e in base]
    index = {e.get("id"): i for i, e in enumerate(out) if isinstance(e, dict)}
    for e in over:
        if not isinstance(e, dict):
            out.append(e)
            continue
        i = index.get(e.get("id"))
        if e.get("remove") is True:
            if i is not None:
                out[i] = None
            continue
        if i is None:
            index[e.get("id")] = len(out)
            out.append(copy.deepcopy(e))
        else:
            out[i] = merge(out[i], e)
    return [e for e in out if e is not None]


def merge(base, over):
    """Mescla `over` sobre `base` (ver regras no topo do módulo)."""
    if isinstance(base, dict) and isinstance(over, dict):
        out = {k: copy.deepcopy(v) for k, v in base.items()}
        for k, v in over.items():
            if v is None:
                out.pop(k, None)
            elif k == "entities" and isinstance(out.get(k), list) and isinstance(v, list):
                out[k] = _merge_entities(out[k], v)
            elif k in out:
                out[k] = merge(out[k], v)
            else:
                out[k] = copy.deepcopy(v)
        return out
    return copy.deepcopy(over)


def _read(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise VariantError(f"não consegui abrir {path}: {e.strerror or e}") from e
    except yaml.YAMLError as e:
        raise VariantError(f"YAML inválido em {path}: {e}") from e
    if not isinstance(data, dict):
        raise VariantError(f"{path} deve conter um mapa")
    return data


def resolve(data, base_dir: Path | None, _seen: tuple = ()):
    """Resolve extends/import. Devolve a cena autocontida (sem essas duas chaves)."""
    if not isinstance(data, dict) or ("extends" not in data and "import" not in data):
        return data
    root = Path(base_dir) if base_dir else Path(".")
    data = copy.deepcopy(data)
    ext = data.pop("extends", None)
    imports = data.pop("import", None)
    result: dict = {}
    if ext is not None:
        if not isinstance(ext, str):
            raise VariantError("extends deve ser o caminho de um arquivo")
        path = (root / ext).resolve()
        if path in _seen:
            chain = _seen + (path,)
            start = chain.index(path)
            raise VariantError("extends em ciclo: " + " -> ".join(p.name for p in chain[start:]))
        base = resolve(_read(path), path.parent, _seen + (path,))
        result = merge(base, data)
    else:
        result = data
    if imports is not None:
        if not isinstance(imports, list) or not all(isinstance(x, str) for x in imports):
            raise VariantError("import deve ser uma lista de caminhos")
        for rel in imports:
            lib = _read((root / rel).resolve())
            for key in IMPORTABLE:
                if key in lib:
                    result[key] = merge(lib[key], result.get(key, {}))   # a cena vence
    return result


# ---------------------------------------------------------------------------
def set_path(data: dict, dotted: str, value) -> None:
    """Define data[a][b]... = value. Em listas, o segmento é o `id` do item (ou um índice)."""
    cur = data
    segs = dotted.split(".")
    for i, seg in enumerate(segs):
        last = i == len(segs) - 1
        if isinstance(cur, list):
            item = next((x for x in cur if isinstance(x, dict) and x.get("id") == seg), None)
            if item is None and seg.isdigit() and int(seg) < len(cur):
                item = cur[int(seg)]
            if item is None:
                raise VariantError(f"caminho inexistente: não há item {seg!r} em {'.'.join(segs[:i]) or 'raiz'}")
            if last:
                raise VariantError("o caminho termina num item de lista; aponte para um campo dele")
            cur = item
        elif isinstance(cur, dict):
            if last:
                cur[seg] = value
                return
            if seg not in cur:
                if i == len(segs) - 2:
                    cur[seg] = {}
                else:
                    raise VariantError(f"caminho inexistente: {'.'.join(segs[:i + 1])}")
            cur = cur[seg]
        else:
            raise VariantError(f"não dá para entrar em {'.'.join(segs[:i])}: não é um mapa nem lista")


def make_sweep(data: dict, axis: str) -> tuple[str, list[tuple[str, dict]]]:
    """axis = 'caminho=v1,v2,v3'. Devolve (caminho, [(rótulo, cena)])."""
    if "=" not in axis:
        raise VariantError("use --axis caminho=v1,v2,v3")
    path, raw = axis.split("=", 1)
    labels = [v.strip() for v in raw.split(",") if v.strip()]
    if len(labels) < 2:
        raise VariantError("a varredura precisa de pelo menos 2 valores")
    out = []
    for label in labels:
        d = copy.deepcopy(data)
        set_path(d, path, yaml.safe_load(label))
        out.append((label, d))
    return path, out


def kendall_tau(expected: list, observed: list) -> float:
    pos = {v: i for i, v in enumerate(observed)}
    pairs = list(itertools.combinations(expected, 2))
    if not pairs:
        return 1.0
    agree = sum(1 for a, b in pairs if pos[a] < pos[b])
    return (2 * agree - len(pairs)) / len(pairs)
