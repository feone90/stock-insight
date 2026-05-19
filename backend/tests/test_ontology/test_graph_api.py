from types import SimpleNamespace

import pytest

from app.api import ontology
from app.models import RelationCandidate, Stock, StockRelation


def _rel(**overrides):
    base = {
        "relation_type": "contract_customer",
        "source": "news",
        "confidence": 0.7,
        "to_kind": "stock",
        "to_target": "OPENAI",
        "extra_metadata": {"rationale": "OpenAI is a major AI customer."},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_business_view_keeps_business_edges_and_drops_context_edges():
    assert ontology._relation_allowed_for_view(
        _rel(relation_type="contract_customer"), "business"
    )
    assert ontology._relation_allowed_for_view(
        _rel(relation_type="competitor"), "business"
    )
    assert not ontology._relation_allowed_for_view(
        _rel(relation_type="peer"), "business"
    )
    assert not ontology._relation_allowed_for_view(
        _rel(relation_type="theme"), "business"
    )


def test_all_view_includes_low_confidence_context_by_default():
    assert ontology._effective_min_confidence(None, "business") == pytest.approx(0.5)
    assert ontology._effective_min_confidence(None, "all") == pytest.approx(0.35)
    assert ontology._relation_allowed_for_view(
        _rel(relation_type="peer", source="sector_match", confidence=0.4), "all"
    )


def test_virtual_business_node_uses_relation_target_when_stock_row_is_missing():
    rel = _rel(to_target="OpenAI", to_kind="stock")

    node = ontology._virtual_node_dict(rel)

    assert node["id"] == "OpenAI"
    assert node["ticker"] == "OpenAI"
    assert node["name"] == "OpenAI"
    assert node["node_kind"] == "private"
    assert node["is_virtual"] is True


@pytest.mark.asyncio
async def test_outgoing_business_view_keeps_virtual_business_target_but_not_peer(db):
    center = Stock(ticker="T999A", name="Center", market="NASDAQ", sector="AI", tier=1)
    peer = Stock(ticker="T999B", name="Peer", market="NASDAQ", sector="AI", tier=1)
    db.add_all([center, peer])
    await db.flush()
    db.add_all([
        StockRelation(
            from_stock_id=center.id,
            to_target=peer.ticker,
            to_kind="stock",
            relation_type="peer",
            strength=0.5,
            source="sector_match",
            signal_direction="positive",
            confidence=0.4,
        ),
        StockRelation(
            from_stock_id=center.id,
            to_target="OpenAI",
            to_kind="stock",
            relation_type="contract_customer",
            strength=0.9,
            source="llm_knowledge",
            signal_direction="positive",
            confidence=0.85,
            extra_metadata={"rationale": "OpenAI buys AI accelerators from Center."},
        ),
    ])
    await db.flush()

    business = await ontology._outgoing(
        db, center.id, None,
        ontology._effective_min_confidence(None, "business"),
        10, "business",
    )
    all_view = await ontology._outgoing(
        db, center.id, None,
        ontology._effective_min_confidence(None, "all"),
        10, "all",
    )

    assert {r.to_target for r in business} == {"OpenAI"}
    assert {r.to_target for r in all_view} == {"OpenAI", peer.ticker}


@pytest.mark.asyncio
async def test_outgoing_includes_private_candidate_as_virtual_business_target(db):
    center = Stock(ticker="T999C", name="Center", market="NASDAQ", sector="AI", tier=1)
    db.add(center)
    await db.flush()
    db.add(
        RelationCandidate(
            from_ticker=center.ticker,
            to_ticker="PrivateInfraLab",
            relation_type="complementary",
            strength=0.9,
            source="llm_knowledge",
            signal_direction="positive",
            confidence=0.88,
            extra_metadata={
                "target_name": "Private Infrastructure Lab",
                "target_is_public": False,
                "business_importance": 5,
                "rationale": (
                    "Center relies on Private Infrastructure Lab as an exclusive "
                    "model infrastructure partner, so usage growth directly affects "
                    "Center's AI platform demand."
                ),
            },
        )
    )
    await db.flush()

    rels = await ontology._outgoing(
        db, center.id, None,
        ontology._effective_min_confidence(None, "business"),
        10, "business",
    )

    assert {r.to_target for r in rels} == {"PrivateInfraLab"}
    node = ontology._virtual_node_dict(rels[0])
    link = ontology._link_dict(center, rels[0], None)
    assert node["id"] == "PrivateInfraLab"
    assert node["name"] == "Private Infrastructure Lab"
    assert node["node_kind"] == "private"
    assert link["target_in_universe"] is False
    assert link["rationale"].startswith("Center relies on Private Infrastructure Lab")
