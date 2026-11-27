# SPDX-FileCopyrightText: Copyright (c) 2026 Innovative Software Solutions LLC. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW Shipping MCP Server — the carrier decision, under the shipper's own agreement (ISS decision engine).

    warehouse.shipping.decide_service       READ
    warehouse.shipping.get_decision_record  READ
    warehouse.shipping.assign_service       WRITE  only with proposal_id and decision_id bound to APPROVED

Same shape as the Labor and Wave servers: MCP client -> this server -> ShippingProvider
(ISSShippingProvider, or MockShippingProvider for tests).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from mcp.server import MCPServer

from maiw_contracts.shipping import (
    SHIPPING_ASSIGN_SERVICE_METADATA,
    SHIPPING_DECIDE_SERVICE_METADATA,
    SHIPPING_GET_DECISION_RECORD_METADATA,
    ShippingAssignRequest,
    ShippingDecideRequest,
    ShippingPackage,
    ShippingRecordRequest,
)
from maiw_mcp.errors import BackendUnavailable

logger = logging.getLogger(__name__)

mcp_server = MCPServer(
    "MAIW Shipping Server",
    instructions=("The carrier decision for each package, made by the ISS engine under the shipper's own negotiated "
                  "agreement before the label prints. Ask with warehouse.shipping.decide_service; the answer carries "
                  "the rules, the arithmetic, the engine's self-check and what it assumed. assign_service executes "
                  "APPROVED proposals only."),
)

_provider = None  # type: Any


def configure_server(provider: Any) -> None:
    global _provider
    _provider = provider


def _get_provider() -> Any:
    global _provider
    if _provider is None:
        from mcp_servers.shipping.adapters.iss_engine import ISSShippingProvider
        _provider = ISSShippingProvider()
    return _provider


@mcp_server.tool(name=SHIPPING_DECIDE_SERVICE_METADATA.name, description=SHIPPING_DECIDE_SERVICE_METADATA.description)
async def warehouse_shipping_decide_service(package_id: str, weight_lb: float, warehouse_id: str = "default",
                                            length_in: float | None = None, width_in: float | None = None,
                                            height_in: float | None = None, box: str | None = None,
                                            dest_zip: str | None = None, ground_transit_days: int | None = None,
                                            requested_service: str | None = None,
                                            requested_by: str = "shipping-agent") -> str:
    req = ShippingDecideRequest(warehouse_id=warehouse_id, requested_by=requested_by, package=ShippingPackage(
        package_id=package_id, weight_lb=weight_lb, length_in=length_in, width_in=width_in, height_in=height_in,
        box=box, dest_zip=dest_zip, ground_transit_days=ground_transit_days, requested_service=requested_service))
    try:
        result = await _get_provider().decide_service(req)
    except ValueError:
        raise
    except Exception as exc:
        raise BackendUnavailable(f"Shipping decision failed: {exc}") from exc
    return json.dumps(result.model_dump())


@mcp_server.tool(name=SHIPPING_GET_DECISION_RECORD_METADATA.name, description=SHIPPING_GET_DECISION_RECORD_METADATA.description)
async def warehouse_shipping_get_decision_record(ledger_key: str, warehouse_id: str = "default") -> str:
    try:
        result = await _get_provider().get_decision_record(ShippingRecordRequest(warehouse_id=warehouse_id, ledger_key=ledger_key))
    except Exception as exc:
        raise BackendUnavailable(f"Shipping record fetch failed: {exc}") from exc
    return json.dumps(result.model_dump())


@mcp_server.tool(name=SHIPPING_ASSIGN_SERVICE_METADATA.name, description=SHIPPING_ASSIGN_SERVICE_METADATA.description)
async def warehouse_shipping_assign_service(package_id: str, service: str, proposal_id: str, decision_id: str,
                                            warehouse_id: str = "default", ledger_key: str | None = None,
                                            execution_id: str | None = None) -> str:
    req = ShippingAssignRequest(warehouse_id=warehouse_id, package_id=package_id, service=service, ledger_key=ledger_key,
                                proposal_id=proposal_id, decision_id=decision_id, execution_id=execution_id)
    try:
        result = await _get_provider().execute_service_assignment(req)
    except Exception as exc:
        raise BackendUnavailable(f"Shipping assignment failed: {exc}") from exc
    return json.dumps(result.model_dump())


if __name__ == "__main__":
    transport = os.getenv("MAIW_MCP_TRANSPORT", "stdio")
    port = int(os.getenv("MAIW_MCP_SHIPPING_PORT", "8770"))
    host = os.getenv("MAIW_MCP_SHIPPING_HOST", "0.0.0.0")
    if transport == "streamable-http":
        mcp_server.run("streamable-http", host=host, port=port, stateless_http=True)
    else:
        mcp_server.run("stdio")
