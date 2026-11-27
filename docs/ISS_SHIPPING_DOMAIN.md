# ISS Shipping Domain for the NVIDIA Multi-Agent Intelligent Warehouse

The NVIDIA Multi-Agent Intelligent Warehouse blueprint (MAIW, v3.0.0) governs every warehouse action the same way:
agents analyze and propose, and a deterministic layer decides, approves, validates and executes:
STATE, REASON, PROPOSE, DECIDE, EXECUTE, MCP, BACKEND. Its domains are equipment, inventory, labor and wave.
It has no shipping domain: the moment a package's carrier service is chosen, under the shipper's own negotiated
agreement, before the label prints.

This adds that domain, built the way MAIW builds its own, and adds nothing to MAIW's core.

| Piece | Where it goes in MAIW | What it is |
|---|---|---|
| `maiw_contracts/shipping.py` | `packages/maiw-contracts/maiw_contracts/` | Typed requests, results and capability metadata |
| `mcp_servers/shipping/provider.py` | `mcp_servers/shipping/` | The vendor-neutral `ShippingProvider` protocol, and a mock |
| `mcp_servers/shipping/adapters/iss_engine.py` | `mcp_servers/shipping/adapters/` | The ISS decision engine behind the protocol |
| `mcp_servers/shipping/proposal.py` | `mcp_servers/shipping/` | Earned autonomy: the proposal's risk, set from evidence |
| `mcp_servers/shipping/server.py` | `mcp_servers/shipping/` | The MCP server, same shape as Labor and Wave |
| `tests/test_iss_shipping.py` | `tests/integration/` | Runs against MAIW's DecisionEngine and the ISS engine |

## Capabilities

| Capability | Side effect | What it does |
|---|---|---|
| `warehouse.shipping.decide_service` | Read | The ISS engine applies the shipper's agreement to one package: billed weight, the contract tier it selects, the shipper's upgrade rule. It returns the service, the price, the rules that fired, the arithmetic, its own second working of the figures and anything it assumed |
| `warehouse.shipping.get_decision_record` | Read | The fingerprinted record of one decision, which anyone can check later |
| `warehouse.shipping.assign_service` | Write | Puts the decided service on the shipment, only with a proposal and decision bound to an APPROVED DecisionResult |

## Earned Autonomy

Every other MAIW write carries a fixed risk chosen by the capability's author. A shipping decision carries
evidence, so its risk is set from that evidence:

| Risk | When | What MAIW's DecisionEngine does |
|---|---|---|
| Not proposed | The engine refused the package: a required input is missing | Nothing reaches it |
| HIGH | The engine's check of its own arithmetic disagreed | Holds it for a person |
| MEDIUM | Something was assumed or not recognized, the transit or tier was unknown, or the asking agent has not passed the shipper's exam at 100 percent | Holds it for a person |
| LOW | The agreement's own outcome, every figure checked, nothing assumed, asked by an agent that passed the exam | Approves it without a person (its rule 4) |

MAIW's DecisionEngine is unchanged; it receives a risk grounded in evidence. An agent never holds the
agreement: the engine does, and the agent cannot talk its way past it.

## Install And Test

```
# already installed in this copy
cd /path/to/Multi-Agent-Intelligent-Warehouse
ISS_ENGINE_DIR=/path/to/iss-engine PYTHONPATH=. python -m pytest tests/integration/test_iss_shipping.py
```

Running against the live engine instead of in process: set `ISS_ENGINE_URL`, `ISS_ENGINE_KEY` and `ISS_CONFIG`
(for example `parcel_demo`, the sample shipper), and `ISS_EXAM_PASSED` for the agents that passed the exam.

## Status

Built and tested on 26 November 2026 against MAIW `main` at `a6404ed` (v3.0.0 plus fixes), with MAIW's own
DecisionEngine and approval store and the ISS engine v240: 10 of 10 tests pass, on the sample shipper
(invented data). The shipping tools are not yet wired into MAIW's planner and Copilot; that needs a running MAIW
stack with its model endpoints.
