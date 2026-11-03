"""Auxiliares de validação compartilhados entre o validador e as camadas."""
from __future__ import annotations

import difflib


def closest(got, options):
    """Opção mais parecida com `got` (None se nenhuma passa do corte). Devolve o valor original da opção."""
    opts = list(options)
    m = difflib.get_close_matches(str(got), [str(o) for o in opts], n=1, cutoff=0.6)
    if not m:
        return None
    return next(o for o in opts if str(o) == m[0])


def suggest(got, options) -> str | None:
    m = closest(got, options)
    return f"você quis dizer {m!r}?" if m is not None else None


def is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def enum_check(c, path: str, value, options, required: bool = True) -> bool:
    if value is None:
        if required:
            c.error(path, "campo obrigatório ausente", accepted=list(options))
        return False
    if value not in options:
        near = closest(value, options)
        c.error(path, "valor fora do vocabulário fechado", got=value, accepted=list(options), hint=suggest(value, options),
                fix={"path": path, "value": near} if near is not None else None)
        return False
    return True


def unknown_keys(c, path: str, mapping: dict, allowed) -> None:
    for key in mapping:
        if key not in allowed:
            near = closest(key, allowed)
            c.error(f"{path}.{key}", "campo desconhecido", got=key, accepted=sorted(allowed), hint=suggest(key, allowed),
                    fix={"path": f"{path}.{key}", "rename": near} if near is not None else None)


def str_list(c, path: str, v) -> list[str]:
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        c.error(path, "deve ser uma lista de textos", got=v)
        return []
    return v
