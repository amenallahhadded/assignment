# -*- coding: utf-8 -*-
"""
converter.py — Transforme le fichier JSON « automotive_faults » en base de
connaissances (faits + règles SI ... ALORS ...) pour le système expert.

Format source (liste de 99 entrées) :
    {"category": "...", "subcategory": "...",
     "symptoms": ["s1", "s2"],
     "diagnosis_steps": [{"step": "...", "result": ["anormal", "normal"]}, ...]}

Hypothèse vérifiée sur le fichier : result[0] = résultat ANORMAL (défaut),
result[1] = résultat NORMAL.

Règles générées (2 niveaux d'inférence) :
    Niveau 1 (une règle par sous-catégorie) :
        SI  (Symptôme: <s1> OU Symptôme: <s2> ...) ALORS Suspect: <Cat / Sous-cat>
    Niveau 2 (une règle par étape de diagnostic) :
        SI  Suspect: <Cat / Sous-cat>
        ET  Test: <étape> = <résultat anormal>    ALORS Panne: <Cat / Sous-cat>

Format interne de la base de connaissances (kb) :
    {"name": str,
     "initial_facts": [str],
     "rules":   [{"id": "R1", "when": {"all": [{"fact": str}, ...]}, "then": str}],
     "catalog": {fait: {"id": str, "label": str,
                        "type": "symptom|test|test_ok|suspect|fault",
                        "question": str, "source": {...}}},
     "facts": [catalog entries],
     "scenarios": [{"id": str, "facts": [...], "goal": str}],
     "metadata": {"format_version": 2, ...}}

Les libelles restent utilises dans les regles pour conserver la compatibilite
avec l'editeur et les anciennes bases. Les identifiants stables du catalogue
permettent toutefois de referencer les faits sans dependre de leur texte.

Usage en ligne de commande :
    python converter.py data/automotive_faults_aktc_obike_et_al.json knowledge_base.json
"""
import json
import re
import sys
from pathlib import Path


def symptom_fact(s):
    return f"Symptôme: {s}"


def test_fact(step, result):
    return f"Test: {step} = {result}"


def suspect_fact(key):
    return f"Suspect: {key}"


def fault_fact(key):
    return f"Panne: {key}"


def stable_id(prefix, value):
    """Create a readable, stable identifier for a knowledge-base fact."""
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return f"{prefix}_{normalized or 'unnamed'}"


def convert(entries, name="Diagnostic automobile"):
    """Convertit la liste d'entrées automobile en base de connaissances."""
    rules, catalog, entities, scenarios, used_keys = [], {}, [], [], set()
    first_scenario = None
    used_ids = set()

    def register_fact(fact, fact_type, question="", source=None, prefix=None):
        if fact in catalog:
            return catalog[fact]["id"]
        base_id = stable_id(prefix or fact_type, fact.split(": ", 1)[-1])
        fact_id = base_id
        suffix = 2
        while fact_id in used_ids:
            fact_id = f"{base_id}_{suffix}"
            suffix += 1
        used_ids.add(fact_id)
        item = {
            "id": fact_id,
            "label": fact,
            "type": fact_type,
            "question": question,
        }
        if source:
            item["source"] = source
        catalog[fact] = item
        entities.append(item.copy())
        return fact_id

    def new_rule(conds, then):
        rules.append({
            "id": f"R{len(rules) + 1}",
            "when": {"all": [{"fact": fact} for fact in conds]},
            "then": then,
        })

    def new_rule_with_condition(condition, then):
        rules.append({
            "id": f"R{len(rules) + 1}",
            "when": condition,
            "then": then,
        })

    for e in entries:
        key = f"{e['category']} / {e['subcategory']}"
        # Garantir l'unicité (ex. « Fuel Injector » apparaît deux fois)
        if key in used_keys:
            i = 2
            while f"{key} #{i}" in used_keys:
                i += 1
            key = f"{key} #{i}"
        used_keys.add(key)

        suspect, fault = suspect_fact(key), fault_fact(key)
        source = {
            "category": e["category"],
            "subcategory": e["subcategory"],
        }
        register_fact(suspect, "suspect", source=source, prefix="suspect")
        register_fact(fault, "fault", source=source, prefix="fault")

        # Niveau 1 : (symptôme1 OU symptôme2 ...) -> suspect
        symptom_facts = []
        for s in e.get("symptoms", []):
            f = symptom_fact(s)
            symptom_facts.append(f)
            register_fact(
                f,
                "symptom",
                f"Le symptôme suivant est-il observé ?\n\n« {s} »",
                source=source,
                prefix="symptom",
            )
        if symptom_facts:
            new_rule_with_condition(
                {"any": [{"fact": f} for f in symptom_facts]},
                suspect,
            )

        # Niveau 2 : suspect + test anormal -> panne
        first_test = None
        for st in e.get("diagnosis_steps", []):
            results = st["result"]
            abnormal = test_fact(st["step"], results[0])
            register_fact(
                abnormal,
                "test",
                (f"Test : {st['step']}\n\n"
                 f"Le résultat observé est-il « {results[0]} » ?"),
                source={**source, "step": st["step"], "result": results[0]},
                prefix="test",
            )
            for r in results[1:]:                      # résultats normaux (info)
                register_fact(
                    test_fact(st["step"], r),
                    "test_ok",
                    (f"Test : {st['step']}\n\n"
                     f"Le résultat observé est-il « {r} » ?"),
                    source={**source, "step": st["step"], "result": r},
                    prefix="test",
                )
            new_rule([suspect, abnormal], fault)
            first_test = first_test or abnormal

        scenario = {
            "id": stable_id("scenario", key),
            "name": f"{e['category']} / {e['subcategory']}",
            "source": source,
            "goal": fault,
            "facts": [symptom_fact(s) for s in e["symptoms"]] + ([first_test] if first_test else []),
        }
        scenarios.append(scenario)
        if first_scenario is None:  # scénario de démonstration = 1re entrée
            first_scenario = scenario

    kb = {"name": name, "initial_facts": first_scenario["facts"] if first_scenario else [],
          "rules": rules, "catalog": catalog, "facts": entities,
          "scenarios": scenarios,
          "metadata": {
              "format_version": 2,
              "source": "automotive_faults_aktc_obike_et_al.json",
              "fact_model": "label_compatibility_with_stable_ids",
          }}
    kb["demo_goal"] = first_scenario["goal"] if first_scenario else ""
    return kb


def load_kb_file(path):
    """Charge soit un JSON automobile brut (converti), soit une KB déjà au format interne."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, list):
        return convert(data)
    if isinstance(data, dict) and "rules" in data:
        data.setdefault("initial_facts", [])
        data.setdefault("catalog", {})
        data.setdefault("facts", [
            {"id": stable_id("fact", fact), "label": fact, **meta}
            for fact, meta in data["catalog"].items()
        ])
        data.setdefault("scenarios", [])
        data.setdefault("name", Path(path).stem)
        return data
    raise ValueError("Format de fichier non reconnu (ni JSON automobile, ni base de connaissances).")


def save_kb_file(kb, path):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(kb, fh, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    kb = load_kb_file(sys.argv[1])
    save_kb_file(kb, sys.argv[2])
    print(f"{len(kb['rules'])} règles, {len(kb['catalog'])} faits -> {sys.argv[2]}")
