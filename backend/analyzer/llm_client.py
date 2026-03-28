"""LLM client abstraction for different providers."""

import json
import logging
from typing import Any
from pydantic import BaseModel
from anthropic import Anthropic, APIError

logger = logging.getLogger(__name__)


class LLMClient:
    """Abstraction over different LLM providers."""

    def __init__(self, provider: str, api_key: str, model: str):
        self.provider = provider
        self.api_key = api_key
        self.model = model

        if provider == "anthropic":
            self.client = Anthropic(api_key=api_key)
        elif provider in ["openai", "deepseek", "nvidia"]:
            # Will implement other providers later
            raise NotImplementedError(f"Provider {provider} not yet implemented")
        else:
            raise ValueError(f"Unknown provider: {provider}")

    async def complete(
        self,
        system: str,
        user: str,
        response_format: type[BaseModel] | None = None,
    ) -> str | BaseModel:
        """
        Call the LLM with a system and user prompt.

        Args:
            system: System prompt
            user: User prompt
            response_format: Optional Pydantic model for structured output

        Returns:
            Either the raw string response or a parsed Pydantic model
        """
        if self.provider == "anthropic":
            return await self._complete_anthropic(system, user, response_format)
        else:
            raise NotImplementedError(f"Provider {self.provider} not implemented")

    async def _complete_anthropic(
        self,
        system: str,
        user: str,
        response_format: type[BaseModel] | None = None,
    ) -> str | BaseModel:
        """Call Claude API."""
        try:
            if response_format:
                # Use tool_use for structured output
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=system,
                    tools=[
                        {
                            "name": "return_structured_output",
                            "description": "Return structured output",
                            "input_schema": response_format.model_json_schema(),
                        }
                    ],
                    messages=[{"role": "user", "content": user}],
                )

                # Extract tool use response
                for block in response.content:
                    if hasattr(block, "input"):
                        return response_format(**block.input)

                raise ValueError("No structured output from LLM")
            else:
                # Simple text response
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                return response.content[0].text

        except APIError as e:
            logger.error(f"LLM API error: {e}")
            raise
