"""Persist generated connector files to disk."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_BASE_DIR = "generated_connectors"


def save_connector(
    provider_name: str,
    files: dict,
    base_dir: str = DEFAULT_BASE_DIR,
) -> Path:
    """Save connector files to generated_connectors/{provider_name}/."""
    provider_name = provider_name.lower().replace(" ", "_").replace("-", "_")
    output_dir = Path(base_dir) / provider_name
    output_dir.mkdir(parents=True, exist_ok=True)

    for filename, content in files.items():
        filepath = output_dir / filename
        filepath.write_text(content)
        logger.info(f"Saved {filepath}")

    logger.info(f"Connector saved to {output_dir}")
    return output_dir
