"""LLM-powered code generation for shipping connectors."""

import json
import logging
from datetime import datetime
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from backend.analyzer.llm_client import LLMClient
from .validator import CodeValidator

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"


class CodeGenerator:
    """Generates connector code using Jinja2 templates + LLM."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client
        self.validator = CodeValidator()
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            keep_trailing_newline=True,
        )

    async def generate(
        self,
        provider_name: str,
        tracking_api: dict,
        auth_api: dict,
        confirmed_mappings: dict,
        documentation: str = "",
    ) -> dict:
        """Generate connector code files. Returns {filename: content}."""
        logger.info(f"Generating connector for {provider_name}")

        # Generate function bodies via LLM
        auth_body = await self._generate_auth_body(auth_api, documentation)
        tracking_body = await self._generate_tracking_body(tracking_api, documentation)
        parse_body = await self._generate_parse_body(tracking_api, documentation)

        # Render template
        template = self.jinja_env.get_template("connector_template.py.jinja2")
        connector_code = template.render(
            provider_name=provider_name,
            timestamp=datetime.now().isoformat(),
            mappings=confirmed_mappings,
            auth_body=auth_body,
            tracking_body=tracking_body,
            parse_body=parse_body,
        )

        # Validate with retries
        for attempt in range(3):
            errors = self.validator.validate(connector_code)
            if not errors:
                break
            logger.warning(f"Validation attempt {attempt+1} failed: {errors}")
            if attempt < 2:
                connector_code = await self._fix_code(connector_code, errors)

        # Build output files
        init_code = f'"""Auto-generated connector for {provider_name}."""\nfrom .connector import *\n'

        config_data = {
            "provider_name": provider_name,
            "generated_at": datetime.now().isoformat(),
            "tracking_api": tracking_api,
            "auth_api": auth_api,
            "status_mappings": confirmed_mappings,
        }

        files = {
            "connector.py": connector_code,
            "__init__.py": init_code,
            "config.json": json.dumps(config_data, indent=2),
        }

        logger.info(f"Generated {len(files)} files for {provider_name}")
        return files

    async def _generate_auth_body(self, auth_api: dict, documentation: str) -> str:
        """Generate the authenticate() function body."""
        if not auth_api or auth_api.get("name") == "no_auth" or auth_api.get("url") == "none":
            return (
                'async def authenticate(credentials: dict) -> dict:\n'
                '    """No dedicated auth endpoint — return credentials as headers."""\n'
                '    return {"headers": credentials}\n'
            )

        system = (
            "You are a Python code generator. Generate ONLY the function body for an "
            "async authenticate function that calls the auth API and returns the auth context.\n"
            "Use httpx.AsyncClient for HTTP calls.\n"
            "Return the complete function definition including the `async def authenticate(credentials: dict) -> dict:` signature.\n"
            "The function should return a dict with 'headers' and/or 'token' keys.\n"
            "Handle errors with try/except and raise descriptive exceptions.\n"
            "Output ONLY Python code, no markdown fences, no explanation."
        )
        user = (
            f"Auth API details:\n{json.dumps(auth_api, indent=2)}\n\n"
            f"Documentation excerpt:\n{documentation[:4000]}"
        )

        result = await self.llm.complete(system=system, user=user)
        return self._clean_code(str(result))

    async def _generate_tracking_body(self, tracking_api: dict, documentation: str) -> str:
        """Generate the track_shipment() function body."""
        system = (
            "You are a Python code generator. Generate ONLY the function body for an "
            "async track_shipment function that calls the tracking API.\n"
            "Use httpx.AsyncClient for HTTP calls.\n"
            "Return the complete function definition including the `async def track_shipment(awb_number: str, auth_context: dict) -> dict:` signature.\n"
            "The function should return the raw API response as a dict.\n"
            "Use auth_context['headers'] for request headers.\n"
            "Handle errors with try/except and raise descriptive exceptions.\n"
            "Output ONLY Python code, no markdown fences, no explanation."
        )
        user = (
            f"Tracking API details:\n{json.dumps(tracking_api, indent=2)}\n\n"
            f"Documentation excerpt:\n{documentation[:4000]}"
        )

        result = await self.llm.complete(system=system, user=user)
        return self._clean_code(str(result))

    async def _generate_parse_body(self, tracking_api: dict, documentation: str) -> str:
        """Generate the parse_tracking_response() function body."""
        system = (
            "You are a Python code generator. Generate ONLY the function body for a "
            "parse_tracking_response function that parses the raw tracking API response.\n"
            "Return the complete function definition including the `def parse_tracking_response(raw: dict) -> dict:` signature.\n"
            "The function should return a dict with keys: awb_number, current_status (use map_status()), "
            "current_status_raw, current_status_timestamp, scan_history (list of dicts with timestamp, status, location, remarks).\n"
            "Use the map_status() function (already defined above) to convert provider statuses.\n"
            "Handle missing fields gracefully with .get() and defaults.\n"
            "Output ONLY Python code, no markdown fences, no explanation."
        )
        user = (
            f"Tracking API response schema:\n{json.dumps(tracking_api.get('response_schema', {}), indent=2)}\n\n"
            f"Documentation excerpt:\n{documentation[:4000]}"
        )

        result = await self.llm.complete(system=system, user=user)
        return self._clean_code(str(result))

    async def _fix_code(self, code: str, errors: list) -> str:
        """Ask LLM to fix validation errors in generated code."""
        logger.info(f"Asking LLM to fix {len(errors)} errors")
        system = (
            "You are a Python code fixer. Fix the errors in the given code.\n"
            "Return ONLY the complete fixed Python code, no markdown fences, no explanation."
        )
        user = f"Errors found:\n{chr(10).join(errors)}\n\nCode to fix:\n{code}"

        result = await self.llm.complete(system=system, user=user)
        return self._clean_code(str(result))

    def _clean_code(self, code: str) -> str:
        """Remove markdown code fences if present."""
        code = code.strip()
        if code.startswith("```python"):
            code = code[len("```python"):].strip()
        if code.startswith("```"):
            code = code[3:].strip()
        if code.endswith("```"):
            code = code[:-3].strip()
        return code
