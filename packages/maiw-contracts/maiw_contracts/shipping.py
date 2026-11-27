# SPDX-FileCopyrightText: Copyright (c) 2026 Innovative Software Solutions LLC. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Shipping domain contracts — the carrier decision, under the shipper's own agreement.

Capabilities:
    warehouse.shipping.decide_service       READ   the service a package ships by, decided by the ISS
                                                   engine under the shipper's negotiated carrier agreement
    warehouse.shipping.get_decision_record  READ   the fingerprinted record of one decision: inputs, rules,
                                                   arithmetic, configuration, engine version
    warehouse.shipping.assign_service       WRITE  put the decided service on the shipment; only after the
                                                   DecisionEngine binds an APPROVED DecisionResult

The decision is the agreement's, applied by a deterministic engine: an agent asks, it does not choose.
The engine checks its own arithmetic before it answers (self_check), and says what it assumed. Those facts
set the proposal's risk (see mcp_servers/shipping/proposal.py): autonomy is earned from evidence.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .common import CapabilityMetadata


class ShippingPackage(BaseModel):
    """One package at the pack station, as the scale and the order give it."""

    package_id: str
    order_id: str | None = None
    weight_lb: float = Field(..., gt=0, description="Weighed at the bench")
    length_in: float | None = None
    width_in: float | None = None
    height_in: float | None = None
    box: str | None = Field(default=None, description="The client's box code, where a listed carton is used")
    dest_zip: str | None = None
    ground_transit_days: int | None = Field(default=None, description="The carrier's ground transit to the destination")
    requested_service: str | None = None


class ShippingDecideRequest(BaseModel):
    warehouse_id: str = "default"
    package: ShippingPackage
    requested_by: str = Field(default="shipping-agent", description="The agent asking; its exam standing is read")


class ShippingDecisionResult(BaseModel):
    package_id: str
    service: str = Field(description="The service decided, e.g. GROUND or 2ND_DAY_AIR")
    price: float | None = None
    baseline: float | None = None
    rules_fired: list[str] = Field(default_factory=list)
    reasoning: list[str] = Field(default_factory=list)
    self_check_ok: bool | None = None
    self_check: str = ""
    assumed: list[str] = Field(default_factory=list)
    not_recognized: list[str] = Field(default_factory=list)
    configuration: str = ""
    engine_version: str = ""
    ledger_key: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
    source: str = "iss"


class ShippingRecordRequest(BaseModel):
    warehouse_id: str = "default"
    ledger_key: str


class ShippingRecordResult(BaseModel):
    ledger_key: str
    found: bool
    record: dict[str, Any] = Field(default_factory=dict)
    fingerprint: str | None = None
    source: str = "iss"


class ShippingAssignRequest(BaseModel):
    warehouse_id: str = "default"
    package_id: str
    service: str
    ledger_key: str | None = None
    proposal_id: str
    decision_id: str
    execution_id: str | None = None


class ShippingAssignResult(BaseModel):
    success: bool
    package_id: str
    service: str
    proposal_id: str
    decision_id: str
    ledger_key: str | None = None
    source: str = "iss"
    message: str = ""


SHIPPING_DECIDE_SERVICE_METADATA = CapabilityMetadata(
    name="warehouse.shipping.decide_service", domain="shipping", side_effect="read", risk="low",
    idempotent=True, timeout_seconds=10, required_permission="shipping:read",
    description=("The service a package ships by, decided by the ISS engine under the shipper's own negotiated "
                 "carrier agreement before the label prints: billed weight, the contract tier, the client's upgrade "
                 "rule, with the rules that fired, the arithmetic, the engine's own check of it, and what it assumed."),
)
SHIPPING_GET_DECISION_RECORD_METADATA = CapabilityMetadata(
    name="warehouse.shipping.get_decision_record", domain="shipping", side_effect="read", risk="low",
    idempotent=True, timeout_seconds=10, required_permission="shipping:read",
    description="The fingerprinted record of one shipping decision, for audit: anyone can check it later.",
)
SHIPPING_ASSIGN_SERVICE_METADATA = CapabilityMetadata(
    name="warehouse.shipping.assign_service", domain="shipping", side_effect="write", risk="medium",
    idempotent=True, timeout_seconds=10, required_permission="shipping:write",
    description=("Put the decided service on the shipment. Runs only with a proposal_id and decision_id bound to an "
                 "APPROVED DecisionResult; the risk is set from the decision's evidence, not by the agent."),
)
