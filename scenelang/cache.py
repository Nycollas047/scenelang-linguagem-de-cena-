"""Cache em memória, endereçado por conteúdo, com invalidação por dependência.

A chave é o hash canônico de TUDO de que o resultado depende (texto da cena, imagem, parâmetros) mais a versão do
scenelang: mudou uma dependência → a chave muda → é uma falha de cache (não existe invalidação manual para esquecer).
Mudar algo de que o resultado NÃO depende (ex.: o histórico de rodadas ao compilar) mantém a chave → acerto.

Não guarda nada em disco. Cenas com `extends`/`import` não entram no cache de leitura, porque dependem de outros
arquivos que o texto não mostra.
"""
from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from typing import Any, Callable

from . import __version__, canon


def key_of(*parts: Any) -> str:
    blob = json.dumps([__version__, *[canon.canonical(p) if not isinstance(p, (bytes, str)) else
                                      (p if isinstance(p, str) else hashlib.sha256(p).hexdigest()) for p in parts]],
                      ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class Cache:
    def __init__(self, maxsize: int = 256):
        self.maxsize = maxsize
        self._d: OrderedDict[tuple[str, str], Any] = OrderedDict()
        self.hits = self.misses = 0
        self.by_ns: dict[str, list[int]] = {}

    def memo(self, ns: str, key: str, fn: Callable[[], Any]):
        k = (ns, key)
        st = self.by_ns.setdefault(ns, [0, 0])
        if k in self._d:
            self._d.move_to_end(k)
            self.hits += 1
            st[0] += 1
            return self._d[k]
        self.misses += 1
        st[1] += 1
        v = fn()
        self._d[k] = v
        if len(self._d) > self.maxsize:
            self._d.popitem(last=False)
        return v

    def clear(self) -> None:
        self._d.clear()
        self.hits = self.misses = 0
        self.by_ns.clear()

    def stats(self) -> dict:
        return {"entries": len(self._d), "hits": self.hits, "misses": self.misses,
                "namespaces": {ns: {"hits": h, "misses": m} for ns, (h, m) in self.by_ns.items()}}


DEFAULT = Cache()


def _external_refs(text: str) -> bool:
    import yaml
    try:
        d = yaml.safe_load(text)
    except yaml.YAMLError:
        return True
    return isinstance(d, dict) and ("extends" in d or "import" in d)


def load_cached(text: str, cache: Cache | None = None):
    """`validate.load_text` com cache. O resultado (diags, scene, data) é compartilhado: trate como somente leitura."""
    from .validate import load_text
    c = cache or DEFAULT
    if _external_refs(text):
        return load_text(text)
    return c.memo("load", key_of(text), lambda: load_text(text))


def compile_key(data: dict, backend: str, size: str | None = None, passname: str | None = None) -> str:
    """O que muda o prompt: a cena inteira menos o histórico (que nunca entra no texto)."""
    return key_of({k: v for k, v in data.items() if k != "history"}, backend, size, passname)
