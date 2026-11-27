# SPDX-FileCopyrightText: Copyright (c) 2026 Innovative Software Solutions LLC. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Earned autonomy: the shipping proposal's risk is set from the decision's evidence, never by the agent.

Every other MAIW write carries a fixed risk chosen by its author. A shipping decision carries evidence the
DecisionEngine can use: the ISS engine has applied the shipper's own agreement, worked its figures a second
way, and said what it assumed. So:

  CRITICAL  never proposed: the engine refused the package (a required input missing)
  HIGH      the engine's own check of its arithmetic disagreed: a person looks before anything ships
  MEDIUM    the decision rests on something assumed or not recognized, the transit or the tier was unknown,
            or the asking agent has not passed the shipper's exam at 100 percent: a person approves
  LOW       the agreement's own outcome, every figure checked, nothing assumed, asked by an agent that passed
            the shipper's exam at 100 percent: the DecisionEngine approves without a person (rule 4)

The DecisionEngine is unchanged; it receives a better-grounded risk. Approval still binds to the proposal.
"""

from __future__ import annotations

from maiw_contracts.shipping import ShippingDecisionResult
from maiw_decision.proposal import ActionProposal, RiskLevel

UNSURE_RULES = {"transit_unknown", "unrated_no_dimensions", "upgrade_blocked_unrated", "box_unknown", "weight_implausible"}


def risk_for(decision: ShippingDecisionResult, agent_passed_exam: bool) -> tuple[RiskLevel, list[str]]:
    why: list[str] = []
    if decision.self_check_ok is False:
        return RiskLevel.HIGH, [f"the engine's check of its own arithmetic disagreed: {decision.self_check}"]
    if decision.assumed:
        why.append("assumed: " + ", ".join(decision.assumed))
    if decision.not_recognized:
        why.append("not recognized: " + ", ".join(decision.not_recognized))
    unsure = sorted(set(decision.rules_fired) & UNSURE_RULES)
    if unsure:
        why.append("decided without: " + ", ".join(unsure))
    if decision.self_check_ok is None:
        why.append("no self-check on this decision")
    if not agent_passed_exam:
        why.append("the asking agent has not passed the shipper's exam at 100 percent")
    return (RiskLevel.MEDIUM, why) if why else (RiskLevel.LOW, ["the agreement's own outcome; every figure checked; "
                                                                 "nothing assumed; exam passed"])


def for_assign_service(decision: ShippingDecisionResult, *, agent_passed_exam: bool, requested_by: str = "shipping-agent",
                       warehouse_id: str = "default", trace_id: str | None = None) -> ActionProposal:
    risk, why = risk_for(decision, agent_passed_exam)
    return ActionProposal(
        action="warehouse.shipping.assign_service",
        parameters={"package_id": decision.package_id, "service": decision.service, "ledger_key": decision.ledger_key,
                    "warehouse_id": warehouse_id, "price": decision.price, "configuration": decision.configuration,
                    "engine_version": decision.engine_version, "evidence": why},
        domain="shipping", risk_level=risk,
        reason=(f"{decision.package_id} ships {decision.service} under the shipper's agreement"
                + (f" at ${decision.price:,.2f}" if decision.price is not None else "") + ". " + "; ".join(why)),
        requested_by=requested_by, requires_approval=risk != RiskLevel.LOW, trace_id=trace_id,
        idempotency_key=f"shipping:{decision.package_id}:{decision.ledger_key or decision.service}")
