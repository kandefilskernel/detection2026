"""
Politique de décision coût-sensible, partagée par le scoring (décision temps réel), le back-office (simulateur,
édition) et l'évaluation hors ligne : un seul calcul, donc ce que montre le simulateur est ce que fera le scoring.

On choisit l'action qui minimise la perte attendue (p = probabilité de fraude, m = montant USD) :

    APPROVE : p × m                                   (fraude non stoppée)
    VERIFY  : friction + p × m × (1 − taux_capture)   (confirmation PIN USSD / OTP / appel)
    BLOCK   : (1 − p) × (coût_faux_blocage + part_m × m)  (client honnête bloqué)

Paramètres par canal, avec surcharges facultatives par opérateur (« AIRTEL », « VODACOM »…) : un opérateur dont les
clients abandonnent davantage une vérification, ou dont le blocage coûte plus cher, a ses propres coûts.
La politique active est versionnée en base par le back-office et publiée dans Redis (REDIS_KEY) ; le scoring la
recharge à chaud. Bornes de validation : un réglage absurde est refusé plutôt qu'appliqué.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

ACTIONS = ("APPROVE", "VERIFY", "BLOCK")
ACTION_RANK = {a: i for i, a in enumerate(ACTIONS)}
CHANNELS = ("MOBILE_MONEY", "VISA_VIRTUAL")
OPERATORS = ("VODACOM", "AIRTEL", "ORANGE")
REDIS_KEY = "policy:decision"

# bornes de validation (nom -> (min, max))
BOUNDS = {
    "friction_usd": (0.0, 50.0),
    "step_up_catch_rate": (0.0, 1.0),
    "false_block_usd": (0.0, 500.0),
    "false_block_amount_share": (0.0, 1.0),
    "block_floor": (0.5, 1.0),
    "approve_ceiling": (0.0, 0.2),
}


@dataclass
class ChannelCosts:
    friction_usd: float              # coût d'une vérification (temps client, abandon, SMS)
    step_up_catch_rate: float        # part des fraudes stoppées par la vérification
    false_block_usd: float           # coût fixe d'un client honnête bloqué (appel, churn)
    false_block_amount_share: float  # + part du montant (transaction perdue)

    @classmethod
    def from_dict(cls, d: dict) -> "ChannelCosts":
        vals = {}
        for k in ("friction_usd", "step_up_catch_rate", "false_block_usd", "false_block_amount_share"):
            if k not in d:
                raise ValueError(f"paramètre manquant : {k}")
            v = float(d[k])
            lo, hi = BOUNDS[k]
            if not lo <= v <= hi:
                raise ValueError(f"{k} = {v} hors des bornes [{lo}, {hi}]")
            vals[k] = v
        return cls(**vals)


def default_costs() -> dict[str, ChannelCosts]:
    return {
        "MOBILE_MONEY": ChannelCosts(0.30, 0.85, 4.0, 0.05),
        # 3-D Secure : vérification moins coûteuse et plus efficace sur carte
        "VISA_VIRTUAL": ChannelCosts(0.15, 0.90, 6.0, 0.05),
    }


@dataclass
class CostPolicy:
    costs: dict[str, ChannelCosts] = field(default_factory=default_costs)
    operator_overrides: dict[str, ChannelCosts] = field(default_factory=dict)   # Mobile Money uniquement
    block_floor: float = 0.97        # au-delà : blocage quel que soit le montant
    approve_ceiling: float = 0.01    # en deçà : approbation directe (pas de friction inutile)
    version: str = "défaut"

    def costs_for(self, channel: str, operator: str | None = None) -> ChannelCosts:
        if channel == "MOBILE_MONEY" and operator and operator.upper() in self.operator_overrides:
            return self.operator_overrides[operator.upper()]
        return self.costs.get(channel, self.costs["MOBILE_MONEY"])

    def expected_costs(self, p: float, amount_usd: float, channel: str, operator: str | None = None) -> dict:
        c = self.costs_for(channel, operator)
        return {
            "APPROVE": p * amount_usd,
            "VERIFY": c.friction_usd + p * amount_usd * (1 - c.step_up_catch_rate),
            "BLOCK": (1 - p) * (c.false_block_usd + c.false_block_amount_share * amount_usd),
        }

    def cost_action(self, p: float, amount_usd: float, channel: str, operator: str | None = None) -> tuple[str, str, dict]:
        """(action, motif, coûts attendus) avant les règles réglementaires."""
        costs = self.expected_costs(p, amount_usd, channel, operator)
        if p >= self.block_floor:
            return "BLOCK", "probabilité de fraude très élevée", costs
        if p < self.approve_ceiling:
            return "APPROVE", "risque négligeable", costs
        return min(costs, key=costs.get), "coût attendu minimal", costs

    # ------------------------------------------------------------------ (dé)sérialisation validée
    def to_dict(self) -> dict:
        return {"costs": {k: asdict(v) for k, v in self.costs.items()},
                "operator_overrides": {k: asdict(v) for k, v in self.operator_overrides.items()},
                "block_floor": self.block_floor, "approve_ceiling": self.approve_ceiling, "version": self.version}

    @classmethod
    def from_dict(cls, d: dict) -> "CostPolicy":
        costs = {ch: ChannelCosts.from_dict(v) for ch, v in (d.get("costs") or {}).items()}
        unknown = set(costs) - set(CHANNELS)
        if unknown or set(costs) != set(CHANNELS):
            raise ValueError(f"canaux attendus : {', '.join(CHANNELS)}")
        overrides = {op.upper(): ChannelCosts.from_dict(v) for op, v in (d.get("operator_overrides") or {}).items()}
        if set(overrides) - set(OPERATORS):
            raise ValueError(f"opérateurs reconnus : {', '.join(OPERATORS)}")
        floor, ceiling = float(d.get("block_floor", 0.97)), float(d.get("approve_ceiling", 0.01))
        for name, v in (("block_floor", floor), ("approve_ceiling", ceiling)):
            lo, hi = BOUNDS[name]
            if not lo <= v <= hi:
                raise ValueError(f"{name} = {v} hors des bornes [{lo}, {hi}]")
        return cls(costs, overrides, floor, ceiling, str(d.get("version") or "défaut"))
