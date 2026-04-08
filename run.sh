#!/bin/bash
set -e

echo "Installing dependencies..."
python3 -m pip install langchain-openai python-dotenv fastapi uvicorn httpx pydantic pydantic-settings sse-starlette jinja2 pyyaml -q

echo "Starting server at http://localhost:8000"
python3 -m backend.main
