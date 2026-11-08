# -*- coding: utf-8 -*-
"""
search_engine.py — Module 2 : graphe orienté pondéré + algorithmes de recherche.

Chaque algorithme est un GÉNÉRATEUR : un `yield` = une étape affichable.
Événements (dict) :
    {"type": "init"|"info"|"step"|"result", "msg": str,
     "node": sommet courant, "frontier": [libellés], "fnodes": [sommets de la frontière],
     "explored": [sommets visités dans l'ordre], ...}
L'événement final "result" contient : found, path, cost, expanded, max_frontier.

Conventions : les successeurs sont parcourus par ordre alphabétique (résultats reproductibles).
Le test de but est fait à l'EXPANSION du sommet.

Non informés : BFS, DFS, UCS (coût uniforme), DLS (profondeur limitée), IDS (itératif).
Informés    : Greedy (meilleur d'abord), A*, SBA* et RBFS.
"""
import heapq
import itertools
import json
import math
import time
from collections import deque
from typing import Any, Optional


def num(x):
    """Affichage compact d'un nombre (3 au lieu de 3.0)."""
    if x is None:
        return "—"
    return str(int(x)) if float(x).is_integer() else f"{x:.3g}"


# =========================================================================== #
# Graphe
# =========================================================================== #
class Graph:
    def __init__(self):
        self.nodes = {}      # nom -> (x, y)
        self.edges = {}      # (u, v) -> coût
        self.h = {}          # nom -> h(n)
        self.start: Optional[str] = None
        self.goal: Optional[str] = None

    # -- construction ------------------------------------------------------
    def add_node(self, name, x: float = 100, y: float = 100, h=None):
        name = name.strip()
        if not name:
            raise ValueError("Le nom du sommet est vide.")
        if name in self.nodes:
            raise ValueError(f"Le sommet « {name} » existe déjà.")
        self.nodes[name] = (x, y)
        if h is not None:
            self.set_h(name, h)

    def set_h(self, name, h):
        if name not in self.nodes:
            raise ValueError(f"Sommet inconnu : {name}")
        if h is None:
            self.h.pop(name, None)
            return
        if h < 0 or math.isnan(h) or math.isinf(h):
            raise ValueError("h(n) doit être un nombre positif ou nul.")
        self.h[name] = float(h)

    def remove_node(self, name):
        self.nodes.pop(name, None)
        self.h.pop(name, None)
        self.edges = {e: c for e, c in self.edges.items() if name not in e}
        if self.start == name:
            self.start = None
        if self.goal == name:
            self.goal = None

    def add_edge(self, u, v, cost):
        if u not in self.nodes or v not in self.nodes:
            raise ValueError("Les deux extrémités de l'arc doivent exister.")
        if u == v:
            raise ValueError("Les boucles (arc d'un sommet vers lui-même) ne sont pas autorisées.")
        if cost < 0 or math.isnan(cost) or math.isinf(cost):
            raise ValueError("Le coût d'un arc doit être un nombre positif ou nul "
                             "(UCS, A*… supposent des coûts non négatifs).")
        self.edges[(u, v)] = float(cost)

    def remove_edge(self, u, v):
        self.edges.pop((u, v), None)

    # -- interrogation -----------------------------------------------------
    def neighbors(self, u):
        return sorted(((v, c) for (a, v), c in self.edges.items() if a == u), key=lambda t: t[0])

    def h_of(self, n):
        if n not in self.h:
            raise ValueError(f"Heuristique h({n}) non définie.")
        return self.h[n]

    def missing_h(self):
        return [n for n in self.nodes if n not in self.h]

    def path_cost(self, path):
        return sum(self.edges[(a, b)] for a, b in zip(path, path[1:]))

    def true_costs_to_goal(self):
        """h*(n) : coût optimal de n vers l'objectif (Dijkstra sur le graphe inversé)."""
        if self.goal is None:
            return {}
        rev = {}
        for (u, v), c in self.edges.items():
            rev.setdefault(v, []).append((u, c))
        dist, heap = {self.goal: 0.0}, [(0.0, self.goal)]
        while heap:
            d, n = heapq.heappop(heap)
            if d > dist.get(n, math.inf):
                continue
            for u, c in rev.get(n, []):
                if d + c < dist.get(u, math.inf):
                    dist[u] = d + c
                    heapq.heappush(heap, (d + c, u))
        return dist

    def inadmissible_nodes(self):
        """[(n, h(n), h*(n))] pour les sommets où h(n) > h*(n) (h non admissible)."""
        star, bad = self.true_costs_to_goal(), []
        for n, hv in self.h.items():
            if n in star and hv > star[n] + 1e-9:
                bad.append((n, hv, star[n]))
        return bad

    # -- sérialisation -----------------------------------------------------
    def to_dict(self):
        return {"nodes": {n: {"x": x, "y": y, "h": self.h.get(n)} for n, (x, y) in self.nodes.items()},
                "edges": [{"from": u, "to": v, "cost": c} for (u, v), c in self.edges.items()],
                "start": self.start, "goal": self.goal}

    @classmethod
    def from_dict(cls, d):
        g = cls()
        for n, a in d["nodes"].items():
            g.add_node(n, a.get("x", 100), a.get("y", 100), a.get("h"))
        for e in d["edges"]:
            g.add_edge(e["from"], e["to"], e["cost"])
        for key in ("start", "goal"):
            v = d.get(key)
            if v is not None and v not in g.nodes:
                raise ValueError(f"{key} « {v} » n'est pas un sommet du graphe.")
            setattr(g, key, v)
        return g

    def save(self, path):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))

    @classmethod
    def example(cls):
        """Graphe de démonstration avec la liaison S→E→G à coût total 10."""
        g = cls()
        pos = {"S": (70, 200), "A": (210, 90), "B": (370, 90), "C": (530, 90),
               "D": (210, 320), "E": (370, 220), "G": (690, 200), "H": (530, 330)}
        hv = {"S": 8, "A": 5, "B": 5, "C": 3, "D": 6, "E": 2, "G": 0, "H": 4}
        for n, (x, y) in pos.items():
            g.add_node(n, x, y, hv[n])
        for u, v, c in [
            ("S", "A", 2), ("S", "D", 4), ("S", "E", 5),
            ("A", "B", 3), ("A", "E", 1), ("B", "C", 2), ("C", "G", 3),
            ("D", "G", 9), ("E", "G", 5),
        ]:
            g.add_edge(u, v, c)
        g.start, g.goal = "S", "G"
        return g


# =========================================================================== #
# Outils communs
# =========================================================================== #
class _Stats:
    def __init__(self):
        self.expanded = 0
        self.max_frontier = 0

    def track(self, size):
        self.max_frontier = max(self.max_frontier, size)


def _ev(type_, msg, **kw):
    d = {"type": type_, "msg": msg}
    d.update(kw)
    return d


def _step(node, msg, items, explored, **kw):
    """items = [(sommet, libellé)] de la frontière."""
    return _ev("step", msg, node=node, frontier=[l for _, l in items], fnodes=[n for n, _ in items],
               explored=list(explored), **kw)


def _found(g, path, s, extra=""):
    cost = g.path_cost(path)
    return _ev("result", f"CHEMIN TROUVÉ : {' → '.join(path)}   |   coût total = {num(cost)}{extra}",
               found=True, path=list(path), cost=cost, expanded=s.expanded, max_frontier=s.max_frontier)


def _fail(s, msg="AUCUN CHEMIN TROUVÉ entre l'état initial et l'état objectif."):
    return _ev("result", msg, found=False, path=[], cost=None,
               expanded=s.expanded, max_frontier=s.max_frontier)


def _succ_text(new):
    return "successeurs ajoutés : " + ", ".join(new) if new else "aucun nouveau successeur"


# =========================================================================== #
# Recherches NON informées
# =========================================================================== #
def bfs(g):
    """Parcours en largeur : frontière FIFO."""
    s, closed = _Stats(), []
    fr: deque[tuple[Any, tuple[Any, ...], float]] = deque([(g.start, (g.start,), 0.0)])
    inf = {g.start}
    yield _ev("init", "Initialisation : frontière = [" + g.start + "]", node=None, frontier=[g.start],
              fnodes=[g.start], explored=[])
    while fr:
        node, path, cost = fr.popleft()
        inf.discard(node)
        closed.append(node)
        s.expanded += 1
        if node == g.goal:
            yield _step(node, f"Expansion de {node} (g={num(cost)}) → OBJECTIF ATTEINT",
                        [(p[0], p[0]) for p, _, _ in fr], closed)
            yield _found(g, path, s)
            return
        new = []
        for v, c in g.neighbors(node):
            if v not in closed and v not in inf:
                fr.append((v, path + (v,), cost + c))
                inf.add(v)
                new.append(v)
        s.track(len(fr))
        yield _step(node, f"Expansion de {node} (g={num(cost)}) ; {_succ_text(new)}",
                    [(n, n) for n, _, _ in fr], closed)
    yield _fail(s)


def dfs(g):
    """Parcours en profondeur : frontière LIFO (pile)."""
    s, closed = _Stats(), []
    stack: list[tuple[Any, tuple[Any, ...], float]] = [(g.start, (g.start,), 0.0)]
    yield _ev("init", "Initialisation : pile = [" + g.start + "]", node=None, frontier=[g.start],
              fnodes=[g.start], explored=[])
    while stack:
        node, path, cost = stack.pop()
        if node in closed:
            continue
        closed.append(node)
        s.expanded += 1
        if node == g.goal:
            yield _step(node, f"Dépilement de {node} (g={num(cost)}) → OBJECTIF ATTEINT",
                        [(n, n) for n, _, _ in reversed(stack) if n not in closed], closed)
            yield _found(g, path, s, "   (DFS : chemin non nécessairement optimal)")
            return
        new = []
        for v, c in reversed(g.neighbors(node)):         # ordre alphabétique en sortie de pile
            if v not in closed:
                stack.append((v, path + (v,), cost + c))
                new.append(v)
        s.track(len(stack))
        yield _step(node, f"Dépilement de {node} (g={num(cost)}) ; {_succ_text(list(reversed(new)))}",
                    [(n, n) for n, _, _ in reversed(stack) if n not in closed], closed)
    yield _fail(s)


def ucs(g):
    """Coût uniforme (Dijkstra) : frontière triée par g(n)."""
    s, closed, cnt = _Stats(), [], itertools.count()
    best = {g.start: 0.0}
    heap: list[tuple[float, int, Any, tuple[Any, ...]]] = [
        (0.0, next(cnt), g.start, (g.start,))
    ]

    def items():
        return [(n, f"{n}(g={num(d)})") for d, _, n, _ in sorted(heap)
                if n not in closed and d == best.get(n)]
    yield _ev("init", f"Initialisation : frontière = [{g.start}(g=0)]", node=None,
              frontier=[l for _, l in items()], fnodes=[n for n, _ in items()], explored=[])
    while heap:
        d, _, node, path = heapq.heappop(heap)
        if node in closed or d > best.get(node, math.inf):
            continue
        closed.append(node)
        s.expanded += 1
        if node == g.goal:
            yield _step(node, f"Extraction de {node} (g={num(d)}) → OBJECTIF ATTEINT", items(), closed)
            yield _found(g, path, s, "   (optimal)")
            return
        new = []
        for v, c in g.neighbors(node):
            nd = d + c
            if v not in closed and nd < best.get(v, math.inf):
                best[v] = nd
                heapq.heappush(heap, (nd, next(cnt), v, path + (v,)))
                new.append(f"{v}(g={num(nd)})")
        s.track(len(heap))
        yield _step(node, f"Extraction de {node} (g={num(d)}) ; {_succ_text(new)}", items(), closed)
    yield _fail(s)


def _dls_iter(g, limit, s, closed):
    """DLS itératif (pile). Retourne ('found', path) | ('cutoff',) | ('fail',)."""
    stack: list[tuple[Any, tuple[Any, ...], float]] = [(g.start, (g.start,), 0.0)]
    cutoff = False
    while stack:
        node, path, cost = stack.pop()
        depth = len(path) - 1
        closed.append(node)
        s.expanded += 1
        items = lambda: [(n, f"{n}(p={len(p) - 1})") for n, p, _ in reversed(stack)]
        if node == g.goal:
            yield _step(node, f"Dépilement de {node} (profondeur {depth}, g={num(cost)}) → OBJECTIF ATTEINT",
                        items(), closed)
            return ("found", path)
        if depth >= limit:
            cutoff = True
            yield _step(node, f"Dépilement de {node} (profondeur {depth}) : limite {limit} atteinte, "
                              f"non développé", items(), closed)
            continue
        new = []
        for v, c in reversed(g.neighbors(node)):
            if v not in path:                              # évite les cycles sur la branche
                stack.append((v, path + (v,), cost + c))
                new.append(v)
        s.track(len(stack))
        yield _step(node, f"Dépilement de {node} (profondeur {depth}, g={num(cost)}) ; "
                          f"{_succ_text(list(reversed(new)))}", items(), closed)
    return ("cutoff",) if cutoff else ("fail",)


def dls(g, limit=3):
    """Recherche en profondeur limitée (paramètre : limite)."""
    s, closed = _Stats(), []
    yield _ev("init", f"Profondeur limitée : limite = {limit}", node=None, frontier=[g.start],
              fnodes=[g.start], explored=[])
    r = yield from _dls_iter(g, limit, s, closed)
    if r[0] == "found":
        yield _found(g, r[1], s)
    elif r[0] == "cutoff":
        yield _fail(s, f"ÉCHEC PAR COUPURE : aucun chemin de profondeur ≤ {limit} "
                       f"(un chemin plus long peut exister : augmentez la limite).")
    else:
        yield _fail(s)


def ids(g):
    """Approfondissement itératif : DLS pour limite = 0, 1, 2, …"""
    s = _Stats()
    yield _ev("init", "Approfondissement itératif (limite 0, 1, 2, …)", node=None, frontier=[g.start],
              fnodes=[g.start], explored=[])
    for limit in range(len(g.nodes) + 1):
        closed = []
        yield _ev("info", f"═ Itération : limite de profondeur = {limit}", node=None, frontier=[],
                  fnodes=[], explored=[])
        r = yield from _dls_iter(g, limit, s, closed)
        if r[0] == "found":
            yield _found(g, r[1], s, f"   (trouvé à la limite {limit} : peu d'arcs, pas forcément le moins cher)")
            return
        if r[0] == "fail":
            break
    yield _fail(s)


# =========================================================================== #
# Recherches informées
# =========================================================================== #
def greedy(g):
    """Meilleur d'abord glouton : frontière triée par h(n)."""
    s, closed, cnt = _Stats(), [], itertools.count()
    heap: list[tuple[float, int, Any, tuple[Any, ...]]] = [
        (g.h_of(g.start), next(cnt), g.start, (g.start,))
    ]
    inf = {g.start}
    items = lambda: [(n, f"{n}(h={num(hv)})") for hv, _, n, _ in sorted(heap)]
    yield _ev("init", f"Initialisation : frontière = [{g.start}(h={num(heap[0][0])})]", node=None,
              frontier=[l for _, l in items()], fnodes=[n for n, _ in items()], explored=[])
    while heap:
        hv, _, node, path = heapq.heappop(heap)
        inf.discard(node)
        closed.append(node)
        s.expanded += 1
        if node == g.goal:
            yield _step(node, f"Extraction de {node} (h={num(hv)}) → OBJECTIF ATTEINT", items(), closed)
            yield _found(g, path, s, "   (glouton : non nécessairement optimal)")
            return
        new = []
        for v, _ in g.neighbors(node):
            if v not in closed and v not in inf:
                heapq.heappush(heap, (g.h_of(v), next(cnt), v, path + (v,)))
                inf.add(v)
                new.append(f"{v}(h={num(g.h_of(v))})")
        s.track(len(heap))
        yield _step(node, f"Extraction de {node} (h={num(hv)}) ; {_succ_text(new)}", items(), closed)
    yield _fail(s)


def astar(g):
    """A* : f(n) = g(n) + h(n). Réouverture des sommets si un meilleur g est trouvé."""
    s, closed, cnt = _Stats(), [], itertools.count()
    best = {g.start: 0.0}
    h0 = g.h_of(g.start)
    heap: list[tuple[float, float, int, Any, tuple[Any, ...], float]] = [
        (h0, h0, next(cnt), g.start, (g.start,), 0.0)
    ]

    def items():
        return [(n, f"{n}(f={num(f)}=g{num(gv)}+h{num(hh)})") for f, hh, _, n, _, gv in sorted(heap)
                if gv == best.get(n) and n not in closed]
    yield _ev("init", f"Initialisation : frontière = [{g.start}(f={num(h0)})]", node=None,
              frontier=[l for _, l in items()], fnodes=[n for n, _ in items()], explored=[])
    while heap:
        f, _, _, node, path, gv = heapq.heappop(heap)
        if gv > best.get(node, math.inf) or node in closed:
            continue
        closed.append(node)
        s.expanded += 1
        if node == g.goal:
            yield _step(node, f"Extraction de {node} (f={num(f)}) → OBJECTIF ATTEINT", items(), closed)
            warn = ""
            if g.inadmissible_nodes():
                warn = "   (⚠ h non admissible : optimalité non garantie)"
            else:
                warn = "   (optimal : h admissible)"
            yield _found(g, path, s, warn)
            return
        new = []
        for v, c in g.neighbors(node):
            ng = gv + c
            if ng < best.get(v, math.inf):
                if v in closed:                       # réouverture (h non consistante)
                    closed.remove(v)
                    new.append(f"{v}(réouvert)")
                best[v] = ng
                hv = g.h_of(v)
                heapq.heappush(heap, (ng + hv, hv, next(cnt), v, path + (v,), ng))
                new.append(f"{v}(f={num(ng + hv)})")
        s.track(len(heap))
        yield _step(node, f"Extraction de {node} (g={num(gv)}, f={num(f)}) ; {_succ_text(new)}", items(), closed)
    yield _fail(s)


def sba_star(g, memory_limit=None):
    """SBA* (Simplified Memory-Bounded A*) : A* avec une borne mémoire explicite.

    L'heuristique est traitée comme dans A* ; la mémoire est bornée par une limite
    explicite, avec élimination des nœuds de plus grand f. La stratégie reste
    compatible avec le format d'événements existant.
    """
    s, closed, cnt = _Stats(), [], itertools.count()
    best = {g.start: 0.0}
    if memory_limit is None:
        memory_limit = max(4, 2 * len(g.nodes))
    h0 = g.h_of(g.start)
    heap: list[tuple[float, float, int, Any, tuple[Any, ...], float]] = [
        (h0, h0, next(cnt), g.start, (g.start,), 0.0)
    ]

    def items():
        return [(n, f"{n}(f={num(f)}=g{num(gv)}+h{num(hh)})") for f, hh, _, n, _, gv in sorted(heap)
                if gv == best.get(n) and n not in closed]

    yield _ev("init", f"SBA* : mémoire max = {memory_limit} nœuds ; frontière = [{g.start}(f={num(h0)})]",
              node=None, frontier=[l for _, l in items()], fnodes=[n for n, _ in items()], explored=[])
    while heap:
        f, _, _, node, path, gv = heapq.heappop(heap)
        if gv > best.get(node, math.inf) or node in closed:
            continue
        closed.append(node)
        s.expanded += 1
        if node == g.goal:
            yield _step(node, f"Extraction de {node} (f={num(f)})  → OBJECTIF ATTEINT", items(), closed)
            warn = "   (optimal : h admissible)" if not g.inadmissible_nodes() else "   (⚠ h non admissible : optimalité non garantie)"
            yield _found(g, path, s, warn)
            return
        new = []
        for v, c in g.neighbors(node):
            ng = gv + c
            if ng < best.get(v, math.inf):
                if v in closed:
                    closed.remove(v)
                    new.append(f"{v}(réouvert)")
                best[v] = ng
                hv = g.h_of(v)
                heapq.heappush(heap, (ng + hv, hv, next(cnt), v, path + (v,), ng))
                new.append(f"{v}(f={num(ng + hv)})")
        if len(heap) > memory_limit:
            heap = sorted(heap, key=lambda x: (x[0], x[1], x[2]))[:memory_limit]
        s.track(len(heap))
        yield _step(node, f"Extraction de {node} (g={num(gv)}, f={num(f)}) ; {_succ_text(new)}", items(), closed)
    yield _fail(s)


sma_star = sba_star


def rbfs(g):
    """RBFS (Recursive Best-First Search) : meilleure branche récursive avec borne f.

    L'algorithme suit le schéma générique de recherche en générateurs : chaque étape
    produit un événement _step, puis un _found/_fail final, compatible avec l'API
    Graph et les fonctions _ev / _step / _found / _fail.
    """
    s = _Stats()

    def search(node, path, gcost, bound):
        s.expanded += 1
        if node == g.goal:
            yield _step(node, f"{node} : f={num(gcost + g.h_of(node))} ≤ borne → OBJECTIF ATTEINT",
                        [], list(path))
            yield _found(g, path, s, "   (optimal si h admissible)")
            return True

        children = []
        for v, c in g.neighbors(node):
            if v in path:
                continue
            ng = gcost + c
            children.append((ng + g.h_of(v), v, path + (v,), ng))
        if not children:
            yield _step(node, f"{node} : aucun successeur, coupure de branche", [], list(path))
            return False

        children.sort(key=lambda item: (item[0], item[1]))
        best_f, best_v, best_path, best_g = children[0]
        if best_f > bound:
            yield _step(node, f"{node} : meilleure branche f={num(best_f)} > borne {num(bound)} → coupure",
                        [(n, f"{n}(f={num(f)})") for f, n, _, _ in children], list(path))
            return False

        alt = children[1][0] if len(children) > 1 else math.inf
        s.track(len(children))
        yield _step(node, f"Expansion de {node} ; meilleur = {best_v} (f={num(best_f)})",
                    [(n, f"{n}(f={num(f)})") for f, n, _, _ in children], list(path))
        result = yield from search(best_v, best_path, best_g, min(bound, alt))
        if result:
            return True
        if len(children) > 1:
            for _, v, subpath, ng in children[1:]:
                result = yield from search(v, subpath, ng, bound)
                if result:
                    return True
        return False

    yield _ev("init", "RBFS : recherche récursive meilleure-première avec borne",
              node=None, frontier=[g.start], fnodes=[g.start], explored=[])
    found = yield from search(g.start, (g.start,), 0.0, math.inf)
    if not found:
        yield _fail(s)


# Registre, validation, comparaison
# =========================================================================== #
UNINFORMED = {
    "Largeur d'abord (BFS)": bfs,
    "Profondeur d'abord (DFS)": dfs,
    "Coût uniforme (UCS)": ucs,
    "Profondeur limitée (DLS)": dls,
    "Approfondissement itératif (IDS)": ids,
}
INFORMED = {
    "Glouton (Greedy Best-First)": greedy,
    "A*": astar,
    "SBA* (Simplified Memory-Bounded A*)": sba_star,
    "RBFS (Recursive Best-First Search)": rbfs,
}


def validate(g, informed):
    """Retourne (erreurs, avertissements) avant de lancer une recherche."""
    errors, warns = [], []
    if not g.nodes:
        errors.append("Le graphe est vide.")
        return errors, warns
    if g.start is None:
        errors.append("L'état initial n'est pas défini.")
    if g.goal is None:
        errors.append("L'état objectif n'est pas défini.")
    if informed:
        miss = g.missing_h()
        if miss:
            errors.append("Heuristique h(n) manquante pour : " + ", ".join(miss))
        elif g.goal is not None:
            bad = g.inadmissible_nodes()
            if bad:
                warns.append("h non admissible (h > coût réel) pour : " +
                             ", ".join(f"{n}(h={num(a)} > h*={num(b)})" for n, a, b in bad) +
                             " → A*/SBA*/RBFS peuvent ne pas être optimaux.")
            if g.h.get(g.goal, 0) != 0:
                warns.append(f"h(objectif) = {num(g.h[g.goal])} ≠ 0.")
    return errors, warns


def run_to_end(fn, g, **params):
    """Exécute un algorithme jusqu'au bout ; retourne (événement résultat, durée en ms, nb d'étapes)."""
    t0, last, steps = time.perf_counter(), None, 0
    for ev in fn(g, **params):
        last = ev
        steps += 1
    return last, (time.perf_counter() - t0) * 1000, steps
