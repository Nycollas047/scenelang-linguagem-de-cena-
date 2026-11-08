"""Grafo de nós e conexões de um mapa (`graph:`) e os algoritmos que o validam: alcançabilidade, softlock, rotas independentes.

graph:
  spawn: atrio_entrada            # nó (ou entidade dentro de um nó) onde o jogador começa
  goal: sala_altar                # nó (ou entidade dentro de um nó) que ele precisa alcançar
  nodes:                          # opcional: papéis; sem isso os nós saem das arestas
    - {id: atrio_entrada, role: spawn}
  edges:
    - {from: atrio_entrada, to: sala_altar, via: ponte_central, kind: bidirectional}
    - {from: corredor, to: sala_altar, via: porta_grade, kind: locked, unlocked_by: mecanismo_grade}

Nós, `via` e `unlocked_by` são ids de entidades da cena (as caixas dão a geometria). Tipos de aresta:
bidirectional (padrão), one_way (só from→to), locked (precisa de `unlocked_by`), destructible, hazard.
`reachable` e `min_paths` tratam trancada/destrutível/perigosa como passáveis (existe passagem); `no_softlock` não: ele só
atravessa uma aresta trancada depois de «coletar» a entidade `unlocked_by`, que precisa estar dentro de um nó já alcançado.
"""
from __future__ import annotations

from collections import deque

from . import layout as L

NODE_ROLES = ("spawn", "hub", "combat", "puzzle", "reward", "boss", "secret", "extraction", "flank", "corridor", "safe")
EDGE_KINDS = ("bidirectional", "one_way", "locked", "destructible", "hazard")
GRAPH_KEYS = {"spawn", "goal", "nodes", "edges"}
EDGE_KEYS = {"from", "to", "via", "kind", "unlocked_by"}
NODE_KEYS = {"id", "role"}
VIA_TOL = 0.12          # `via` precisa estar a até esta distância borda a borda (em alturas) dos dois nós que liga


def edges(data: dict) -> list[dict]:
    g = data.get("graph")
    return [e for e in (g.get("edges") if isinstance(g, dict) else None) or [] if isinstance(e, dict)]


def node_ids(data: dict) -> list[str]:
    g = data.get("graph") or {}
    ids = [n["id"] for n in g.get("nodes") or [] if isinstance(n, dict) and isinstance(n.get("id"), str)]
    for e in edges(data):
        for k in ("from", "to"):
            if isinstance(e.get(k), str) and e[k] not in ids:
                ids.append(e[k])
    return ids


def node_of(scene, ref: str) -> str | None:
    """Nó que `ref` representa: o próprio id, ou o nó cuja caixa contém o centro da entidade."""
    name = str(ref).split(".")[0]
    nodes = node_ids(scene.data)
    if name in nodes:
        return name
    ent = scene.by_id.get(name)
    if ent is None:
        return None
    cx, cy = ent.center
    inside = [n for n in nodes if n in scene.by_id and L.point_in_box((cx, cy), scene.by_id[n].box)]
    inside.sort(key=lambda n: scene.by_id[n].box[2] * scene.by_id[n].box[3])      # o menor nó que contém
    return inside[0] if inside else None


def _arcs(data: dict, unlocked: set[str] | None = None):
    """Arestas orientadas (a, b, aresta). `unlocked=None`: trancadas passam; senão só com a chave em `unlocked`."""
    for e in edges(data):
        kind = e.get("kind", "bidirectional")
        if unlocked is not None and kind == "locked" and e.get("unlocked_by") not in unlocked:
            continue
        yield e["from"], e["to"], e
        if kind != "one_way":
            yield e["to"], e["from"], e


def _bfs(data: dict, start: str, unlocked: set[str] | None = None) -> set[str]:
    adj: dict[str, list[str]] = {}
    for a, b, _ in _arcs(data, unlocked):
        adj.setdefault(a, []).append(b)
    seen, q = {start}, deque([start])
    while q:
        for n in adj.get(q.popleft(), ()):
            if n not in seen:
                seen.add(n)
                q.append(n)
    return seen


def reachable(scene, a: str, b: str) -> tuple[bool, str]:
    na, nb = node_of(scene, a), node_of(scene, b)
    if na is None or nb is None:
        return False, f"{a if na is None else b} não está em nenhum nó do grafo"
    seen = _bfs(scene.data, na)
    return nb in seen, (f"{nb} alcançável a partir de {na}" if nb in seen else f"{nb} não é alcançável a partir de {na}; alcança só: {', '.join(sorted(seen))}")


def connected(scene, a: str, b: str) -> tuple[bool, str]:
    na, nb = node_of(scene, a), node_of(scene, b)
    if na is None or nb is None:
        return False, f"{a if na is None else b} não está em nenhum nó do grafo"
    for e in edges(scene.data):
        if {e["from"], e["to"]} != {na, nb}:
            continue
        via = e.get("via")
        if via and via in scene.by_id and na in scene.by_id and nb in scene.by_id:
            vb = scene.by_id[via].box
            ds = [L.box_clearance(vb, scene.by_id[n].box, scene.ratio) for n in (na, nb)]
            if max(ds) > VIA_TOL:
                far = nb if ds[1] > ds[0] else na
                return False, f"existe aresta {na}↔{nb}, mas {via} está a {max(ds):.3f} de {far} (limite {VIA_TOL})"
        return True, f"aresta {na}↔{nb}" + (f" via {via}" if via else "")
    return False, f"nenhuma aresta liga {na} a {nb}"


def no_softlock(scene, spawn: str, goal: str) -> tuple[bool, str]:
    ns, ng = node_of(scene, spawn), node_of(scene, goal)
    if ns is None or ng is None:
        return False, f"{spawn if ns is None else goal} não está em nenhum nó do grafo"
    unlocked: set[str] = set()
    while True:
        reached = _bfs(scene.data, ns, unlocked)
        keys = {e["unlocked_by"] for e in edges(scene.data) if e.get("kind") == "locked" and e.get("unlocked_by")}
        found = {k for k in keys if k in scene.by_id and node_of(scene, k) in reached}
        if found <= unlocked:
            break
        unlocked |= found
    if ng in reached:
        return True, f"{ng} alcançável de {ns}" + (f" coletando {', '.join(sorted(unlocked))}" if unlocked else " sem chaves")
    why = []
    for e in edges(scene.data):
        if e.get("kind") == "locked" and e.get("unlocked_by") not in unlocked and (e["from"] in reached or e["to"] in reached):
            k = e.get("unlocked_by")
            where = node_of(scene, k) if k in scene.by_id else None
            why.append(f"a passagem {e.get('via') or e['from'] + '→' + e['to']} só abre com {k}, que está em {where or '(fora de qualquer nó)'}"
                       + (" (atrás dela mesma)" if where and where not in reached else ""))
    return False, f"softlock: de {ns} só se alcança {', '.join(sorted(reached))}; " + ("; ".join(why) or f"{ng} não tem aresta de entrada")


def requires(scene, a: str, b: str, key: str) -> tuple[bool, str]:
    """`key` é obrigatória para ir de a até b? Verdadeiro se b é alcançável com todas as chaves, mas NÃO sem `key`
    (qualquer atalho que contorne a trava faz o predicado falhar)."""
    na, nb = node_of(scene, a), node_of(scene, b)
    if na is None or nb is None:
        return False, f"{a if na is None else b} não está em nenhum nó do grafo"
    keys = {e["unlocked_by"] for e in edges(scene.data) if e.get("kind") == "locked" and e.get("unlocked_by")}
    if key not in keys:
        return False, f"{key} não abre nenhuma passagem do grafo"

    def reach(blocked: str | None) -> set[str]:
        unlocked: set[str] = set()
        while True:
            reached = _bfs(scene.data, na, unlocked)
            found = {k for k in keys if k != blocked and k in scene.by_id and node_of(scene, k) in reached}
            if found <= unlocked:
                return reached
            unlocked |= found

    if nb not in reach(None):
        return False, f"{nb} nem é alcançável com todas as chaves (veja no_softlock)"
    without = reach(key)
    if nb in without:
        return False, f"{key} NÃO é obrigatória: {nb} é alcançável sem ela (existe um atalho que contorna a trava)"
    return True, f"sem {key}, de {na} só se alcança {', '.join(sorted(without))}; {nb} exige a chave"


def max_paths(scene, a: str, b: str) -> tuple[int, str]:
    """Rotas independentes (sem arestas em comum) entre dois nós: fluxo máximo com capacidade 1 por aresta (teorema de Menger)."""
    na, nb = node_of(scene, a), node_of(scene, b)
    if na is None or nb is None:
        return 0, f"{a if na is None else b} não está em nenhum nó do grafo"
    if na == nb:
        return 0, "origem e destino são o mesmo nó"
    cap: dict[tuple[str, str], int] = {}
    adj: dict[str, set[str]] = {}
    for x, y, _ in _arcs(scene.data):
        cap[(x, y)] = cap.get((x, y), 0) + 1
        cap.setdefault((y, x), 0)
        adj.setdefault(x, set()).add(y)
        adj.setdefault(y, set()).add(x)
    flow = 0
    while True:
        prev, q = {na: None}, deque([na])
        while q and nb not in prev:
            u = q.popleft()
            for v in adj.get(u, ()):
                if v not in prev and cap[(u, v)] > 0:
                    prev[v] = u
                    q.append(v)
        if nb not in prev:
            return flow, f"{flow} rota(s) independente(s) entre {na} e {nb}"
        v = nb
        while prev[v] is not None:
            u = prev[v]
            cap[(u, v)] -= 1
            cap[(v, u)] += 1
            v = u
        flow += 1


def check(c, data: dict, scene) -> None:
    g = data.get("graph")
    if g is None:
        return
    if not isinstance(g, dict):
        c.error("$.graph", "deve ser um mapa com spawn, goal, nodes, edges", got=g)
        return
    for k in g:
        if k not in GRAPH_KEYS:
            c.error(f"$.graph.{k}", "campo desconhecido", got=k, accepted=sorted(GRAPH_KEYS))
    ents = set(scene.by_id) if scene is not None else None

    def ent_ok(path, ref, what):
        if not isinstance(ref, str):
            c.error(path, f"{what} deve ser o id de uma entidade", got=ref)
            return False
        if ents is not None and ref not in ents and ref not in c.skipped:
            c.error(path, f"{what}: entidade inexistente", got=ref, accepted=sorted(ents))
            return False
        return True

    declared: set[str] = set()
    for i, n in enumerate(g.get("nodes") or []):
        p = f"$.graph.nodes[{i}]"
        if not isinstance(n, dict):
            c.error(p, "cada nó deve ser um mapa {id, role}", got=n)
            continue
        for k in n:
            if k not in NODE_KEYS:
                c.error(f"{p}.{k}", "campo desconhecido", got=k, accepted=sorted(NODE_KEYS))
        if ent_ok(f"{p}.id", n.get("id"), "nó"):
            if n["id"] in declared:
                c.error(f"{p}.id", "nó repetido", got=n["id"])
            declared.add(n["id"])
        if "role" in n and n["role"] not in NODE_ROLES:
            c.error(f"{p}.role", "papel de nó desconhecido", got=n["role"], accepted=list(NODE_ROLES))
    es = g.get("edges")
    if not isinstance(es, list) or not es:
        c.error("$.graph.edges", "deve ser uma lista não vazia de arestas {from, to, via, kind}", got=es)
        return
    used: set[str] = set()
    for i, e in enumerate(es):
        p = f"$.graph.edges[{i}]"
        if not isinstance(e, dict):
            c.error(p, "cada aresta deve ser um mapa", got=e)
            continue
        for k in e:
            if k not in EDGE_KEYS:
                c.error(f"{p}.{k}", "campo desconhecido", got=k, accepted=sorted(EDGE_KEYS))
        for k in ("from", "to"):
            if k not in e:
                c.error(f"{p}.{k}", "campo obrigatório ausente")
            elif ent_ok(f"{p}.{k}", e[k], "nó"):
                used.add(e[k])
                if declared and e[k] not in declared:
                    c.error(f"{p}.{k}", "nó não declarado em graph.nodes", got=e[k], accepted=sorted(declared))
        if e.get("via") is not None:
            ent_ok(f"{p}.via", e["via"], "via")
        kind = e.get("kind", "bidirectional")
        if kind not in EDGE_KINDS:
            c.error(f"{p}.kind", "tipo de aresta desconhecido", got=kind, accepted=list(EDGE_KINDS))
        if kind == "locked":
            if not e.get("unlocked_by"):
                c.error(f"{p}.unlocked_by", "aresta trancada exige `unlocked_by` (a entidade que a abre)")
            else:
                ent_ok(f"{p}.unlocked_by", e["unlocked_by"], "unlocked_by")
        elif "unlocked_by" in e:
            c.warn(f"{p}.unlocked_by", "`unlocked_by` só tem efeito em arestas `locked`", got=kind)
        if e.get("from") == e.get("to") and e.get("from") is not None:
            c.error(p, "uma aresta não pode ligar um nó a ele mesmo", got=e.get("from"))
    nodes = declared | used
    for k in ("spawn", "goal"):
        if k in g and ent_ok(f"$.graph.{k}", g[k], k) and scene is not None and node_of(scene, g[k]) is None:
            c.error(f"$.graph.{k}", f"{g[k]!r} não é um nó nem está dentro de um nó", got=g[k], accepted=sorted(nodes))
