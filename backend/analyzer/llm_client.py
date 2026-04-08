from typing import Optional, Union
import json
import re
import time
import logging
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class LLMClient:
    """Abstraction over LLM providers using LangChain."""

    def __init__(self, provider: str, api_key: str, model: str, base_url: str = ""):
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

        if provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI
            self.llm = ChatGoogleGenerativeAI(
                model=model,
                google_api_key=api_key,
                temperature=0.1,
                max_output_tokens=4096,
            )
        else:
            from langchain_openai import ChatOpenAI
            self.llm = ChatOpenAI(
                model=model,
                api_key=api_key,
                base_url=base_url or None,
                temperature=0.1,
                max_tokens=4096,
                request_timeout=120,
            )

        logger.info(f"LLMClient initialised | provider={provider} model={model}")

    async def complete(
        self,
        system: str,
        user: str,
        response_format: Optional[type[BaseModel]] = None,
    ) -> Union[str, BaseModel]:
        """Call the LLM with a system and user prompt."""
        label = response_format.__name__ if response_format else "text"
        prompt_chars = len(system) + len(user)

        if response_format:
            schema = json.dumps(response_format.model_json_schema(), indent=2)
            augmented_system = (
                f"{system}\n\n"
                f"IMPORTANT: Respond with a single valid JSON object only.\n"
                f"No markdown, no code fences, no explanation — raw JSON only.\n"
                f"JSON schema to follow:\n{schema}"
            )
            messages = [("system", augmented_system), ("human", user)]
        else:
            messages = [("system", system), ("human", user)]

        logger.info(
            f"LLM request → model={self.model} format={label} "
            f"system_chars={len(system)} user_chars={len(user)} total_chars={prompt_chars}"
        )
        logger.debug(f"LLM system prompt:\n{system}")
        logger.debug(f"LLM user prompt (first 500 chars):\n{user[:500]}")

        t0 = time.perf_counter()
        try:
            response = await self.llm.ainvoke(messages)
            elapsed = time.perf_counter() - t0
            text = response.content.strip()

            logger.info(
                f"LLM response ← format={label} response_chars={len(text)} "
                f"elapsed={elapsed:.2f}s"
            )
            logger.debug(f"LLM raw response:\n{text}")

            if response_format:
                text = self._extract_json(text)
                data = json.loads(text)
                parsed = response_format(**data)
                logger.debug(f"LLM parsed {label}: {parsed}")
                return parsed

            return text

        except json.JSONDecodeError as e:
            elapsed = time.perf_counter() - t0
            logger.error(
                f"LLM JSON parse failed | format={label} elapsed={elapsed:.2f}s | "
                f"error={e} | raw_text={text!r:.300}"
            )
            raise
        except Exception as e:
            elapsed = time.perf_counter() - t0
            logger.error(
                f"LLM API error | format={label} elapsed={elapsed:.2f}s | {type(e).__name__}: {e}"
            )
            raise

    def _extract_json(self, text: str) -> str:
        """Extract raw JSON from a response that may have markdown code fences."""
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            return match.group(1).strip()
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return match.group(0)
        return text
