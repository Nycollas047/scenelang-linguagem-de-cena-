"""Auxiliares de validação compartilhados entre o validador e as camadas."""
from __future__ import annotations

import difflib


def suggest(got, options) -> str | None:
    m = difflib.get_close_matches(str(got), [str(o) for o in options], n=1, cutoff=0.6)
    return f"você quis dizer {m[0]!r}?" if m else None


def is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def enum_check(c, path: str, value, options, required: bool = True) -> bool:
    if value is None:
        if required:
            c.error(path, "campo obrigatório ausente", accepted=list(options))
        return False
    if value not in options:
        c.error(path, "valor fora do vocabulário fechado", got=value, accepted=list(options), hint=suggest(value, options))
        return False
    return True


def unknown_keys(c, path: str, mapping: dict, allowed) -> None:
    for key in mapping:
        if key not in allowed:
            c.error(f"{path}.{key}", "campo desconhecido", got=key, accepted=sorted(allowed), hint=suggest(key, allowed))


def str_list(c, path: str, v) -> list[str]:
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        c.error(path, "deve ser uma lista de textos", got=v)
        return []
    return v
