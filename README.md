# GoKwik Shipping Connector Agent

LLM-powered agent that generates Python shipping connector code from API documentation.

## Setup

```bash
pip install -e .
cp .env.example .env
# Edit .env with your LLM API key
```

## Run

```bash
python -m backend.main
# Visit http://localhost:8000
```

## Phase 1 Status

✓ Project structure
✓ Core models (GoKwikShipmentStatus, ShipmentTrackingResult)
✓ Config management
✓ LLM client (Anthropic)
✓ Fetcher (Postman collections)
✓ API discovery analyzer (tracks/auth endpoints)
✓ FastAPI routes with SSE
✓ Minimal frontend
⏳ Code generation, validation, status mapping
