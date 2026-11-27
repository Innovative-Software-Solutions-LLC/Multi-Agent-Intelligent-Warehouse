# SPDX-FileCopyrightText: Copyright (c) 2026 Innovative Software Solutions LLC. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
ISSShippingProvider — the ISS decision engine behind the shipping domain.

The engine holds the shipper's negotiated carrier agreement as configuration and applies it to one package
at a time: billed weight (the greater of actual and dimensional), the contract tier it selects, the
client's own upgrade rule. It returns the decision with the rules that fired, the arithmetic, its own
second working of the figures (self_check) and what it assumed. Agents never hold the agreement: the
engine does. Nothing here writes to a carrier or to the client's system.

Settings (environment):
    ISS_ENGINE_URL      the engine's address
    ISS_ENGINE_KEY      the client's key (never logged)
    ISS_CONFIG          the client's configuration, e.g. parcel_demo for the sample shipper
    ISS_EXAM_PASSED     agents that passed the client's exam at 100%, comma-separated; the engine's own
                        exam results are read as well where the configuration keeps them
Standard library only; the transport can be replaced (tests run the engine in process).
"""

from __future__ import annotations

import asyncio
import json
import os
import urllib.request
from typing import Any, Callable

from maiw_contracts.shipping import (
    ShippingAssignRequest,
    ShippingAssignResult,
    ShippingDecideRequest,
    ShippingDecisionResult,
    ShippingRecordRequest,
    ShippingRecordResult,
)

Transport = Callable[[str, str, dict[str, Any] | None], tuple[int, Any]]


def http_transport(base: str, key: str, timeout: float = 10.0) -> Transport:
    def call(method: str, path: str, body: dict[str, Any] | None) -> tuple[int, Any]:
        req = urllib.request.Request(base.rstrip("/") + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"content-type": "application/json", "x-iss-key": key})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode() or "{}")
            except ValueError:
                return e.code, {"error": str(e)}
    return call


class ISSShippingProvider:
    def __init__(self, transport: Transport | None = None, config: str | None = None,
                 passed_agents: set[str] | None = None) -> None:
        self._config = config or os.getenv("ISS_CONFIG", "parcel_demo")
        self._t = transport or http_transport(os.getenv("ISS_ENGINE_URL", ""), os.getenv("ISS_ENGINE_KEY", ""))
        env = {a.strip() for a in os.getenv("ISS_EXAM_PASSED", "").split(",") if a.strip()}
        self._passed = set(passed_agents or ()) | env

    async def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
        return await asyncio.to_thread(self._t, method, path, body)

    async def decide_service(self, request: ShippingDecideRequest) -> ShippingDecisionResult:
        p = request.package
        ship: dict[str, Any] = {"id": p.package_id, "weight_lb": p.weight_lb}
        for k in ("length_in", "width_in", "height_in", "dest_zip"):
            if getattr(p, k) is not None:
                ship[k] = getattr(p, k)
        flags: dict[str, Any] = {}
        if p.ground_transit_days is not None:
            flags["ground_transit_days"] = p.ground_transit_days
        if p.box:
            flags["box"] = p.box
        if p.requested_service:
            flags["requested_service"] = p.requested_service
        if flags:
            ship["flags"] = flags
        st, out = await self._call("POST", f"/decide?config={self._config}", {"shipments": [ship]})
        if st != 200 or not (out or {}).get("decisions"):
            errs = (out or {}).get("errors") or [{"error": (out or {}).get("error", f"HTTP {st}")}]
            raise ValueError("the engine refused the package: " + "; ".join(str(e.get("error")) for e in errs))
        d = out["decisions"][0]
        sc = d.get("self_check") or {}
        inp = d.get("inputs") or {}
        return ShippingDecisionResult(
            package_id=str(d.get("shipment_id") or p.package_id), service=str(d.get("decision")), price=d.get("total"),
            baseline=d.get("baseline"), rules_fired=list(d.get("rules_fired") or []), reasoning=list(d.get("reasoning") or []),
            self_check_ok=sc.get("ok"), self_check=str(sc.get("summary") or ""),
            assumed=[str(x) for x in inp.get("assumed") or []],
            not_recognized=[str(x.get("field") if isinstance(x, dict) else x) for x in inp.get("not_recognized") or []],
            configuration=str(out.get("config") or self._config), engine_version=str(d.get("engine_version") or ""),
            ledger_key=d.get("ledger_key"), detail=d.get("detail") or {}, source="iss")

    async def get_decision_record(self, request: ShippingRecordRequest) -> ShippingRecordResult:
        st, out = await self._call("GET", f"/record/decision?id={request.ledger_key}")
        found = st == 200 and isinstance(out, dict) and bool(out.get("record") or out.get("fingerprint"))
        return ShippingRecordResult(ledger_key=request.ledger_key, found=found, record=out if found else {},
                                    fingerprint=(out or {}).get("fingerprint") if found else None)

    async def execute_service_assignment(self, request: ShippingAssignRequest) -> ShippingAssignResult:
        # The assignment lives in the warehouse's own shipment record; the engine keeps the decision's record.
        return ShippingAssignResult(success=True, package_id=request.package_id, service=request.service,
                                    proposal_id=request.proposal_id, decision_id=request.decision_id,
                                    ledger_key=request.ledger_key,
                                    message=f"{request.package_id} ships {request.service}, as decided under the agreement")

    async def exam_passed(self, agent: str) -> bool:
        if agent in self._passed:
            return True
        st, out = await self._call("GET", f"/parcel/exam/results?config={self._config}")
        for r in (out or {}).get("results") or [] if st == 200 else []:
            if str(r.get("agent") or r.get("model") or "") == agent and (r.get("passed") or r.get("score_pct") == 100):
                return True
        return False
