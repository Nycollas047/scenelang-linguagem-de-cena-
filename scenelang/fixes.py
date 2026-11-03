"""Aplica as correções propostas pelos diagnósticos (`Diagnostic.fix`)."""
from __future__ import annotations

import copy
import re

_TOKEN = re.compile(r"\.([^.\[\]]+)|\[(\d+)\]")


def parse_path(path: str) -> list:
    if not path.startswith("$"):
        raise ValueError(f"caminho inválido: {path!r}")
    return [m.group(1) if m.group(1) is not None else int(m.group(2)) for m in _TOKEN.finditer(path[1:])]


def _walk(data, tokens):
    cur = data
    for t in tokens:
        cur = cur[t]
    return cur


def apply_fixes(data, diagnostics):
    """Devolve (nova cópia, lista de correções aplicadas). Só aplica o que tem `fix`."""
    d = copy.deepcopy(data)
    applied = []
    for diag in diagnostics:
        fx = getattr(diag, "fix", None)
        if not fx:
            continue
        try:
            tokens = parse_path(fx["path"])
            if "value" in fx:
                parent = _walk(d, tokens[:-1])
                old = parent[tokens[-1]]
                parent[tokens[-1]] = fx["value"]
                applied.append(f"{fx['path']}: {old!r} → {fx['value']!r}")
            elif "rename" in fx:
                parent = _walk(d, tokens[:-1])
                old = tokens[-1]
                if fx["rename"] in parent:
                    continue
                parent[fx["rename"]] = parent.pop(old)
                applied.append(f"{fx['path']}: campo {old!r} → {fx['rename']!r}")
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return d, applied
