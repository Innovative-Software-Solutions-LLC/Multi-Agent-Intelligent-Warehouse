# SPDX-FileCopyrightText: Copyright (c) 2026 Innovative Software Solutions LLC. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
The shipping domain in MAIW: the ISS engine decides under the shipper's agreement; MAIW's own DecisionEngine
governs the write; the risk is earned from the decision's evidence. Runs against MAIW's real DecisionEngine
and the real ISS engine in process (ISS_ENGINE_DIR), on the sample shipper (invented data).
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

import pytest

from maiw_decision import DecisionEngine, DecisionOutcome, DecisionRequest
from maiw_decision.approval import InMemoryApprovalStore
from maiw_decision.proposal import RiskLevel
from maiw_state import WarehouseState, WarehouseStateSnapshot
from maiw_contracts.shipping import ShippingDecideRequest, ShippingPackage, ShippingAssignRequest
from mcp_servers.shipping.adapters.iss_engine import ISSShippingProvider
from mcp_servers.shipping.provider import MockShippingProvider, ShippingProvider
from mcp_servers.shipping import proposal as sp

ISS = os.environ.get("ISS_ENGINE_DIR", "/home/claude/iss-engine")
os.environ.setdefault("ISS_CLIENT_CONFIG_DIR", tempfile.mkdtemp())
os.environ.setdefault("ISS_SNAPSHOT_DIR", tempfile.mkdtemp())
os.environ.setdefault("ISS_USER", "u")
os.environ.setdefault("ISS_PASS", "p")
sys.path.insert(0, ISS)
import handler as iss  # noqa: E402  the ISS engine, in process


def in_process(method, path, body):
    p, _, qs = path.partition("?")
    q = dict(x.split("=", 1) for x in qs.split("&") if "=" in x)
    if body is not None:
        body = {**body, "_no_ledger": True}
    return iss.route(method, p, json.dumps(body) if body is not None else None, q)


def snapshot():
    return WarehouseStateSnapshot.seal(WarehouseState(warehouse_id="DC-47", observed_at=datetime.now(timezone.utc)))


def decide(provider, **pkg):
    return asyncio.run(provider.decide_service(ShippingDecideRequest(package=ShippingPackage(**pkg), requested_by="agent-a")))


PKG = dict(package_id="PKG-1", weight_lb=3, length_in=10, width_in=8, height_in=6, ground_transit_days=5)


def test_provider_meets_the_protocol():
    assert isinstance(ISSShippingProvider(transport=in_process), ShippingProvider)
    assert isinstance(MockShippingProvider(), ShippingProvider)


def test_the_engine_decides_under_the_agreement():
    d = decide(ISSShippingProvider(transport=in_process), **PKG)
    assert d.service == "2ND_DAY_AIR" and d.price == 11.10 and "service_upgrade" in d.rules_fired
    assert d.self_check_ok is True and not d.assumed and d.configuration == "parcel_demo"


def test_earned_autonomy_low_risk_approved_without_a_person():
    prov = ISSShippingProvider(transport=in_process, passed_agents={"agent-a"})
    d = decide(prov, **PKG)
    p = sp.for_assign_service(d, agent_passed_exam=asyncio.run(prov.exam_passed("agent-a")), requested_by="agent-a")
    assert p.risk_level == RiskLevel.LOW and p.requires_approval is False and p.domain == "shipping"
    result, audit = DecisionEngine().evaluate(DecisionRequest(proposal=p, state=snapshot()))
    assert result.outcome == DecisionOutcome.APPROVED


def test_no_exam_no_autonomy_a_person_approves():
    prov = ISSShippingProvider(transport=in_process)
    d = decide(prov, **PKG)
    p = sp.for_assign_service(d, agent_passed_exam=asyncio.run(prov.exam_passed("agent-b")), requested_by="agent-b")
    assert p.risk_level == RiskLevel.MEDIUM and any("exam" in e for e in p.parameters["evidence"])
    engine = DecisionEngine()
    result, _ = engine.evaluate(DecisionRequest(proposal=p, state=snapshot()))
    assert result.outcome == DecisionOutcome.REQUIRES_HUMAN_APPROVAL
    store = InMemoryApprovalStore()
    rec = store.create(proposal_id=p.proposal_id, decision_id=result.result_id)
    rec = store.approve(rec.approval_id, approved_by="shift-lead")
    final, _ = engine.authorize_with_approval(DecisionRequest(proposal=p, state=snapshot()), rec,
                                              expected_decision_id=result.result_id)
    assert final.outcome == DecisionOutcome.APPROVED


def test_unknown_transit_is_never_autonomous():
    prov = ISSShippingProvider(transport=in_process, passed_agents={"agent-a"})
    d = decide(prov, **{**PKG, "ground_transit_days": None})
    p = sp.for_assign_service(d, agent_passed_exam=True)
    assert "transit_unknown" in d.rules_fired and p.risk_level == RiskLevel.MEDIUM


def test_a_failed_self_check_is_high_risk():
    d = decide(ISSShippingProvider(transport=in_process), **PKG)
    bad = d.model_copy(update={"self_check_ok": False, "self_check": "1 of 5 checks disagree"})
    p = sp.for_assign_service(bad, agent_passed_exam=True)
    assert p.risk_level == RiskLevel.HIGH and p.requires_approval
    result, _ = DecisionEngine().evaluate(DecisionRequest(proposal=p, state=snapshot()))
    assert result.outcome == DecisionOutcome.REQUIRES_HUMAN_APPROVAL


def test_a_refused_package_is_never_proposed():
    with pytest.raises(ValueError):
        decide(ISSShippingProvider(transport=in_process, config="no_such_config"), **PKG)


def test_the_write_runs_with_the_bound_decision():
    prov = ISSShippingProvider(transport=in_process, passed_agents={"agent-a"})
    d = decide(prov, **PKG)
    p = sp.for_assign_service(d, agent_passed_exam=True)
    result, _ = DecisionEngine().evaluate(DecisionRequest(proposal=p, state=snapshot()))
    out = asyncio.run(prov.execute_service_assignment(ShippingAssignRequest(
        package_id=d.package_id, service=d.service, ledger_key=d.ledger_key,
        proposal_id=p.proposal_id, decision_id=result.result_id)))
    assert out.success and out.service == "2ND_DAY_AIR" and out.decision_id == result.result_id


def test_ground_when_transit_is_short():
    d = decide(ISSShippingProvider(transport=in_process), **{**PKG, "ground_transit_days": 2})
    assert d.service == "GROUND"


def test_the_mcp_server_lists_and_answers_the_shipping_tools():
    server = pytest.importorskip("mcp_servers.shipping.server")
    server.configure_server(ISSShippingProvider(transport=in_process, passed_agents={"agent-a"}))
    tools = asyncio.run(server.mcp_server.list_tools())
    names = {t.name for t in tools}
    assert {"warehouse.shipping.decide_service", "warehouse.shipping.get_decision_record",
            "warehouse.shipping.assign_service"} <= names
    out = json.loads(asyncio.run(server.warehouse_shipping_decide_service(**PKG)))
    assert out["service"] == "2ND_DAY_AIR" and out["self_check_ok"] is True
