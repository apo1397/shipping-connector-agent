"""Live test runner for generated connectors using exec()."""

import asyncio
import logging
import traceback
from typing import List

logger = logging.getLogger(__name__)

CALL_TIMEOUT = 30  # seconds per API call


class ConnectorTester:
    """Runs generated connector code against real APIs."""

    async def test(
        self,
        connector_code: str,
        credentials: dict,
        awb_numbers: List[str],
    ) -> List[dict]:
        """Execute generated connector with real credentials and AWBs."""
        results = []

        # Load the generated code into a namespace
        namespace = {"__builtins__": __builtins__}
        try:
            exec(connector_code, namespace)
        except Exception as e:
            logger.error(f"Failed to load connector code: {e}")
            return [{"awb": awb, "success": False, "error": f"Code load error: {e}"}
                    for awb in awb_numbers]

        authenticate = namespace.get("authenticate")
        track_shipment = namespace.get("track_shipment")
        parse_tracking_response = namespace.get("parse_tracking_response")

        if not all([authenticate, track_shipment, parse_tracking_response]):
            missing = []
            if not authenticate:
                missing.append("authenticate")
            if not track_shipment:
                missing.append("track_shipment")
            if not parse_tracking_response:
                missing.append("parse_tracking_response")
            return [{"awb": awb, "success": False, "error": f"Missing functions: {missing}"}
                    for awb in awb_numbers]

        # Authenticate
        try:
            auth_ctx = await asyncio.wait_for(
                authenticate(credentials), timeout=CALL_TIMEOUT
            )
            logger.info("Authentication successful")
        except asyncio.TimeoutError:
            return [{"awb": awb, "success": False, "error": "Authentication timed out"}
                    for awb in awb_numbers]
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"Auth failed: {e}\n{tb}")
            return [{"awb": awb, "success": False, "error": f"Auth failed: {e}"}
                    for awb in awb_numbers]

        # Track each AWB
        for awb in awb_numbers:
            awb = awb.strip()
            if not awb:
                continue
            try:
                raw = await asyncio.wait_for(
                    track_shipment(awb, auth_ctx), timeout=CALL_TIMEOUT
                )
                parsed = parse_tracking_response(raw)
                results.append({
                    "awb": awb,
                    "success": True,
                    "result": parsed,
                    "raw_response": raw if isinstance(raw, dict) else str(raw),
                    "error": None,
                })
                logger.info(f"AWB {awb}: success")
            except asyncio.TimeoutError:
                results.append({"awb": awb, "success": False, "error": "Request timed out", "result": None, "raw_response": None})
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f"AWB {awb} failed: {e}\n{tb}")
                results.append({"awb": awb, "success": False, "error": str(e), "result": None, "raw_response": None})

        return results
