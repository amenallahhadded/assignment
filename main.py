# -*- coding: utf-8 -*-
"""
main.py — Application « Systèmes experts & Algorithmes de recherche » (ENSI, II2)
Module 1 : Système expert de DIAGNOSTIC AUTOMOBILE (Tkinter).

Lancement :  python main.py
"""
import json
import tkinter as tk
from collections.abc import Generator
from tkinter import ttk, messagebox, filedialog
from pathlib import Path

from converter import load_kb_file, save_kb_file
from engine import (forward_chaining, backward_chaining, format_rule, all_facts)
from search_engine import Graph, INFORMED, UNINFORMED, validate

BASE = Path(__file__).resolve().parent
DEFAULT_KB_FILES = [BASE / "knowledge_base.json",
                    BASE / "data" / "automotive_faults_aktc_obike_et_al.json"]

# Couleurs des types d'événements dans la trace
TAGS = {
    "start":    dict(foreground="#0b3d91", font=("Segoe UI", 11, "bold")),
    "cycle":    dict(foreground="#0b3d91", font=("Segoe UI", 10, "bold")),
    "conflict": dict(foreground="#6a6a6a"),
    "info":     dict(foreground="#6a6a6a"),
    "fire":     dict(foreground="#0a7a2f"),
    "goal":     dict(foreground="#6b2fa0", font=("Segoe UI", 10, "bold")),
    "rule":     dict(foreground="#1f5fbf"),
    "known":    dict(foreground="#0a7a2f"),
    "ask":      dict(foreground="#c25e00", font=("Segoe UI", 10, "bold")),
    "success":  dict(foreground="#0a7a2f", font=("Segoe UI", 10, "bold")),
    "fail":     dict(foreground="#b3261e"),
    "ok":       dict(foreground="#0a7a2f", font=("Segoe UI", 11, "bold")),
    "ko":       dict(foreground="#b3261e", font=("Segoe UI", 11, "bold")),
    "proof":    dict(foreground="#222222", font=("Consolas", 10)),
    "answer":   dict(foreground="#c25e00"),
}


# =========================================================================== #
# Boîtes de dialogue
# =========================================================================== #
class FactPicker(tk.Toplevel):
    """Choisir un fait du catalogue (recherche par filtre) ou en saisir un nouveau."""

    def __init__(self, master, facts, title="Choisir un fait", initial=""):
        super().__init__(master)
        self.title(title)
        self.geometry("620x440")
        self.transient(master)
        self.facts = facts
        self.result = None

        ttk.Label(self, text="Filtrer / saisir un fait :").pack(anchor="w", padx=10, pady=(10, 2))
        self.var = tk.StringVar(value=initial)
        ent = ttk.Entry(self, textvariable=self.var)
        ent.pack(fill="x", padx=10)
        ent.focus_set()
        self.var.trace_add("write", lambda *_: self._filter())

        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=10, pady=8)
        self.lb = tk.Listbox(frm, activestyle="dotbox")
        sb = ttk.Scrollbar(frm, command=self.lb.yview)
        self.lb.configure(yscrollcommand=sb.set)
        self.lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.lb.bind("<Double-Button-1>", lambda _: self._ok())

        bt = ttk.Frame(self)
        bt.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Label(bt, text="(sélection dans la liste, sinon le texte saisi est utilisé)",
                  foreground="#666").pack(side="left")
        ttk.Button(bt, text="Annuler", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(bt, text="OK", command=self._ok).pack(side="right")
        self.bind("<Return>", lambda _: self._ok())
        self.bind("<Escape>", lambda _: self.destroy())
        self._filter()
        self.grab_set()
        self.wait_window()

    def _filter(self):
        t = self.var.get().lower()
        self.lb.delete(0, "end")
        for f in self.facts:
            if t in f.lower():
                self.lb.insert("end", f)

    def _ok(self):
        sel = self.lb.curselection()
        self.result = self.lb.get(sel[0]) if sel else self.var.get().strip()
        if self.result:
            self.destroy()


class RuleEditor(tk.Toplevel):
    """Editor for nested JSON conditions, with legacy ``if`` import support."""

    def __init__(self, master, facts, rule=None):
        super().__init__(master)
        self.title("Règle" + (f" {rule['id']}" if rule else " — nouvelle"))
        self.geometry("700x380")
        self.transient(master)
        self.facts = facts
        self.result = None

        ttk.Label(self, text="SI (condition JSON : all / any / not / fact) :").pack(
            anchor="w", padx=10, pady=(10, 2))
        self.txt = tk.Text(self, height=8, wrap="word")
        self.txt.pack(fill="both", expand=True, padx=10)
        if rule:
            condition = rule.get("when")
            if condition is None:
                condition = {"all": [{"fact": f} for f in rule.get("if", [])]}
            self.txt.insert("1.0", json.dumps(condition, ensure_ascii=False, indent=2))
        else:
            self.txt.insert("1.0", '{\n  "all": [\n    {"fact": ""}\n  ]\n}')
        ttk.Button(self, text="＋ Insérer un fait du catalogue…", command=self._insert).pack(
            anchor="w", padx=10, pady=4)
        ttk.Label(self, text="ALORS (conclusion) :").pack(anchor="w", padx=10)
        self.concl = tk.StringVar(value=rule["then"] if rule else "")
        ttk.Entry(self, textvariable=self.concl).pack(fill="x", padx=10, pady=(2, 8))
        bt = ttk.Frame(self)
        bt.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(bt, text="Annuler", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(bt, text="Enregistrer", command=self._ok).pack(side="right")
        self.grab_set()
        self.wait_window()

    def _insert(self):
        p = FactPicker(self, self.facts, "Insérer un fait")
        if p.result:
            cur = self.txt.get("1.0", "end").strip()
            try:
                condition = json.loads(cur)
                if isinstance(condition, dict) and isinstance(condition.get("all"), list):
                    condition["all"].append({"fact": p.result})
                    self.txt.delete("1.0", "end")
                    self.txt.insert("1.0", json.dumps(condition, ensure_ascii=False, indent=2))
                    return
            except json.JSONDecodeError:
                pass
            self.txt.insert("end", ("\n" if cur else "") + p.result)

    def _ok(self):
        raw = self.txt.get("1.0", "end").strip()
        then = self.concl.get().strip()
        try:
            condition = json.loads(raw)
        except json.JSONDecodeError:
            # Keep old, line-oriented rules easy to edit and migrate.
            conds = [l.strip() for l in raw.splitlines() if l.strip()]
            condition = {"all": [{"fact": f} for f in conds]}
        if not then or not isinstance(condition, dict):
            messagebox.showwarning("Règle incomplète", "Il faut au moins une condition et une conclusion.", parent=self)
            return
        from engine import condition_facts
        if not condition_facts(condition):
            messagebox.showwarning("Règle incomplète", "La condition doit contenir au moins un fait.", parent=self)
            return
        if then in condition_facts(condition):
            messagebox.showwarning("Règle invalide", "La conclusion ne peut pas être une de ses conditions.", parent=self)
            return
        self.result = (condition, then)
        self.destroy()


# =========================================================================== #
# Module 1 — Système expert
# =========================================================================== #
class ExpertSystemFrame(ttk.Frame):
    def __init__(self, master, on_back):
        super().__init__(master)
        self.on_back = on_back
        self.kb = {"name": "Base vide", "initial_facts": [], "rules": [], "catalog": {}}
        self.facts_init = []          # base de faits INITIALE (éditable)
        self.goal_var = tk.StringVar()
        self.method_var = tk.StringVar(value="forward")
        self._reset_state()
        self._build()
        self._load_default_kb()

    # ------------------------------------------------------------------ état
    def _reset_state(self):
        self.gen: Generator[dict, object, None] | None = None
        self.work_facts = set()
        self.derived = {}
        self.pending_answer = None
        self.finished = False
        self.step_count = 0
        self.run_cfg = None

    # ------------------------------------------------------------------- UI
    def _build(self):
        top = ttk.Frame(self, style="Card.TFrame", padding=(12, 10))
        top.pack(fill="x", padx=12, pady=(12, 8))
        ttk.Button(top, text="←  Menu principal", command=self.on_back,
                   style="Secondary.TButton").pack(side="left")
        self.title_lbl = ttk.Label(top, text="", style="Module.TLabel")
        self.title_lbl.pack(side="left", padx=18)
        ttk.Label(top, text="Gestion des faits, règles et raisonnement",
                  foreground="#657786").pack(side="right", padx=8)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.tab_kb = ttk.Frame(nb)
        self.tab_run = ttk.Frame(nb)
        nb.add(self.tab_kb, text="  1. Présentation / Base de connaissances  ")
        nb.add(self.tab_run, text="  2. Raisonnement  ")
        self.nb = nb
        self._build_kb_tab()
        self._build_run_tab()

    def _build_kb_tab(self):
        t = self.tab_kb
        bar = ttk.Frame(t)
        bar.pack(fill="x", pady=6, padx=6)
        ttk.Button(bar, text="📥 Importer JSON automobile…", command=self.import_json).pack(side="left", padx=2)
        ttk.Button(bar, text="📂 Ouvrir une base…", command=self.open_kb).pack(side="left", padx=2)
        ttk.Button(bar, text="💾 Enregistrer la base…", command=self.save_kb).pack(side="left", padx=2)

        pan = ttk.PanedWindow(t, orient="horizontal")
        pan.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        # --- Faits
        lf = ttk.LabelFrame(pan, text="Base de faits initiale")
        pan.add(lf, weight=1)
        self.facts_lb = tk.Listbox(lf, selectmode="extended", activestyle="none")
        sb = ttk.Scrollbar(lf, command=self.facts_lb.yview)
        self.facts_lb.configure(yscrollcommand=sb.set)
        bt = ttk.Frame(lf)
        bt.pack(side="bottom", fill="x", pady=4)
        ttk.Button(bt, text="Ajouter", command=self.add_fact).pack(side="left", padx=2)
        ttk.Button(bt, text="Modifier", command=self.edit_fact).pack(side="left", padx=2)
        ttk.Button(bt, text="Supprimer", command=self.del_fact).pack(side="left", padx=2)
        ttk.Button(bt, text="Vider", command=self.clear_facts).pack(side="left", padx=2)
        sb.pack(side="right", fill="y")
        self.facts_lb.pack(side="left", fill="both", expand=True)
        self.facts_lb.bind("<Double-Button-1>", lambda _: self.edit_fact())

        # --- Règles
        rf = ttk.LabelFrame(pan, text="Base de règles  (SI conditions ALORS conclusion)")
        pan.add(rf, weight=5)
        # Position initiale du séparateur (en pixels depuis le bord gauche).
        # Modifier FACTS_PANE_WIDTH pour réduire ou agrandir la zone des faits.
        FACTS_PANE_WIDTH = 250
        pan.after(500, lambda: pan.sashpos(0, FACTS_PANE_WIDTH))
        fr = ttk.Frame(rf)
        fr.pack(fill="x", padx=4, pady=4)
        ttk.Label(fr, text="Filtrer :").pack(side="left")
        self.rule_filter = tk.StringVar()
        self.rule_filter.trace_add("write", lambda *_: self.refresh_rules())
        ttk.Entry(fr, textvariable=self.rule_filter).pack(side="left", fill="x", expand=True, padx=4)
        self.rule_count = ttk.Label(fr, text="")
        self.rule_count.pack(side="right")

        bt2 = ttk.Frame(rf)
        bt2.pack(side="bottom", fill="x", pady=4)
        ttk.Button(bt2, text="Ajouter", command=self.add_rule).pack(side="left", padx=2)
        ttk.Button(bt2, text="Modifier", command=self.edit_rule).pack(side="left", padx=2)
        ttk.Button(bt2, text="Supprimer", command=self.del_rule).pack(side="left", padx=2)

        cols = ("id", "si", "alors")
        body = ttk.Frame(rf)
        body.pack(fill="both", expand=True)
        self.rules_tv = ttk.Treeview(body, columns=cols, show="headings", selectmode="extended")
        self.rules_tv.heading("id", text="ID")
        self.rules_tv.heading("si", text="SI (conditions)")
        self.rules_tv.heading("alors", text="ALORS (conclusion)")
        self.rules_tv.column("id", width=50, stretch=False)
        self.rules_tv.column("si", width=750, minwidth=260)
        self.rules_tv.column("alors", width=260)
        sb2 = ttk.Scrollbar(body, command=self.rules_tv.yview)
        sbx = ttk.Scrollbar(rf, orient="horizontal", command=self.rules_tv.xview)
        self.rules_tv.configure(yscrollcommand=sb2.set, xscrollcommand=sbx.set)
        sbx.pack(side="bottom", fill="x")
        sb2.pack(side="right", fill="y")
        self.rules_tv.pack(side="left", fill="both", expand=True)
        self.rules_tv.bind("<Double-Button-1>", lambda _: self.edit_rule())

    def _build_run_tab(self):
        t = self.tab_run
        cfg = ttk.LabelFrame(t, text="Paramètres du raisonnement")
        cfg.pack(fill="x", padx=6, pady=6)

        r1 = ttk.Frame(cfg)
        r1.pack(fill="x", padx=6, pady=4)
        ttk.Label(r1, text="Objectif à démontrer :").pack(side="left")
        self.goal_cb = ttk.Combobox(r1, textvariable=self.goal_var, width=70)
        self.goal_cb.pack(side="left", padx=6, fill="x", expand=True)
        self.goal_cb.bind("<KeyRelease>", self._filter_goals)
        self.goal_cb.bind("<<ComboboxSelected>>", lambda _: self._on_config_change())
        self.goal_cb.bind("<Return>", lambda _: self._on_config_change())
        ttk.Button(r1, text="Panne…", width=8, command=self._pick_goal).pack(side="left")
        self.goal_status = ttk.Label(r1, text="", width=40)
        self.goal_status.pack(side="left", padx=6)

        r2 = ttk.Frame(cfg)
        r2.pack(fill="x", padx=6, pady=4)
        ttk.Label(r2, text="Méthode :").pack(side="left")
        ttk.Radiobutton(r2, text="Chaînage avant (Forward)", variable=self.method_var, value="forward",
                        command=self._on_config_change).pack(side="left", padx=8)
        ttk.Radiobutton(r2, text="Chaînage arrière (Backward)", variable=self.method_var, value="backward",
                        command=self._on_config_change).pack(side="left", padx=8)
        ttk.Separator(r2, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(r2, text="▶ Étape suivante", command=self.step).pack(side="left", padx=3)
        ttk.Button(r2, text="⏩ Tout exécuter", command=self.run_all).pack(side="left", padx=3)
        ttk.Button(r2, text="↺ Réinitialiser", command=self.reset_run).pack(side="left", padx=3)
        ttk.Button(r2, text="🧹 Effacer la trace", command=self.clear_trace).pack(side="left", padx=3)

        pan = ttk.PanedWindow(t, orient="horizontal")
        pan.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        lf = ttk.LabelFrame(pan, text="Trace du raisonnement")
        pan.add(lf, weight=4)
        self.trace = tk.Text(lf, wrap="word", font=("Segoe UI", 10), state="disabled", background="#fbfbfb")
        sb = ttk.Scrollbar(lf, command=self.trace.yview)
        self.trace.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.trace.pack(fill="both", expand=True)
        for k, v in TAGS.items():
            self.trace.tag_configure(k, **v)

        ff = ttk.LabelFrame(pan, text="Faits courants (base de travail)")
        pan.add(ff, weight=1)
        self.work_lb = tk.Listbox(ff, activestyle="none")
        sb3 = ttk.Scrollbar(ff, command=self.work_lb.yview)
        self.work_lb.configure(yscrollcommand=sb3.set)
        sb3.pack(side="right", fill="y")
        self.work_lb.pack(fill="both", expand=True)

        self.status = ttk.Label(t, text="Choisissez un objectif et une méthode, puis « Étape suivante ».",
                                foreground="#444")
        self.status.pack(fill="x", padx=8, pady=(0, 6))

    # ------------------------------------------------------- chargement KB
    def _load_default_kb(self):
        for p in DEFAULT_KB_FILES:
            if p.exists():
                try:
                    self.set_kb(load_kb_file(p))
                    return
                except Exception as exc:                   # pragma: no cover
                    messagebox.showerror("Chargement", f"{p.name} : {exc}")
        self.set_kb(self.kb)

    def set_kb(self, kb):
        self.kb = kb
        self.facts_init = list(kb.get("initial_facts", []))
        self.title_lbl.configure(text=f"Système expert — {kb.get('name', '')}")
        self._all = all_facts(kb)
        # « Panne: » en tête pour retrouver facilement les objectifs de diagnostic
        self._goals = sorted(self._all, key=lambda f: (not f.startswith("Panne:"), f))
        self.goal_cb["values"] = self._goals
        if kb.get("demo_goal"):
            self.goal_var.set(kb["demo_goal"])
        elif self.goal_var.get() not in self._all:
            self.goal_var.set("")
        self.refresh_facts()
        self.refresh_rules()
        self.reset_run()

    def _touch_kb(self):
        self._all = all_facts(self.kb)
        self._goals = sorted(self._all, key=lambda f: (not f.startswith("Panne:"), f))
        self.goal_cb["values"] = self._goals
        self.kb["initial_facts"] = list(self.facts_init)
        self.refresh_facts()
        self.refresh_rules()
        self.reset_run()

    def import_json(self):
        p = filedialog.askopenfilename(title="JSON automobile", filetypes=[("JSON", "*.json")])
        if p:
            try:
                self.set_kb(load_kb_file(p))
            except Exception as exc:
                messagebox.showerror("Import", str(exc))

    open_kb = import_json

    def save_kb(self):
        p = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")],
                                         initialfile="knowledge_base.json")
        if p:
            self.kb["initial_facts"] = list(self.facts_init)
            save_kb_file(self.kb, p)
            messagebox.showinfo("Enregistrement", f"Base enregistrée :\n{p}")

    # ----------------------------------------------------------------- faits
    def refresh_facts(self):
        self.facts_lb.delete(0, "end")
        for f in self.facts_init:
            self.facts_lb.insert("end", f)
        self._update_goal_status()

    def add_fact(self):
        p = FactPicker(self, self._all, "Ajouter un fait à la base de faits")
        if p.result and p.result not in self.facts_init:
            self.facts_init.append(p.result)
            self._touch_kb()

    def edit_fact(self):
        sel = self.facts_lb.curselection()
        if not sel:
            return
        i = sel[0]
        p = FactPicker(self, self._all, "Modifier le fait", initial=self.facts_init[i])
        if p.result:
            self.facts_init[i] = p.result
            self._touch_kb()

    def del_fact(self):
        for i in reversed(self.facts_lb.curselection()):
            del self.facts_init[i]
        self._touch_kb()

    def clear_facts(self):
        if self.facts_init and messagebox.askyesno("Vider", "Supprimer tous les faits initiaux ?"):
            self.facts_init = []
            self._touch_kb()

    # ---------------------------------------------------------------- règles
    def refresh_rules(self):
        t = self.rule_filter.get().lower()
        self.rules_tv.delete(*self.rules_tv.get_children())
        n = 0
        for r in self.kb["rules"]:
            si = format_rule(r).split(": SI ", 1)[1].rsplit(" ALORS ", 1)[0]
            if t and t not in (si + " " + r["then"] + " " + r["id"]).lower():
                continue
            self.rules_tv.insert("", "end", iid=r["id"], values=(r["id"], "SI  " + si, "ALORS  " + r["then"]))
            n += 1
        self.rule_count.configure(text=f"{n} / {len(self.kb['rules'])} règle(s)")

    def _next_rule_id(self):
        nums = [int(r["id"][1:]) for r in self.kb["rules"] if r["id"][1:].isdigit()]
        return f"R{max(nums, default=0) + 1}"

    def add_rule(self):
        ed = RuleEditor(self, self._all)
        if ed.result:
            self.kb["rules"].append({"id": self._next_rule_id(), "when": ed.result[0], "then": ed.result[1]})
            self._touch_kb()

    def edit_rule(self):
        sel = self.rules_tv.selection()
        if not sel:
            return
        rule = next(r for r in self.kb["rules"] if r["id"] == sel[0])
        ed = RuleEditor(self, self._all, rule)
        if ed.result:
            rule["when"], rule["then"] = ed.result
            self._touch_kb()

    def del_rule(self):
        sel = set(self.rules_tv.selection())
        if sel and messagebox.askyesno("Supprimer", f"Supprimer {len(sel)} règle(s) ?"):
            self.kb["rules"] = [r for r in self.kb["rules"] if r["id"] not in sel]
            self._touch_kb()

    # ------------------------------------------------------------- objectif
    def _filter_goals(self, event):
        if event.keysym in ("Up", "Down", "Return", "Escape", "Tab"):
            return
        t = self.goal_var.get().lower()
        self.goal_cb["values"] = [g for g in self._goals if t in g.lower()] or self._goals
        self._update_goal_status()

    def _pick_goal(self):
        p = FactPicker(self, [g for g in self._goals if g.startswith("Panne:")] or self._goals,
                       "Choisir l'objectif (panne à démontrer)")
        if p.result:
            self.goal_var.set(p.result)
            self._on_config_change()

    def _update_goal_status(self):
        g = self.goal_var.get().strip()
        if not g:
            self.goal_status.configure(text="", foreground="#444")
        elif g in self.facts_init:
            self.goal_status.configure(text="✔ Déjà présent dans la base de faits", foreground="#0a7a2f")
        elif any(r["then"] == g for r in self.kb["rules"]):
            self.goal_status.configure(text="✘ Absent — à démontrer", foreground="#b3261e")
        else:
            self.goal_status.configure(text="✘ Absent (aucune règle ne le conclut)", foreground="#b3261e")

    def _on_config_change(self):
        """Changement d'objectif / méthode : on repart de zéro, sans relancer l'application."""
        self._update_goal_status()
        if self.run_cfg is not None and self.run_cfg != (self.goal_var.get().strip(), self.method_var.get()):
            self.reset_run(keep_trace=True)
            self._write("\n— Configuration modifiée : raisonnement réinitialisé —\n", "info")

    # --------------------------------------------------------- raisonnement
    def _write(self, text, tag="info"):
        self.trace.configure(state="normal")
        self.trace.insert("end", text, tag)
        self.trace.see("end")
        self.trace.configure(state="disabled")

    def clear_trace(self):
        self.trace.configure(state="normal")
        self.trace.delete("1.0", "end")
        self.trace.configure(state="disabled")

    def _refresh_work(self):
        self.work_lb.delete(0, "end")
        for f in sorted(self.work_facts):
            self.work_lb.insert("end", f)
            if f in self.derived:
                self.work_lb.itemconfig("end", foreground="#0a7a2f")
            elif f not in self.facts_init:
                self.work_lb.itemconfig("end", foreground="#c25e00")

    def reset_run(self, keep_trace=False):
        self._reset_state()
        self.work_facts = set(self.facts_init)
        self._refresh_work()
        self._update_goal_status()
        if not keep_trace:
            self.clear_trace()
        self.status.configure(text="Prêt. Cliquez sur « Étape suivante » ou « Tout exécuter ».")

    def _start(self):
        goal = self.goal_var.get().strip()
        if not goal:
            messagebox.showwarning("Objectif", "Veuillez choisir un objectif à démontrer.")
            return False
        if not self.kb["rules"]:
            messagebox.showwarning("Base vide", "La base de règles est vide.")
            return False
        cfg = (goal, self.method_var.get())
        if self.run_cfg != cfg or self.gen is None:
            self.reset_run(keep_trace=True)
            self.run_cfg = cfg
            fn = forward_chaining if cfg[1] == "forward" else backward_chaining
            self.gen = fn(self.kb, self.work_facts, goal, self.derived)
            self._write("\n" + "═" * 70 + "\n", "info")
        return True

    def step(self):
        """Exécute UNE étape de raisonnement. Retourne False si terminé."""
        if self.finished:
            self.status.configure(text="Raisonnement terminé — modifiez l'objectif/méthode ou réinitialisez.")
            return False
        if not self._start():
            return False
        try:
            ans, self.pending_answer = self.pending_answer, None
            generator = self.gen
            if generator is None:
                return False
            ev = generator.send(ans)
        except StopIteration:
            self.finished = True
            return False
        self.step_count += 1
        self._show(ev)
        self._refresh_work()
        return not self.finished

    def _show(self, ev):
        t = ev["type"]
        indent = "     " * ev.get("depth", 0)
        if t == "result":
            self._write("\n" + ev["msg"] + "\n", "ok" if ev["success"] else "ko")
            if ev["proof"]:
                self._write("\nJustification (arbre de preuve) :\n", "goal")
                self._write("\n".join(ev["proof"]) + "\n", "proof")
            self.finished = True
            self.status.configure(text=f"Terminé en {self.step_count} étape(s).")
            return
        self._write(f"{indent}{ev['msg']}", t)
        if t == "ask":
            ans = messagebox.askyesno("Question du système expert", ev["question"], parent=self)
            self.pending_answer = ans
            self._write(f"   →  {'OUI' if ans else 'NON'}", "answer")
        self._write("\n", t)
        self.status.configure(text=f"Étape {self.step_count}")

    def run_all(self):
        n = 0
        while self.step() and n < 200000:
            n += 1
        self.update_idletasks()


# =========================================================================== #
# Module 2 — Algorithmes de recherche
# =========================================================================== #
class SearchFrame(ttk.Frame):
    """Interface pas-à-pas pour les algorithmes du module ``search_engine``."""

    def __init__(self, master, on_back):
        super().__init__(master)
        self.on_back = on_back
        self.graph = Graph.example()
        self._algorithms = {**UNINFORMED, **INFORMED}
        self._gen: Generator[dict, None, None] | None = None
        self._finished = False
        self._step_count = 0
        self._final_path = []
        self._build()
        self._refresh_summary()

    def _build(self):
        top = ttk.Frame(self, style="Card.TFrame", padding=(12, 10))
        top.pack(fill="x", padx=12, pady=(12, 8))
        ttk.Button(top, text="←  Menu principal", command=self.on_back,
                   style="Secondary.TButton").pack(side="left")
        ttk.Label(top, text="Algorithmes de recherche", style="Module.TLabel").pack(
            side="left", padx=18
        )
        ttk.Label(top, text="Graphes orientés · exploration pas à pas",
                  foreground="#657786").pack(side="right", padx=8)

        cfg = ttk.LabelFrame(self, text="Paramètres de la recherche")
        cfg.pack(fill="x", padx=8, pady=(0, 6))
        row = ttk.Frame(cfg)
        row.pack(fill="x", padx=6, pady=5)
        ttk.Label(row, text="Type :").pack(side="left")
        self.category_var = tk.StringVar(value="informed")
        ttk.Radiobutton(row, text="Non informée", variable=self.category_var,
                        value="uninformed", command=self._category_changed).pack(side="left", padx=3)
        ttk.Radiobutton(row, text="Informée", variable=self.category_var,
                        value="informed", command=self._category_changed).pack(side="left", padx=3)
        ttk.Label(row, text="Algorithme :").pack(side="left", padx=(12, 0))
        self.algorithm_var = tk.StringVar(value=next(iter(self._algorithms)))
        self.algorithm_cb = ttk.Combobox(
            row, textvariable=self.algorithm_var, values=list(INFORMED),
            state="readonly", width=32
        )
        self.algorithm_cb.pack(side="left", padx=6)
        self.algorithm_cb.bind("<<ComboboxSelected>>", lambda _: self._reset_run())
        ttk.Label(row, text="Limite DLS :").pack(side="left", padx=(14, 2))
        self.limit_var = tk.StringVar(value="3")
        self.limit_entry = ttk.Entry(row, textvariable=self.limit_var, width=6)
        self.limit_entry.pack(side="left")
        self.limit_entry.bind("<Return>", lambda _: self._reset_run())
        ttk.Label(row, text="Mémoire SBA* :").pack(side="left", padx=(8, 2))
        self.memory_var = tk.StringVar(value="32")
        self.memory_entry = ttk.Entry(row, textvariable=self.memory_var, width=6)
        self.memory_entry.pack(side="left")
        self.memory_entry.bind("<Return>", lambda _: self._reset_run())
        ttk.Button(row, text="▶ Étape suivante", command=self.step).pack(side="left", padx=(16, 3))
        ttk.Button(row, text="⏩ Tout exécuter", command=self.run_all).pack(side="left", padx=3)
        ttk.Button(row, text="↺ Réinitialiser", command=self._reset_run).pack(side="left", padx=3)

        self.validation = ttk.Label(cfg, text="", foreground="#444")
        self.validation.pack(fill="x", padx=6, pady=(0, 5))

        edit = ttk.LabelFrame(self, text="Construction du graphe")
        edit.pack(fill="x", padx=8, pady=(0, 6))
        erow = ttk.Frame(edit)
        erow.pack(fill="x", padx=6, pady=4)
        ttk.Button(erow, text="＋ Sommet", command=self._add_node).pack(side="left", padx=2)
        ttk.Button(erow, text="＋ Arc", command=self._add_edge).pack(side="left", padx=2)
        ttk.Button(erow, text="Graphe exemple", command=self._load_example).pack(side="left", padx=2)
        ttk.Label(erow, text="Départ :").pack(side="left", padx=(12, 2))
        self.start_var = tk.StringVar(value=self.graph.start or "")
        self.start_cb = ttk.Combobox(erow, textvariable=self.start_var, state="readonly", width=10)
        self.start_cb.pack(side="left")
        self.start_cb.bind("<<ComboboxSelected>>", lambda _: self._set_endpoint("start"))
        ttk.Label(erow, text="Objectif :").pack(side="left", padx=(8, 2))
        self.goal_node_var = tk.StringVar(value=self.graph.goal or "")
        self.goal_node_cb = ttk.Combobox(erow, textvariable=self.goal_node_var, state="readonly", width=10)
        self.goal_node_cb.pack(side="left")
        self.goal_node_cb.bind("<<ComboboxSelected>>", lambda _: self._set_endpoint("goal"))

        lists = ttk.PanedWindow(edit, orient="horizontal")
        lists.pack(fill="x", padx=6, pady=(0, 5))
        nodes_box = ttk.LabelFrame(lists, text="Sommets (double-clic pour modifier)")
        edges_box = ttk.LabelFrame(lists, text="Arcs orientés (double-clic pour modifier)")
        lists.add(nodes_box, weight=1)
        lists.add(edges_box, weight=2)
        self.nodes_tv = ttk.Treeview(nodes_box, columns=("name", "h", "position"),
                                     show="headings", height=4, selectmode="browse")
        for col, title, width in (("name", "Nom", 120), ("h", "h(n)", 70), ("position", "Position", 110)):
            self.nodes_tv.heading(col, text=title)
            self.nodes_tv.column(col, width=width, stretch=True)
        self.nodes_tv.pack(side="left", fill="both", expand=True)
        self.nodes_tv.bind("<Double-1>", lambda _: self._edit_node())
        node_buttons = ttk.Frame(nodes_box)
        node_buttons.pack(side="right", fill="y")
        ttk.Button(node_buttons, text="Ajouter", command=self._add_node).pack(pady=1)
        ttk.Button(node_buttons, text="Modifier", command=self._edit_node).pack(pady=1)
        ttk.Button(node_buttons, text="Supprimer", command=self._remove_node).pack(pady=1)
        self.edges_tv = ttk.Treeview(edges_box, columns=("from", "to", "cost"),
                                     show="headings", height=4, selectmode="browse")
        for col, title, width in (("from", "Départ", 100), ("to", "Arrivée", 100), ("cost", "Coût", 70)):
            self.edges_tv.heading(col, text=title)
            self.edges_tv.column(col, width=width, stretch=True)
        self.edges_tv.pack(side="left", fill="both", expand=True)
        self.edges_tv.bind("<Double-1>", lambda _: self._edit_edge())
        edge_buttons = ttk.Frame(edges_box)
        edge_buttons.pack(side="right", fill="y")
        ttk.Button(edge_buttons, text="Ajouter", command=self._add_edge).pack(pady=1)
        ttk.Button(edge_buttons, text="Modifier", command=self._edit_edge).pack(pady=1)
        ttk.Button(edge_buttons, text="Supprimer", command=self._remove_edge).pack(pady=1)

        pan = ttk.PanedWindow(self, orient="horizontal")
        pan.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        trace_frame = ttk.LabelFrame(pan, text="Trace de la recherche")
        pan.add(trace_frame, weight=4)
        self.trace = tk.Text(trace_frame, wrap="word", state="disabled",
                             font=("Segoe UI", 10), background="#fbfbfb")
        trace_scroll = ttk.Scrollbar(trace_frame, command=self.trace.yview)
        self.trace.configure(yscrollcommand=trace_scroll.set)
        trace_scroll.pack(side="right", fill="y")
        self.trace.pack(fill="both", expand=True)

        side = ttk.Frame(pan)
        pan.add(side, weight=2)
        summary_frame = ttk.LabelFrame(side, text="Graphe construit")
        summary_frame.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(summary_frame, height=230, background="white", highlightthickness=1,
                                highlightbackground="#cccccc")
        self.canvas.pack(fill="both", expand=True, padx=4, pady=4)
        self.summary = tk.Text(summary_frame, height=7, wrap="word", state="disabled",
                               font=("Consolas", 9))
        self.summary.pack(fill="both", expand=True, padx=4, pady=4)
        state_frame = ttk.LabelFrame(side, text="État courant")
        state_frame.pack(fill="both", expand=True, pady=(6, 0))
        self.state_text = tk.Text(state_frame, height=8, wrap="word", state="disabled",
                                  font=("Consolas", 9))
        self.state_text.pack(fill="both", expand=True, padx=4, pady=4)
        self.status = ttk.Label(self, text="Choisissez un algorithme puis lancez une étape.",
                                foreground="#444")
        self.status.pack(fill="x", padx=10, pady=(0, 6))

    def _set_text(self, widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _refresh_summary(self):
        edges = "\n".join(f"  {u} → {v}  (coût {c:g})"
                          for (u, v), c in sorted(self.graph.edges.items()))
        hs = ", ".join(f"{n}={h:g}" for n, h in sorted(self.graph.h.items()))
        self._set_text(
            self.summary,
            f"Sommets ({len(self.graph.nodes)}) : {', '.join(sorted(self.graph.nodes))}\n"
            f"Départ : {self.graph.start}\nObjectif : {self.graph.goal}\n"
            f"Heuristiques h(n) : {hs}\n\nArcs ({len(self.graph.edges)}) :\n{edges}"
        )
        values = sorted(self.graph.nodes)
        self.start_cb.configure(values=values)
        self.goal_node_cb.configure(values=values)
        self.start_var.set(self.graph.start or "")
        self.goal_node_var.set(self.graph.goal or "")
        self._refresh_lists()
        self._draw_graph()

    def _refresh_lists(self):
        for tv in (self.nodes_tv, self.edges_tv):
            tv.delete(*tv.get_children())
        for name, (x, y) in sorted(self.graph.nodes.items()):
            h = self.graph.h.get(name, "")
            h = f"{h:g}" if h != "" else "—"
            self.nodes_tv.insert("", "end", iid=name, values=(name, h, f"{x:g}, {y:g}"))
        for (u, v), cost in sorted(self.graph.edges.items()):
            iid = f"{u}\0{v}"
            self.edges_tv.insert("", "end", iid=iid,
                                 values=(u, v, f"{cost:g}"))

    def _draw_graph(self):
        self.canvas.delete("all")
        if not self.graph.nodes:
            self.canvas.create_text(150, 100, text="Graphe vide", fill="#666")
            return
        width = max(self.canvas.winfo_width(), 300)
        height = max(self.canvas.winfo_height(), 180)
        positions: dict[str, tuple[float, float]] = {}
        for _, node in enumerate(sorted(self.graph.nodes)):
            x, y = self.graph.nodes[node]
            positions[node] = (40 + (x / 700) * (width - 80), 30 + (y / 380) * (height - 60))
        highlighted = set(zip(self._final_path, self._final_path[1:]))
        radius = 21
        for (u, v), cost in self.graph.edges.items():
            x1, y1 = positions[u]
            x2, y2 = positions[v]
            dx, dy = x2 - x1, y2 - y1
            length = max((dx * dx + dy * dy) ** 0.5, 1)
            ux, uy = dx / length, dy / length
            sx, sy = x1 + ux * radius, y1 + uy * radius
            ex, ey = x2 - ux * radius, y2 - uy * radius

            # Separate opposite arcs so each arrowhead remains unambiguous.
            reverse = (v, u) in self.graph.edges
            offset = 7 if reverse and u < v else (-7 if reverse else 0)
            px, py = -uy * offset, ux * offset
            points = (sx + px, sy + py, ex + px, ey + py)
            is_path = (u, v) in highlighted
            self.canvas.create_line(
                *points, arrow=tk.LAST, arrowshape=(12, 14, 5),
                fill="#d22" if is_path else "#526777",
                width=3 if is_path else 2,
            )
            label_x = (sx + ex) / 2 + px
            label_y = (sy + ey) / 2 + py - 8
            self.canvas.create_text(
                label_x, label_y,
                text=str(int(cost) if cost.is_integer() else cost),
                fill="#334e60", font=("Segoe UI", 9, "bold"),
            )
        for node, (x, y) in positions.items():
            fill = "#b8e0ff" if node not in (self.graph.start, self.graph.goal) else (
                "#b9f6ca" if node == self.graph.start else "#ffd1d1")
            self.canvas.create_oval(x-radius, y-radius, x+radius, y+radius,
                                    fill=fill, outline="#1f5fbf", width=2)
            self.canvas.create_text(x, y, text=node, fill="#17324d",
                                    font=("Segoe UI", 10, "bold"))
            h_value = self.graph.h.get(node)
            h_label = "h=—" if h_value is None else f"h={h_value:g}"
            self.canvas.create_text(x, y - radius - 10, text=f"({h_label})",
                                    fill="#17324d", font=("Segoe UI", 9, "bold"))

    def _category_changed(self):
        values = list(UNINFORMED if self.category_var.get() == "uninformed" else INFORMED)
        self.algorithm_cb.configure(values=values)
        self.algorithm_var.set(values[0])
        self._reset_run()

    def _graph_changed(self):
        self._reset_run()
        self._refresh_summary()

    def _add_node(self):
        self._node_dialog()

    def _edit_node(self):
        selected = self.nodes_tv.selection()
        if not selected:
            messagebox.showinfo("Sommet", "Sélectionnez un sommet à modifier.", parent=self)
            return
        self._node_dialog(selected[0])

    def _node_dialog(self, old_name=None):
        win = tk.Toplevel(self)
        win.title("Modifier le sommet" if old_name else "Ajouter un sommet")
        win.transient(self.winfo_toplevel())
        win.grab_set()
        name_var = tk.StringVar(value=old_name or "")
        x0, y0 = self.graph.nodes.get(old_name, (100, 100))
        x_var, y_var = tk.StringVar(value=str(x0)), tk.StringVar(value=str(y0))
        h_var = tk.StringVar(value="" if old_name is None or old_name not in self.graph.h
                             else str(self.graph.h[old_name]))
        for row, label, var in ((0, "Nom :", name_var), (1, "Position X :", x_var),
                                (2, "Position Y :", y_var), (3, "h(n) (optionnelle) :", h_var)):
            ttk.Label(win, text=label).grid(row=row, column=0, padx=8, pady=4, sticky="w")
            ttk.Entry(win, textvariable=var, width=24).grid(row=row, column=1, padx=8, pady=4)
        def save():
            try:
                name = name_var.get().strip()
                x, y = float(x_var.get()), float(y_var.get())
                h_text = h_var.get().strip()
                h = None if not h_text else float(h_text)
                if old_name is not None and name != old_name:
                    if name in self.graph.nodes:
                        raise ValueError(f"Le sommet « {name} » existe déjà.")
                    self.graph.nodes[name] = self.graph.nodes.pop(old_name)
                    if old_name in self.graph.h:
                        self.graph.h[name] = self.graph.h.pop(old_name)
                    self.graph.edges = {
                        (name if u == old_name else u, name if v == old_name else v): c
                        for (u, v), c in self.graph.edges.items()
                    }
                    if self.graph.start == old_name:
                        self.graph.start = name
                    if self.graph.goal == old_name:
                        self.graph.goal = name
                if old_name is None:
                    self.graph.add_node(name, x, y, h)
                else:
                    self.graph.nodes[name] = (x, y)
                    self.graph.set_h(name, h)
                win.destroy()
                self._graph_changed()
            except (TypeError, ValueError) as exc:
                messagebox.showerror("Sommet invalide", str(exc), parent=win)
        ttk.Button(win, text="Annuler", command=win.destroy).grid(row=4, column=0, padx=8, pady=8)
        ttk.Button(win, text="Enregistrer", command=save).grid(row=4, column=1, padx=8, pady=8)
        win.wait_window()

    def _add_edge(self):
        nodes = sorted(self.graph.nodes)
        if len(nodes) < 2:
            messagebox.showerror("Arc impossible", "Ajoutez au moins deux sommets.", parent=self)
            return
        self._edge_dialog()

    def _edit_edge(self):
        selected = self.edges_tv.selection()
        if not selected:
            messagebox.showinfo("Arc", "Sélectionnez un arc à modifier.", parent=self)
            return
        u, v = selected[0].split("\0")
        self._edge_dialog((u, v))

    def _edge_dialog(self, old_edge=None):
        win = tk.Toplevel(self)
        win.title("Modifier l'arc" if old_edge else "Ajouter un arc")
        win.transient(self.winfo_toplevel())
        win.grab_set()
        nodes = sorted(self.graph.nodes)
        u0, v0 = old_edge or (nodes[0], nodes[1])
        u_var, v_var = tk.StringVar(value=u0), tk.StringVar(value=v0)
        cost_var = tk.StringVar(value=str(self.graph.edges.get(old_edge, 1)))
        for row, label, var in ((0, "Départ :", u_var), (1, "Arrivée :", v_var), (2, "Coût :", cost_var)):
            ttk.Label(win, text=label).grid(row=row, column=0, padx=8, pady=5, sticky="w")
            if row < 2:
                ttk.Combobox(win, textvariable=var, values=nodes, state="readonly",
                             width=22).grid(row=row, column=1, padx=8, pady=5)
            else:
                ttk.Entry(win, textvariable=var, width=24).grid(row=row, column=1, padx=8, pady=5)
        def save():
            try:
                u, v, cost = u_var.get(), v_var.get(), float(cost_var.get())
                if old_edge:
                    self.graph.remove_edge(*old_edge)
                self.graph.add_edge(u, v, cost)
                win.destroy()
                self._graph_changed()
            except (TypeError, ValueError) as exc:
                messagebox.showerror("Arc invalide", str(exc), parent=win)
        ttk.Button(win, text="Annuler", command=win.destroy).grid(row=3, column=0, padx=8, pady=8)
        ttk.Button(win, text="Enregistrer", command=save).grid(row=3, column=1, padx=8, pady=8)
        win.wait_window()

    def _remove_node(self):
        selected = self.nodes_tv.selection()
        if selected and messagebox.askyesno("Supprimer le sommet",
                                            f"Supprimer « {selected[0]} » et ses arcs ?",
                                            parent=self):
            self.graph.remove_node(selected[0])
            self._graph_changed()

    def _remove_edge(self):
        selected = self.edges_tv.selection()
        if selected and messagebox.askyesno("Supprimer l'arc",
                                            f"Supprimer « {selected[0].replace(chr(0), ' → ')} » ?",
                                            parent=self):
            self.graph.remove_edge(*selected[0].split("\0"))
            self._graph_changed()

    def _set_endpoint(self, endpoint):
        value = (self.start_var if endpoint == "start" else self.goal_node_var).get()
        setattr(self.graph, endpoint, value or None)
        self._graph_changed()

    def _load_example(self):
        self.graph = Graph.example()
        self._graph_changed()

    def _write(self, text):
        self.trace.configure(state="normal")
        self.trace.insert("end", text.rstrip() + "\n")
        self.trace.see("end")
        self.trace.configure(state="disabled")

    def _reset_run(self):
        self._gen = None
        self._finished = False
        self._step_count = 0
        self._final_path = []
        self._set_text(self.trace, "")
        self._set_text(self.state_text, "")
        self.status.configure(text="Recherche réinitialisée.")
        self._check_configuration(show_errors=False)

    def _check_configuration(self, show_errors=True):
        name = self.algorithm_var.get()
        informed = name in INFORMED
        errors, warns = validate(self.graph, informed)
        if name == "Profondeur limitée (DLS)":
            try:
                if int(self.limit_var.get()) < 0:
                    raise ValueError
            except ValueError:
                errors.append("La limite DLS doit être un entier positif ou nul.")
        if name.startswith("SBA*"):
            try:
                if int(self.memory_var.get()) < 2:
                    raise ValueError
            except ValueError:
                errors.append("La mémoire SBA* doit être un entier supérieur ou égal à 2.")
        message = ("Erreur : " + " ".join(errors) if errors else
                   ("Avertissement : " + " ".join(warns) if warns else "Configuration valide."))
        self.validation.configure(text=message,
                                  foreground="#b3261e" if errors else "#c25e00" if warns else "#0a7a2f")
        if errors and show_errors:
            messagebox.showerror("Configuration invalide", "\n".join(errors), parent=self)
        return errors

    def _event_text(self, ev):
        text = ev.get("msg", "")
        if ev.get("frontier") is not None:
            text += "\n  Frontière : " + (", ".join(ev["frontier"]) or "∅")
        if ev.get("explored") is not None:
            text += "\n  Explorés : " + (", ".join(ev["explored"]) or "∅")
        return text

    def _refresh_state(self, ev):
        frontier = ", ".join(ev.get("frontier", [])) or "∅"
        explored = ", ".join(ev.get("explored", [])) or "∅"
        self._set_text(self.state_text, f"Frontière : {frontier}\nExplorés : {explored}")

    def step(self):
        if self._finished:
            return False
        if self._gen is None:
            if self._check_configuration():
                return False
            fn = self._algorithms[self.algorithm_var.get()]
            params = {}
            if fn is UNINFORMED["Profondeur limitée (DLS)"]:
                params["limit"] = int(self.limit_var.get())
            if self.algorithm_var.get().startswith("SBA*"):
                params["memory_limit"] = int(self.memory_var.get())
            self._gen = fn(self.graph, **params)
            self._write(f"Algorithme : {self.algorithm_var.get()}")
        try:
            generator = self._gen
            if generator is None:
                return False
            ev = next(generator)
        except StopIteration:
            self._finished = True
            return False
        self._step_count += 1
        self._write(self._event_text(ev))
        self._refresh_state(ev)
        if ev["type"] == "result":
            self._finished = True
            self._final_path = ev.get("path", [])
            self._draw_graph()
            outcome = "trouvé" if ev.get("found") else "en échec"
            self.status.configure(
                text=f"Recherche terminée ({outcome}) — {self._step_count} étape(s), "
                     f"{ev.get('expanded', 0)} sommet(s) développé(s)."
            )
        else:
            self.status.configure(text=f"Étape {self._step_count}")
        return not self._finished

    def run_all(self):
        count = 0
        while self.step() and count < 200000:
            count += 1
        self.update_idletasks()


# =========================================================================== #
# Application principale
# =========================================================================== #
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("IA & ML — Systèmes experts et algorithmes de recherche")
        self.geometry("1280x820")
        self.minsize(1000, 650)
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        self._configure_style(style)
        self.menu_frame = None
        self.expert = None
        self.search = None
        self.show_menu()

    @staticmethod
    def _configure_style(style):
        style.configure(".", font=("Segoe UI", 10))
        style.configure("TFrame", background="#f4f6f8")
        style.configure("TLabel", background="#f4f6f8", foreground="#243447")
        style.configure("TButton", padding=(12, 7), font=("Segoe UI", 10))
        style.configure("Accent.TButton", background="#1769aa", foreground="white",
                        padding=(16, 10), font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#0d4f82")])
        style.configure("Secondary.TButton", background="#e8eef3", foreground="#17324d",
                        padding=(12, 8), font=("Segoe UI", 10, "bold"))
        style.map("Secondary.TButton", background=[("active", "#d4e1eb")])
        style.configure("Danger.TButton", foreground="#a52a2a",
                        padding=(12, 7), font=("Segoe UI", 10))
        style.configure("Title.TLabel", background="#17324d", foreground="white",
                        font=("Segoe UI", 20, "bold"))
        style.configure("Subtitle.TLabel", background="#17324d", foreground="#d9e7f2",
                        font=("Segoe UI", 10))
        style.configure("Module.TLabel", background="#f4f6f8", foreground="#17324d",
                        font=("Segoe UI", 16, "bold"))
        style.configure("Card.TFrame", background="white", relief="solid", borderwidth=1)
        style.configure("Card.TLabel", background="white", foreground="#243447")
        style.configure("CardMuted.TLabel", background="white", foreground="#657786")
        style.configure("CardKicker.TLabel", background="white", foreground="#1769aa",
                        font=("Segoe UI", 10, "bold"))
        style.configure("TLabelframe", background="#f4f6f8", padding=8)
        style.configure("TLabelframe.Label", background="#f4f6f8",
                        foreground="#1769aa", font=("Segoe UI", 10, "bold"))
        style.configure("TNotebook", background="#f4f6f8", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(16, 9), font=("Segoe UI", 10, "bold"))
        style.map("TNotebook.Tab", background=[("selected", "#ffffff")],
                  foreground=[("selected", "#1769aa")])
        style.configure("Treeview", rowheight=28, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        style.configure("Status.TLabel", background="#17324d", foreground="#d9e7f2",
                        padding=(10, 5), font=("Segoe UI", 9))

    def show_menu(self):
        if self.expert is not None:
            self.expert.pack_forget()
        if self.search is not None:
            self.search.pack_forget()
        self.menu_frame = ttk.Frame(self)
        self.menu_frame.pack(fill="both", expand=True)
        header = ttk.Frame(self.menu_frame, style="Card.TFrame", padding=(36, 24))
        header.pack(fill="x", padx=48, pady=(42, 18))
        ttk.Label(header, text="PLATEFORME IA & ML", style="CardKicker.TLabel",
                  anchor="w").pack(fill="x")
        ttk.Label(header, text="Systèmes experts & recherche", style="Title.TLabel",
                  anchor="w").pack(fill="x", ipady=8)
        ttk.Label(header, text="Une interface pédagogique pour modéliser, raisonner et explorer.",
                  style="CardMuted.TLabel", anchor="w").pack(fill="x")

        ttk.Label(self.menu_frame, text="Choisissez un espace de travail",
                  style="Module.TLabel").pack(anchor="w", padx=52, pady=(10, 12))
        cards = ttk.Frame(self.menu_frame)
        cards.pack(fill="x", padx=48)
        expert_card = ttk.Frame(cards, style="Card.TFrame", padding=22)
        search_card = ttk.Frame(cards, style="Card.TFrame", padding=22)
        expert_card.pack(side="left", fill="both", expand=True, padx=(0, 10))
        search_card.pack(side="left", fill="both", expand=True, padx=(10, 0))
        ttk.Label(expert_card, text="01  ·  SYSTÈME EXPERT",
                  style="CardKicker.TLabel").pack(anchor="w")
        ttk.Label(expert_card, text="Diagnostic automobile",
                  style="Card.TLabel", font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(8, 4))
        ttk.Label(expert_card, text="Construisez une base de faits et de règles, puis utilisez le chaînage avant ou arrière pour établir un diagnostic.",
                  style="CardMuted.TLabel",
                  wraplength=360, justify="left", foreground="#657786").pack(anchor="w", fill="x", pady=(0, 18))
        ttk.Button(expert_card, text="Ouvrir le module  →", command=self.open_expert,
                   style="Accent.TButton").pack(anchor="w")
        ttk.Label(search_card, text="02  ·  RECHERCHE",
                  style="CardKicker.TLabel").pack(anchor="w")
        ttk.Label(search_card, text="Algorithmes sur graphes",
                  style="Card.TLabel", font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(8, 4))
        ttk.Label(search_card, text="Créez un graphe orienté, configurez les coûts et heuristiques, puis visualisez l’exploration étape par étape.",
                  style="CardMuted.TLabel",
                  wraplength=360, justify="left", foreground="#657786").pack(anchor="w", fill="x", pady=(0, 18))
        ttk.Button(search_card, text="Ouvrir le module  →", command=self.open_search,
                   style="Secondary.TButton").pack(anchor="w")
        footer = ttk.Frame(self.menu_frame)
        footer.pack(fill="x", padx=48, pady=(28, 12))
        ttk.Label(footer, text="ENSI · IA & ML · Assignment 1",
                  foreground="#657786").pack(side="left")
        ttk.Button(footer, text="Quitter", command=self.destroy,
                   style="Danger.TButton").pack(side="right")

    def _hide_menu(self):
        if self.menu_frame is not None:
            self.menu_frame.destroy()
            self.menu_frame = None

    def open_expert(self):
        self._hide_menu()
        if self.expert is None:
            self.expert = ExpertSystemFrame(self, on_back=self._back)
        self.expert.pack(fill="both", expand=True)

    def _back(self):
        if self.expert is not None:
            self.expert.pack_forget()
        self.show_menu()

    def open_search(self):
        self._hide_menu()
        if self.search is None:
            self.search = SearchFrame(self, on_back=self._back_search)
        self.search.pack(fill="both", expand=True)

    def _back_search(self):
        if self.search is not None:
            self.search.pack_forget()
        self.show_menu()


if __name__ == "__main__":
    App().mainloop()
