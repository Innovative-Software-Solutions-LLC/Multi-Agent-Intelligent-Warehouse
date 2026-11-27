# SPDX-FileCopyrightText: Copyright (c) 2026 Innovative Software Solutions LLC. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
ShippingProvider — vendor-neutral carrier-decision source and write boundary.

    ISSShippingProvider   the ISS decision engine (adapters/iss_engine.py): the shipper's own carrier
                          agreement, applied deterministically, with its rules, arithmetic and self-check
    MockShippingProvider  in-memory, for tests

As in every MAIW domain, proposals are built locally (proposal.py); only after the DecisionEngine returns
APPROVED does the executor call execute_service_assignment().
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from maiw_contracts.shipping import (
    ShippingAssignRequest,
    ShippingAssignResult,
    ShippingDecideRequest,
    ShippingDecisionResult,
    ShippingRecordRequest,
    ShippingRecordResult,
)


@runtime_checkable
class ShippingProvider(Protocol):
    """Vendor-neutral shipping decision source and write boundary."""

    async def decide_service(self, request: ShippingDecideRequest) -> ShippingDecisionResult: ...

    async def get_decision_record(self, request: ShippingRecordRequest) -> ShippingRecordResult: ...

    async def execute_service_assignment(self, request: ShippingAssignRequest) -> ShippingAssignResult: ...

    async def exam_passed(self, agent: str) -> bool: ...


class MockShippingProvider:
    """In-memory provider: ground unless transit is 4 days or more, then 2nd Day Air at a flat $11.10."""

    def __init__(self, passed_agents: set[str] | None = None) -> None:
        self._passed = set(passed_agents or ())
        self.assigned: list[ShippingAssignRequest] = []

    async def decide_service(self, request: ShippingDecideRequest) -> ShippingDecisionResult:
        p = request.package
        fast = (p.ground_transit_days or 0) >= 4
        return ShippingDecisionResult(
            package_id=p.package_id, service="2ND_DAY_AIR" if fast else "GROUND", price=11.10 if fast else 12.40,
            baseline=12.40, rules_fired=["contract_tier"] + (["service_upgrade"] if fast else []),
            reasoning=["mock decision"], self_check_ok=True, self_check="mock: all agree",
            assumed=[] if p.ground_transit_days is not None else ["flags.ground_transit_days"],
            configuration="mock", engine_version="mock", source="mock")

    async def get_decision_record(self, request: ShippingRecordRequest) -> ShippingRecordResult:
        return ShippingRecordResult(ledger_key=request.ledger_key, found=False, source="mock")

    async def execute_service_assignment(self, request: ShippingAssignRequest) -> ShippingAssignResult:
        self.assigned.append(request)
        return ShippingAssignResult(success=True, package_id=request.package_id, service=request.service,
                                    proposal_id=request.proposal_id, decision_id=request.decision_id,
                                    ledger_key=request.ledger_key, source="mock",
                                    message=f"{request.package_id} ships {request.service}")

    async def exam_passed(self, agent: str) -> bool:
        return agent in self._passed
