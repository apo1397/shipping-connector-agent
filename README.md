# GoKwik Shipping Connector Agent

LLM-powered agent that generates Python shipping connector code from API documentation.

## Setup

1. Copy the environment file:
```bash
cp .env.example .env
```

2. Edit `.env` with your NVIDIA API key:
```bash
# Get your API key from https://build.nvidia.com/
LLM_API_KEY=your_nvidia_api_key_here
```

## Run

```bash
bash run.sh
# Server starts at http://localhost:8000
```

Or manually:
```bash
python3 -m pip install langchain-openai python-dotenv fastapi uvicorn httpx pydantic pydantic-settings sse-starlette jinja2 pyyaml
python3 -m backend.main
```

## Implementation Status

### Completed
✓ Multi-step wizard UI (5 steps)
✓ LLM-powered API discovery (tracking & auth endpoints)
✓ Status extraction & suggestion (LLM maps provider statuses to GoKwik canonical statuses)
✓ Code generation (Jinja2 template + LLM-generated function bodies)
✓ Code validation (AST-based syntax checking + function verification)
✓ Connector storage (`generated_connectors/{provider}/`)
✓ Live testing (execute generated code with user credentials & AWBs)
✓ Download ZIP of generated connector
✓ Server-Sent Events (SSE) for real-time progress updates
✓ Full FastAPI backend with session management
✓ Frontend with Tailwind CSS & Prism.js syntax highlighting

### Pipeline Flow
1. **Input**: User provides API documentation URL
2. **Discovery**: LLM extracts tracking & auth endpoints
3. **Mapping**: LLM suggests mappings from provider statuses to GoKwik statuses (user confirms)
4. **Generation**: LLM generates connector code (authenticate, track_shipment, parse_response functions)
5. **Validation**: Code syntax & structure verified
6. **Storage**: Connector saved to `generated_connectors/{provider_name}/`
7. **Testing**: User provides credentials & AWBs, connector code executed in sandbox
