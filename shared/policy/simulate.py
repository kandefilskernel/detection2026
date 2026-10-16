"""Rejeu d'une politique de coût sur des transactions déjà scorées (simulateur du back-office, évaluation hors ligne).

Chaque ligne : probabilité p, montant, canal, opérateur, étiquette (1 / 0 / None) et indicateur « une règle
réglementaire a imposé au moins une vérification » (les règles ne peuvent que renforcer la décision : toutes imposent
VERIFY, donc leur effet se rejoue sans les variables d'origine).

Deux lectures des coûts :
    attendus  d'après la probabilité du modèle, sur TOUTES les transactions ;
    réalisés  d'après les étiquettes (verdicts, plaintes), sur les seules transactions étiquetées.
"""
from __future__ import annotations

from collections import defaultdict

from shared.policy.costs import ACTION_RANK, ACTIONS, CostPolicy


def decide(policy: CostPolicy, p: float, amount: float, channel: str, operator: str | None, rule_verify: bool) -> str:
    action = policy.cost_action(p, amount, channel, operator)[0]
    if rule_verify and ACTION_RANK[action] < ACTION_RANK["VERIFY"]:
        action = "VERIFY"
    return action


def realized_costs(rows: list[dict], actions: list[str], cost_model: CostPolicy) -> dict:
    """Pertes réalisées d'après les étiquettes, avec un modèle de coût FIXÉ (pour comparer des politiques entre elles,
    y compris un simple seuil, sur la même échelle de coûts)."""
    real = {"n": 0, "frauds": 0, "fraud_blocked": 0, "fraud_verified": 0, "fraud_missed": 0,
            "legit_blocked": 0, "legit_verified": 0, "fraud_loss": 0.0, "friction": 0.0, "false_block": 0.0}
    for r, a in zip(rows, actions):
        y = r.get("label")
        if y is None:
            continue
        m = float(r["amount_usd"])
        c = cost_model.costs_for(r["channel"], r.get("operator"))
        real["n"] += 1
        if y == 1:
            real["frauds"] += 1
            if a == "APPROVE":
                real["fraud_missed"] += 1
                real["fraud_loss"] += m
            elif a == "VERIFY":
                real["fraud_verified"] += 1
                real["friction"] += c.friction_usd
                real["fraud_loss"] += m * (1 - c.step_up_catch_rate)
            else:
                real["fraud_blocked"] += 1
        elif a == "VERIFY":
            real["legit_verified"] += 1
            real["friction"] += c.friction_usd
        elif a == "BLOCK":
            real["legit_blocked"] += 1
            real["false_block"] += c.false_block_usd + c.false_block_amount_share * m
    real["total"] = real["fraud_loss"] + real["friction"] + real["false_block"]
    return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in real.items()}


def simulate(rows: list[dict], policy: CostPolicy, cost_model: CostPolicy | None = None) -> tuple[dict, list[str]]:
    """Décisions de `policy`, coûts évalués avec `cost_model` (par défaut la politique elle-même)."""
    cost_model = cost_model or policy
    counts = dict.fromkeys(ACTIONS, 0)
    exp = {"fraud_loss": 0.0, "friction": 0.0, "false_block": 0.0, "fraud_stopped_usd": 0.0}
    by_channel: dict[str, dict] = defaultdict(lambda: {"n": 0, **dict.fromkeys(ACTIONS, 0), "expected_cost": 0.0})
    actions = []
    for r in rows:
        p, m, ch, op = float(r["p"]), float(r["amount_usd"]), r["channel"], r.get("operator")
        a = decide(policy, p, m, ch, op, bool(r.get("rule_verify")))
        actions.append(a)
        c = cost_model.costs_for(ch, op)
        counts[a] += 1
        bc = by_channel[ch if ch != "MOBILE_MONEY" or not op else f"{ch}:{op}"]
        bc["n"] += 1
        bc[a] += 1
        if a == "APPROVE":
            exp["fraud_loss"] += p * m
            bc["expected_cost"] += p * m
        elif a == "VERIFY":
            exp["friction"] += c.friction_usd
            exp["fraud_loss"] += p * m * (1 - c.step_up_catch_rate)
            exp["fraud_stopped_usd"] += p * m * c.step_up_catch_rate
            bc["expected_cost"] += c.friction_usd + p * m * (1 - c.step_up_catch_rate)
        else:
            fb = (1 - p) * (c.false_block_usd + c.false_block_amount_share * m)
            exp["false_block"] += fb
            exp["fraud_stopped_usd"] += p * m
            bc["expected_cost"] += fb
    n = len(rows)
    exp["total"] = exp["fraud_loss"] + exp["friction"] + exp["false_block"]
    return {
        "n": n, "actions": counts, "shares": {a: (counts[a] / n if n else 0.0) for a in ACTIONS},
        "expected": {k: round(v, 2) for k, v in exp.items()},
        "realized": realized_costs(rows, actions, cost_model),
        "by_channel": {k: {**v, "expected_cost": round(v["expected_cost"], 2)} for k, v in sorted(by_channel.items())},
    }, actions


def compare(rows: list[dict], current: CostPolicy, candidate: CostPolicy) -> dict:
    """Les deux politiques sont jugées avec les MÊMES coûts, ceux de la candidate (ce que l'on croit vrai)."""
    cur, a_cur = simulate(rows, current, cost_model=candidate)
    cand, a_cand = simulate(rows, candidate)
    moves: dict[str, int] = defaultdict(int)
    for x, y in zip(a_cur, a_cand):
        if x != y:
            moves[f"{x}->{y}"] += 1
    return {"current": cur, "candidate": cand, "changed": sum(moves.values()), "moves": dict(moves)}
