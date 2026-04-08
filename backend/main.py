"""Main FastAPI application."""

import logging
import uvicorn
from backend.config import get_settings
from backend.api import create_app

logger = logging.getLogger(__name__)


def main():
    """Run the FastAPI server."""
    settings = get_settings()

    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    logger.info(
        f"Starting GoKwik Connector Agent | host={settings.host} port={settings.port} "
        f"debug={settings.debug} llm_provider={settings.llm_provider} "
        f"llm_model={settings.llm_model}"
    )
    
    app = create_app(settings)
    
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
