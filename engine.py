# -*- coding: utf-8 -*-
"""
engine.py — Moteur d'inférence (chaînage avant / chaînage arrière).

Les deux moteurs sont des GÉNÉRATEURS : chaque `yield` produit un événement
(dict) correspondant à UNE étape du raisonnement, ce qui permet à l'interface
d'afficher le raisonnement pas à pas.

Événement : {"type": str, "msg": str, "depth": int, ...}
Types : start, cycle, conflict, fire, known, goal, rule, ask, success, fail, info, result
Le chaînage arrière émet des événements "ask" ; l'appelant répond avec
`gen.send(True/False)` (l'utilisateur confirme ou non le fait).
"""
from collections import defaultdict


def condition_facts(condition):
    """Return the facts referenced by a nested condition tree."""
    if isinstance(condition, str):
        return [condition]
    if not isinstance(condition, dict):
        return []
    if "fact" in condition:
        return [condition["fact"]]
    values = []
    for key in ("all", "any"):
        for child in condition.get(key, []):
            values.extend(condition_facts(child))
    if "not" in condition:
        values.extend(condition_facts(condition["not"]))
    return values


def rule_condition(rule):
    """Read both the current ``when`` format and legacy ``if`` rules."""
    if "when" in rule:
        return rule["when"]
    return {"all": [{"fact": fact} for fact in rule.get("if", [])]}


def evaluate_condition(condition, facts):
    """Evaluate a condition tree against a set of known facts."""
    if isinstance(condition, str):
        return condition in facts
    if not isinstance(condition, dict):
        return False
    if "fact" in condition:
        return condition["fact"] in facts
    if "all" in condition:
        return all(evaluate_condition(c, facts) for c in condition["all"])
    if "any" in condition:
        return any(evaluate_condition(c, facts) for c in condition["any"])
    if "not" in condition:
        return not evaluate_condition(condition["not"], facts)
    return False


def format_condition(condition):
    if isinstance(condition, str):
        return condition
    if not isinstance(condition, dict):
        return "<?>"
    if "fact" in condition:
        return condition["fact"]
    if "all" in condition:
        return "(" + " ET ".join(format_condition(c) for c in condition["all"]) + ")"
    if "any" in condition:
        return "(" + " OU ".join(format_condition(c) for c in condition["any"]) + ")"
    if "not" in condition:
        return "NON (" + format_condition(condition["not"]) + ")"
    return "<?>"


def format_rule(r):
    return f"{r['id']}: SI {format_condition(rule_condition(r))} ALORS {r['then']}"


def question_for(kb, fact):
    q = kb.get("catalog", {}).get(fact, {}).get("question")
    return q or f"Le fait suivant est-il vrai ?\n\n« {fact} »"


def all_facts(kb):
    """Ensemble de tous les faits connus (catalogue + règles + base initiale)."""
    s = set(kb.get("catalog", {})) | set(kb.get("initial_facts", []))
    for r in kb["rules"]:
        s.update(condition_facts(rule_condition(r)))
        s.add(r["then"])
    return sorted(s)


def explain(fact, facts0, derived, indent=0):
    """Arbre de preuve (lignes de texte) justifiant `fact`."""
    pad = "    " * indent
    if fact in derived:
        r = derived[fact]
        lines = [f"{pad}{fact}   ⇐ {r['id']}"]
        for c in condition_facts(rule_condition(r)):
            lines += explain(c, facts0, derived, indent + 1)
        return lines
    origin = "base de faits" if fact in facts0 else "réponse de l'utilisateur"
    return [f"{pad}{fact}   [{origin}]"]


def _ev(type_, msg, depth=0, **kw):
    d = {"type": type_, "msg": msg, "depth": depth}
    d.update(kw)
    return d


# --------------------------------------------------------------------------- #
# Chaînage avant (guidé par les données)
# --------------------------------------------------------------------------- #
def forward_chaining(kb, facts, goal, derived=None):
    """
    `facts` : set MODIFIÉ en place (base de faits courante).
    Stratégie : à chaque cycle on calcule l'ensemble de conflit (règles dont
    toutes les conditions sont vraies et dont la conclusion est nouvelle) ;
    résolution de conflit = première règle dans l'ordre de la base.
    Arrêt dès que le but est dans la base ou qu'aucune règle n'est applicable.
    """
    derived = {} if derived is None else derived
    facts0 = set(facts)
    rules = kb["rules"]
    yield _ev("start", f"CHAÎNAGE AVANT — objectif : « {goal} »")
    yield _ev("info", f"Base de faits initiale : {len(facts)} fait(s) ; base de règles : {len(rules)} règle(s)")

    if goal in facts:
        yield _ev("known", f"✔ L'objectif est déjà présent dans la base de faits.")
        yield _ev("result", "✔ OBJECTIF DÉMONTRÉ (déjà présent)", success=True,
                  proof=explain(goal, facts0, derived), fired=0)
        return

    cycle, fired = 0, 0
    while True:
        cycle += 1
        conflict = [r for r in rules
                    if r["then"] not in facts and evaluate_condition(rule_condition(r), facts)]
        yield _ev("cycle", f"── Cycle {cycle} ──")
        if not conflict:
            yield _ev("fail", "Aucune règle applicable : saturation de la base de faits.")
            yield _ev("result", f"✘ OBJECTIF NON DÉMONTRÉ : « {goal} » n'est pas déductible "
                                f"avec les faits actuels ({len(facts)} faits, {fired} règle(s) tirée(s)).",
                      success=False, proof=[], fired=fired)
            return
        ids = ", ".join(r["id"] for r in conflict[:8]) + (" …" if len(conflict) > 8 else "")
        yield _ev("conflict", f"Ensemble de conflit : {len(conflict)} règle(s) applicable(s) [{ids}]")
        r = conflict[0]
        facts.add(r["then"])
        derived[r["then"]] = r
        fired += 1
        yield _ev("fire", f"Tir de {format_rule(r)}\n      → nouveau fait : « {r['then']} »")
        if r["then"] == goal:
            yield _ev("success", f"✔ L'objectif « {goal} » vient d'être déduit.")
            yield _ev("result", f"✔ OBJECTIF DÉMONTRÉ en {cycle} cycle(s), {fired} règle(s) tirée(s).",
                      success=True, proof=explain(goal, facts0, derived), fired=fired)
            return


# --------------------------------------------------------------------------- #
# Chaînage arrière (guidé par le but)
# --------------------------------------------------------------------------- #
def backward_chaining(kb, facts, goal, derived=None):
    """
    Démonstration récursive du but (DFS). Un fait qui n'est ni dans la base
    ni conclusion d'une règle est une « feuille » : l'utilisateur est interrogé
    (événement "ask", réponse via gen.send(bool)).
    """
    derived = {} if derived is None else derived
    facts0 = set(facts)
    false_ = set()                                   # faits réfutés / inconnus
    by_head = defaultdict(list)
    for r in kb["rules"]:
        by_head[r["then"]].append(r)
    stats = {"asked": 0, "rules": 0}

    def prove(g, depth, stack):
        if g in facts:
            yield _ev("known", f"✔ « {g} » est connu (base de faits).", depth)
            return True
        if g in false_:
            yield _ev("fail", f"✘ « {g} » déjà réfuté.", depth)
            return False
        if g in stack:
            yield _ev("fail", f"✘ Boucle détectée sur « {g} ».", depth)
            return False

        yield _ev("goal", f"BUT : démontrer « {g} »", depth)
        cands = by_head.get(g, [])
        if cands:
            yield _ev("info", f"{len(cands)} règle(s) concluent ce fait : "
                              + ", ".join(r["id"] for r in cands[:8]) + (" …" if len(cands) > 8 else ""), depth)
            for r in cands:
                stats["rules"] += 1
                yield _ev("rule", f"Essai de {format_rule(r)}", depth)
                ok = True
                res = yield from prove_condition(rule_condition(r), depth + 1, stack | {g})
                ok = res
                if ok:
                    facts.add(g)
                    derived[g] = r
                    yield _ev("success", f"✔ {r['id']} appliquée → « {g} » démontré.", depth)
                    return True
                yield _ev("fail", f"✘ {r['id']} échoue (une condition n'est pas démontrable).", depth)
            false_.add(g)
            yield _ev("fail", f"✘ Aucune règle ne permet de démontrer « {g} ».", depth)
            return False
        # Feuille : on interroge l'utilisateur
        stats["asked"] += 1
        ans = yield _ev("ask", f"QUESTION : « {g} » ?", depth, fact=g, question=question_for(kb, g))
        if ans:
            facts.add(g)
            yield _ev("success", f"✔ Réponse OUI : « {g} » ajouté à la base de faits.", depth)
            return True
        false_.add(g)
        yield _ev("fail", f"✘ Réponse NON / inconnu : « {g} » considéré faux.", depth)
        return False

    def prove_condition(condition, depth, stack):
        if isinstance(condition, str):
            return (yield from prove(condition, depth, stack))
        if not isinstance(condition, dict):
            return False
        if "fact" in condition:
            return (yield from prove(condition["fact"], depth, stack))
        if "all" in condition:
            for child in condition["all"]:
                if not (yield from prove_condition(child, depth, stack)):
                    return False
            return True
        if "any" in condition:
            for child in condition["any"]:
                if (yield from prove_condition(child, depth, stack)):
                    return True
            return False
        if "not" in condition:
            return not (yield from prove_condition(condition["not"], depth, stack))
        return False

    yield _ev("start", f"CHAÎNAGE ARRIÈRE — objectif : « {goal} »")
    yield _ev("info", f"Base de faits initiale : {len(facts)} fait(s) ; base de règles : {len(kb['rules'])} règle(s)")
    ok = yield from prove(goal, 0, frozenset())
    if ok:
        yield _ev("result", f"✔ OBJECTIF DÉMONTRÉ ({stats['rules']} essai(s) de règle, "
                            f"{stats['asked']} question(s)).",
                  success=True, proof=explain(goal, facts0, derived), fired=len(derived))
    else:
        yield _ev("result", f"✘ OBJECTIF NON DÉMONTRÉ ({stats['rules']} essai(s) de règle, "
                            f"{stats['asked']} question(s)).", success=False, proof=[], fired=len(derived))
