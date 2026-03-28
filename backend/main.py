"""Main FastAPI application."""

import logging
import uvicorn
from backend.config import get_settings
from backend.api import create_app

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def main():
    """Run the FastAPI server."""
    settings = get_settings()
    logger.info(f"Starting GoKwik Connector Agent on {settings.host}:{settings.port}")
    
    app = create_app(settings)
    
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
