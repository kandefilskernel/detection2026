import math

import pytest

from shared.graph.network import TransactionGraph, node_id, split_node, tx_entities


def p2p(user, wallet, device, amount=50.0):
    return {"user_id": user, "tx_type": "P2P_SEND", "counterparty_id": wallet, "device_id": device,
            "agent_id": None, "merchant_id": None, "amount_usd": amount}


@pytest.fixture
def mule_graph():
    """Cinq victimes envoient vers le même portefeuille mule ; trente comptes vivent normalement."""
    g = TransactionGraph()
    for i in range(30):
        for k in range(5):
            g.add(p2p(f"U{i}", f"W-ami-{i}-{k % 2}", f"D-perso-{i}"), 0.0)
        g.add({"user_id": f"U{i}", "tx_type": "MERCHANT_PAYMENT", "device_id": f"D-perso-{i}",
               "merchant_id": "M-supermarche", "amount_usd": 20.0}, 0.0)
    for v in range(5):
        g.add(p2p(f"V{v}", "W-mule", "D-fraudeur"), 1.0)
        for _ in range(4):
            g.add(p2p(f"V{v}", f"W-famille-{v}", f"D-victime-{v}"), 0.0)
    return g


def test_entities_skip_missing_values_and_non_transfer_counterparties():
    assert tx_entities({"tx_type": "AIRTIME", "counterparty_id": "VODACOM", "device_id": "D1",
                        "agent_id": float("nan"), "merchant_id": ""}) == ["D:D1"]
    assert tx_entities(p2p("U1", "W1", "D1")) == ["W:W1", "D:D1"]


def test_node_ids_round_trip_and_reject_unknown_kind():
    assert split_node(node_id("W", "243700000001")) == ("W", "243700000001")
    with pytest.raises(ValueError):
        split_node("X:1")


def test_shared_mule_and_fraud_device_outrank_legit_entities(mule_graph):
    sc = mule_graph.compute_scores()
    assert sc.entity["W:W-mule"] > 0.5 and sc.entity["D:D-fraudeur"] > 0.5
    # un marchand très fréquenté mais sain reste au niveau du taux de base
    assert sc.entity["M:M-supermarche"] < 0.1
    # les victimes sont exposées, les comptes sans lien avec le réseau ne le sont pas
    assert sc.account["U:V0"] > 0.5 and sc.account["U:U0"] < 0.2


def test_propagation_excludes_the_entity_itself(mule_graph):
    """Le risque propagé d'une entité ne doit pas provenir d'elle-même (sinon elle s'auto-alimente)."""
    sc = mule_graph.compute_scores()
    # hors la mule, les victimes ne sont exposées que par l'appareil du fraudeur : la mule hérite de son excès de risque
    excess = (sc.direct["D:D-fraudeur"] - sc.base_rate) / (1 - sc.base_rate)
    assert sc.propagated["W:W-mule"] == pytest.approx(excess) and excess > 0.5
    g = TransactionGraph()
    for v in range(3):
        g.add(p2p(f"V{v}", "W-seule", None), 1.0)
    sc2 = g.compute_scores()
    assert sc2.propagated["W:W-seule"] == pytest.approx(0.0, abs=1e-9)


def test_active_account_with_many_healthy_entities_is_not_exposed():
    """L'exposition ne cumule que l'excès de risque : 60 marchands sains ne rendent pas un compte suspect."""
    g = TransactionGraph()
    for i in range(500):
        g.add({"user_id": f"U{i % 50}", "tx_type": "MERCHANT_PAYMENT", "merchant_id": f"M{i % 60}", "amount_usd": 5.0}, 0.02)
    for m in range(60):
        g.add({"user_id": "ACTIF", "tx_type": "MERCHANT_PAYMENT", "merchant_id": f"M{m}", "amount_usd": 5.0}, 0.02)
    sc = g.compute_scores()
    assert sc.account["U:ACTIF"] < 0.05
    assert max(sc.entity[f"M:M{m}"] for m in range(60)) < 0.1


def test_beta_prior_needs_more_than_one_fraud_on_a_busy_entity():
    g = TransactionGraph()
    for i in range(200):
        g.add({"user_id": f"U{i}", "tx_type": "MERCHANT_PAYMENT", "merchant_id": "M1", "amount_usd": 5.0},
              1.0 if i == 0 else 0.0)
    g.add(p2p("Z", "W-neuf", None), 1.0)
    sc = g.compute_scores()
    assert sc.direct["M:M1"] < 0.05 < sc.direct["W:W-neuf"]


def test_relabel_replaces_model_score_by_analyst_verdict():
    g = TransactionGraph()
    tx = p2p("U1", "W1", "D1")
    g.add(tx, 0.9)
    g.relabel(tx, 0.9, 0.0)
    st = g.edges[("U:U1", "W:W1")]
    assert st.n == 1 and st.n_known == 1 and math.isclose(st.s, 0.0, abs_tol=1e-12)


def test_rings_group_victims_around_the_mule(mule_graph):
    rings = mule_graph.rings(mule_graph.compute_scores())
    assert len(rings) == 1
    r = rings[0]
    assert r["n_accounts"] == 5 and set(r["top_entities"]) == {"W:W-mule", "D:D-fraudeur"}
    assert r["expected_frauds"] == pytest.approx(10.0)       # 5 transactions x 2 entités du réseau


def test_ego_keeps_center_and_riskiest_neighbours(mule_graph):
    sc = mule_graph.compute_scores()
    out = mule_graph.ego("W:W-mule", sc, hops=2, max_nodes=8)
    ids = {n["id"] for n in out["nodes"]}
    assert "W:W-mule" in ids and "D:D-fraudeur" in ids and len(ids) <= 8
    assert all(e["source"] in ids and e["target"] in ids for e in out["edges"])
    assert mule_graph.ego("U:inconnu", sc)["nodes"] == []


def test_add_edge_matches_transaction_by_transaction(mule_graph):
    """Arêtes pré-agrégées (GROUP BY SQL du back-office) = même graphe et mêmes scores."""
    g = TransactionGraph()
    for (u, e), st in mule_graph.edges.items():
        g.add_edge(u[2:], e, st.n, st.n_known, st.s, st.amount)
    a, b = mule_graph.compute_scores(), g.compute_scores()
    assert a.entity == pytest.approx(b.entity) and a.account == pytest.approx(b.account)
    with pytest.raises(ValueError):
        g.add_edge("U1", "X:inconnu", 1, 1, 0.0, 1.0)
