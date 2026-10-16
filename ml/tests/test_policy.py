import pytest

from ml.serving.decision import DecisionPolicy
from shared.policy.costs import CostPolicy
from shared.policy.simulate import compare, simulate


def test_round_trip_and_validation():
    p = CostPolicy()
    assert CostPolicy.from_dict(p.to_dict()).to_dict() == p.to_dict()
    bad = p.to_dict()
    bad["costs"]["MOBILE_MONEY"]["step_up_catch_rate"] = 1.5
    with pytest.raises(ValueError, match="step_up_catch_rate"):
        CostPolicy.from_dict(bad)
    missing = p.to_dict()
    del missing["costs"]["VISA_VIRTUAL"]
    with pytest.raises(ValueError, match="canaux"):
        CostPolicy.from_dict(missing)
    unknown = p.to_dict()
    unknown["operator_overrides"] = {"MTN": unknown["costs"]["MOBILE_MONEY"]}
    with pytest.raises(ValueError, match="opérateurs"):
        CostPolicy.from_dict(unknown)


def test_operator_override_changes_the_decision_only_for_that_operator():
    d = CostPolicy().to_dict()
    # opérateur dont les clients abandonnent souvent une vérification : friction très chère
    d["operator_overrides"] = {"AIRTEL": {**d["costs"]["MOBILE_MONEY"], "friction_usd": 20.0}}
    pol = DecisionPolicy(threshold=0.5, cost=CostPolicy.from_dict(d))
    feats = {"is_new_device": 0, "is_near_full_drain": 0, "amount_to_kyc_limit": 0.1, "is_new_province": 0}
    tx = {"tx_type": "P2P_SEND"}
    assert pol.decide(0.2, 60.0, "MOBILE_MONEY", feats, tx, operator="VODACOM")["action"] == "VERIFY"
    assert pol.decide(0.2, 60.0, "MOBILE_MONEY", feats, tx, operator="AIRTEL")["action"] != "VERIFY"


def test_simulation_costs_add_up_and_rules_force_verification():
    rows = [
        {"p": 0.005, "amount_usd": 10.0, "channel": "MOBILE_MONEY", "operator": "ORANGE", "label": 0},
        {"p": 0.005, "amount_usd": 10.0, "channel": "MOBILE_MONEY", "operator": "ORANGE", "label": None, "rule_verify": True},
        {"p": 0.99, "amount_usd": 200.0, "channel": "VISA_VIRTUAL", "operator": None, "label": 1},
        {"p": 0.99, "amount_usd": 50.0, "channel": "MOBILE_MONEY", "operator": "AIRTEL", "label": 0},
    ]
    res, actions = simulate(rows, CostPolicy())
    assert actions == ["APPROVE", "VERIFY", "BLOCK", "BLOCK"]
    e = res["expected"]
    assert e["total"] == pytest.approx(e["fraud_loss"] + e["friction"] + e["false_block"], abs=0.02)
    r = res["realized"]
    assert r["n"] == 3 and r["frauds"] == 1 and r["fraud_blocked"] == 1 and r["legit_blocked"] == 1
    assert r["false_block"] == pytest.approx(4.0 + 0.05 * 50.0)          # coût d'un client honnête bloqué


def test_compare_counts_moves_between_policies():
    rows = [{"p": 0.3, "amount_usd": a, "channel": "MOBILE_MONEY", "operator": "VODACOM", "label": None}
            for a in (5.0, 50.0, 500.0)]
    strict = CostPolicy().to_dict()
    strict["costs"]["MOBILE_MONEY"]["false_block_usd"] = 0.0           # bloquer ne coûte presque rien
    strict["costs"]["MOBILE_MONEY"]["false_block_amount_share"] = 0.0
    out = compare(rows, CostPolicy(), CostPolicy.from_dict(strict))
    assert out["changed"] >= 1
    assert out["candidate"]["actions"]["BLOCK"] > out["current"]["actions"]["BLOCK"]
    assert sum(out["moves"].values()) == out["changed"]
