import json

import numpy as np
import pytest

from shared.rag.retriever import (CaseMemory, KnowledgeBase, agreement, build_evidence, consensus)

FEATS = ["is_card", "a", "b"]


def make_index(tmp_path):
    rng = np.random.default_rng(0)
    legit = rng.normal(0, 0.3, size=(200, 3)).astype(np.float32)
    fraud = rng.normal(0, 0.3, size=(40, 3)).astype(np.float32) + np.array([0, 4, 4], dtype=np.float32)
    X = np.vstack([legit, fraud])
    y = np.array([0] * 200 + [1] * 40, dtype=np.int8)
    path = tmp_path / "idx.npz"
    np.savez(path, X=X, y=y, w=np.ones(len(y), dtype=np.float32), ftype=np.array([""] * 200 + ["SIM_SWAP"] * 40),
             ids=np.array([f"T{i}" for i in range(len(y))]), channel=np.array(["MOBILE_MONEY"] * len(y)),
             tx_type=np.array(["P2P_SEND"] * len(y)), amount=np.ones(len(y), dtype=np.float32),
             mean=np.zeros(3), scale=np.ones(3), clip=np.float32(10), ref_dist=np.float32(0.5),
             feature_names=json.dumps(FEATS))
    return CaseMemory(path)


def test_neighbors_of_a_fraud_like_point_are_frauds(tmp_path):
    mem = make_index(tmp_path)
    n = mem.neighbors({"is_card": 0, "a": 4, "b": 4}, k=5)
    assert len(n) == 5 and all(r["label"] == 1 and r["fraud_type"] == "SIM_SWAP" for r in n)
    assert n == sorted(n, key=lambda r: r["d"])
    assert all(0 < r["similarity"] <= 1 for r in n)


def test_agreement_flags_divergence_with_the_model(tmp_path):
    mem = make_index(tmp_path)
    fraud_like, legit_like = {"is_card": 0, "a": 4, "b": 4}, {"is_card": 0, "a": 0, "b": 0}
    assert agreement(True, consensus(mem.neighbors(fraud_like, k=5))) == "COHERENT"
    assert agreement(True, consensus(mem.neighbors(legit_like, k=5))) == "DIVERGENT"
    far = consensus(mem.neighbors({"is_card": 0, "a": 80, "b": -80}, k=5))
    assert agreement(True, far) == "INSUFFISANT"          # trop éloigné de tout cas connu


def test_analyst_verdicts_extend_the_memory(tmp_path):
    mem = make_index(tmp_path)
    extra = [{"id": "ANALYSTE-1", "features": {"is_card": 0, "a": 9, "b": 9}, "label": 0, "channel": "MOBILE_MONEY",
              "tx_type": "P2P_SEND", "amount_usd": 5}]
    n = mem.neighbors({"is_card": 0, "a": 9, "b": 9}, k=3, extra=extra)
    assert n[0]["id"] == "ANALYSTE-1" and n[0]["source"] == "verdict analyste"


def test_knowledge_returns_the_typology_sheet_first():
    kb = KnowledgeBase()
    out = kb.search("is_new_device is_new_counterparty", fraud_type="SIM_SWAP", k=3)
    assert out[0]["section"] == "Définition" and "SIM" in out[0]["title"]
    assert {p["title"] for p in out} == {out[0]["title"]}
    sections = [p["section"] for p in kb.search("tx_count_1h", fraud_type="CARD_TESTING", k=3)]
    assert "Signaux observables" in sections
    assert kb.search("peu importe", fraud_type=None, k=2)[0]["title"].startswith("Politique")


def test_build_evidence_summary_is_grounded(tmp_path):
    mem, kb = make_index(tmp_path), KnowledgeBase()
    ev = build_evidence(kb, mem, {"is_card": 0, "a": 4, "b": 4}, model_flagged=True, probability=0.97,
                        fraud_type="SIM_SWAP", top_features=["is_new_device"], channel="MOBILE_MONEY")
    assert ev["agreement"] == "COHERENT" and ev["reliability"] == "ELEVEE" and ev["type_agreement"] is True
    assert "5 des 5" in ev["summary"]
    bad = build_evidence(kb, mem, {"is_card": 0, "a": 0, "b": 0}, model_flagged=True, probability=0.9,
                         fraud_type="SIM_SWAP", top_features=[], channel="MOBILE_MONEY")
    assert bad["reliability"] == "A_VERIFIER" and "légitime" in bad["summary"]
