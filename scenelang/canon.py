"""Serialização canônica e hash da cena.

Duas cenas que dizem a mesma coisa (mesmas chaves e valores, em qualquer ordem de chaves YAML) geram o mesmo hash.

Regras da forma canônica (algoritmo `canon-v1`):
- dicionários: chaves viram texto e são ordenadas em todos os níveis;
- listas e tuplas: a ordem é significativa e se preserva (a ordem das entidades define a ordem de desenho);
- números: inteiro e float de mesmo valor são iguais (1 == 1.0); NaN e infinito são rejeitados;
- booleanos, nulos e textos ficam como são; datas viram ISO 8601; texto em UTF-8, sem escape de acentos;
- SHA-256 sobre o JSON compacto resultante.

Dados semânticos × metadados transitórios: `TRANSIENT_KEYS` (histórico e correções da rodada) ficam fora do hash
semântico, porque mudam a cada rodada sem mudar a cena que o usuário pediu. Quem quiser o estado completo
(auditoria da rodada) usa `include_transient=True`.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import math

ALGORITHM = "canon-v1-sha256"
TRANSIENT_KEYS = ("history", "corrections")


class CanonError(ValueError):
    pass


def canonical(obj, _path: str = "$"):
    """Devolve a mesma estrutura em forma canônica (dicts ordenados, números normalizados, só tipos JSON)."""
    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, int):
        return obj
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise CanonError(f"{_path}: número não finito ({obj})")
        return int(obj) if obj.is_integer() and abs(obj) < 2**53 else obj
    if isinstance(obj, (_dt.date, _dt.datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        keys = {}
        for k, v in obj.items():
            ks = str(k)
            if ks in keys:
                raise CanonError(f"{_path}: chaves {k!r} e outra equivalente colidem como {ks!r}")
            keys[ks] = v
        return {k: canonical(keys[k], f"{_path}.{k}") for k in sorted(keys)}
    if isinstance(obj, (list, tuple)):
        return [canonical(v, f"{_path}[{i}]") for i, v in enumerate(obj)]
    if isinstance(obj, (set, frozenset)):
        return sorted((canonical(v, _path) for v in obj), key=lambda x: json.dumps(x, ensure_ascii=False))
    if hasattr(obj, "item"):   # escalar numpy
        return canonical(obj.item(), _path)
    raise CanonError(f"{_path}: tipo sem forma canônica ({type(obj).__name__})")


def semantic(data: dict, include_transient: bool = False) -> dict:
    return {k: v for k, v in data.items() if include_transient or k not in TRANSIENT_KEYS}


def dumps(data, include_transient: bool = False) -> str:
    if isinstance(data, dict):
        data = semantic(data, include_transient)
    return json.dumps(canonical(data), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def scene_hash(data, include_transient: bool = False) -> str:
    """SHA-256 (64 hex) da forma canônica. Aceita o dict da cena ou um objeto com `.data`."""
    data = getattr(data, "data", data)
    return hashlib.sha256(dumps(data, include_transient).encode("utf-8")).hexdigest()


def short(h: str, n: int = 12) -> str:
    return h[:n]
