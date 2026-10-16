"""
Décision coût-sensible : APPROVE / VERIFY / BLOCK.

Un seuil unique « fraude / pas fraude » ignore le montant : bloquer 2 USD de crédit
téléphonique et laisser passer 900 USD de cash-out n'ont pas le même coût. On choisit
l'action qui minimise la perte attendue (p = probabilité de fraude, m = montant USD) :

    APPROVE : p × m                                   (fraude non stoppée)
    VERIFY  : friction + p × m × (1 − taux_capture)   (confirmation PIN USSD / OTP / appel)
    BLOCK   : (1 − p) × (coût_faux_blocage + part_m × m)  (client honnête bloqué)

Paramètres par canal (Mobile Money / Visa virtuelle), avec surcharges par opérateur, réglables sans réentraîner :
la politique de coût (shared/policy/costs.py) est éditée et simulée dans le back-office, puis rechargée à chaud.
Des règles réglementaires explicites passent ensuite AVANT le coût (auditables BCC).

Le niveau de risque affiché aux analystes (FAIBLE / MOYEN / ÉLEVÉ / CRITIQUE) dépend
uniquement de p, par rapport au seuil F1 choisi sur la validation.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from shared.policy.costs import ACTION_RANK, ACTIONS, ChannelCosts, CostPolicy  # noqa: F401 (réexport)


@dataclass
class DecisionPolicy:
    threshold: float                                   # seuil F1 du modèle (validation)
    cost: CostPolicy = field(default_factory=CostPolicy)

    def risk_level(self, p: float) -> str:
        t = self.threshold
        if p >= max(0.9, t):
            return "CRITIQUE"
        if p >= t:
            return "ELEVE"
        if p >= t / 5:
            return "MOYEN"
        return "FAIBLE"

    def expected_costs(self, p: float, amount_usd: float, channel: str, operator: str | None = None) -> dict:
        return self.cost.expected_costs(p, amount_usd, channel, operator)

    def decide(self, p: float, amount_usd: float, channel: str, feats: dict, tx: dict,
               text: dict | None = None, physics: dict | None = None, operator: str | None = None) -> dict:
        action, reason, costs = self.cost.cost_action(p, amount_usd, channel, operator)
        rules = regulatory_rules(feats, tx, text, physics)
        for rule in rules:
            if ACTION_RANK[rule["min_action"]] > ACTION_RANK[action]:
                action, reason = rule["min_action"], f"règle : {rule['id']}"
        return {
            "action": action,
            "risk_level": self.risk_level(p),
            "reason": reason,
            "expected_costs_usd": {k: round(v, 4) for k, v in costs.items()},
            "rules_triggered": [r["id"] for r in rules],
            "policy_version": self.cost.version,
        }


def regulatory_rules(feats: dict, tx: dict, text: dict | None = None, physics: dict | None = None) -> list[dict]:
    """Règles métier explicites, prioritaires sur le modèle (conformité et bon sens terrain).
    Elles ne peuvent que RENFORCER la décision, jamais l'assouplir."""
    rules = []
    debit = tx["tx_type"] not in ("P2P_RECEIVE", "CASH_IN")
    if debit and feats["is_new_device"] and feats["is_near_full_drain"]:
        rules.append({"id": "NOUVEL_APPAREIL_VIDAGE_COMPTE", "min_action": "VERIFY"})
    if debit and feats["amount_to_kyc_limit"] > 1.0:
        rules.append({"id": "DEPASSEMENT_PLAFOND_KYC", "min_action": "VERIFY"})
    if tx["tx_type"] == "CASH_OUT" and feats["is_new_device"] and feats["is_new_province"]:
        rules.append({"id": "CASH_OUT_APPAREIL_ET_PROVINCE_INHABITUELS", "min_action": "VERIFY"})
    # Le texte seul ne justifie jamais un blocage (lexique, pas de certitude) : il impose une confirmation
    # du client quand le message du transfert ressemble fortement à une manipulation.
    if debit and text and text["social_engineering"]["level"] == "ELEVE":
        rules.append({"id": "TEXTE_INGENIERIE_SOCIALE", "min_action": "VERIFY"})
    # Loi physique de cinématique (modèle par les lois physiques) : un client ne peut pas être là où il ne peut
    # physiquement pas être. Fournie seulement en mode « enforce » ; ne peut que renforcer la décision.
    if physics and "CINEMATIQUE" in physics["violated"] and physics["severe"]:
        rules.append({"id": "LOI_PHYSIQUE_CINEMATIQUE", "min_action": "VERIFY"})
    return rules
