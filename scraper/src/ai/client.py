"""Anthropic API client wrapper with retry logic and cost tracking"""

import os
import time
import logging
import json
import re
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

import anthropic
from anthropic import APIError, RateLimitError, APIConnectionError

logger = logging.getLogger(__name__)


def repair_json(json_str: str) -> str:
    """Attempt to repair common JSON issues from LLM output."""
    # Remove any markdown code block wrapping
    if json_str.startswith('```'):
        lines = json_str.split('\n')
        end_idx = len(lines)
        for i in range(1, len(lines)):
            if lines[i].strip() == '```':
                end_idx = i
                break
        json_str = '\n'.join(lines[1:end_idx])

    # Find where the main JSON object/array ends
    depth = 0
    in_string = False
    escape_next = False
    last_close = -1

    for i, char in enumerate(json_str):
        if escape_next:
            escape_next = False
            continue
        if char == '\\' and in_string:
            escape_next = True
            continue
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if char in '{[':
            depth += 1
        elif char in '}]':
            depth -= 1
            if depth == 0:
                last_close = i
                break

    # Truncate at the end of the main JSON structure
    if last_close > 0 and last_close < len(json_str) - 1:
        json_str = json_str[:last_close + 1]

    # Fix trailing commas
    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)

    # Try parsing
    try:
        json.loads(json_str)
        return json_str
    except json.JSONDecodeError:
        pass

    # Try fixing single quotes
    json_str = re.sub(r"'([^']+)'(\s*:)", r'"\1"\2', json_str)
    json_str = re.sub(r":\s*'([^']*)'", r': "\1"', json_str)

    return json_str


class AIError(Exception):
    """Custom exception for AI-related errors"""
    pass


@dataclass
class AIResponse:
    """Structured response from AI"""
    content: str
    parsed_json: Optional[Dict[str, Any]]
    input_tokens: int
    output_tokens: int
    model: str
    stop_reason: str


# Model pricing per 1M tokens (as of Dec 2024)
MODEL_PRICING = {
    'claude-opus-4-5-20251101': {'input': 5.00, 'output': 25.00},
    'claude-opus-4-0-20250514': {'input': 15.00, 'output': 75.00},
    'claude-sonnet-4-5-20251101': {'input': 3.00, 'output': 15.00},
    'claude-sonnet-4-0-20250514': {'input': 3.00, 'output': 15.00},
    'claude-haiku-4-5-20251001': {'input': 1.00, 'output': 5.00},
}

# Default model for different operations
DEFAULT_MODEL = 'claude-haiku-4-5-20251001'
FALLBACK_MODEL = 'claude-sonnet-4-5-20251101'


class AIClient:
    """Wrapper for Anthropic API with retry logic and cost tracking"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        """
        Initialize the AI client.

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            model: Model to use (defaults to claude-3-5-haiku)
            max_retries: Number of retries for transient errors
            retry_delay: Base delay between retries (exponential backoff)
        """
        self.api_key = api_key or os.environ.get('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise AIError(
                "Anthropic API key not found. Set ANTHROPIC_API_KEY environment variable "
                "or pass api_key parameter."
            )

        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.model = model
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Track cumulative usage
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_requests = 0

    def send_message(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        expect_json: bool = False,
        model_override: Optional[str] = None
    ) -> AIResponse:
        """
        Send a message to the AI and get a response.

        Args:
            system_prompt: System prompt for context
            user_message: User message/query
            max_tokens: Maximum tokens in response
            temperature: Temperature for response (0.0 = deterministic)
            expect_json: If True, parse response as JSON
            model_override: Override the default model

        Returns:
            AIResponse with content and usage stats
        """
        model = model_override or self.model
        last_error = None

        for attempt in range(self.max_retries):
            try:
                response = self.client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_prompt,
                    messages=[
                        {"role": "user", "content": user_message}
                    ]
                )

                # Extract content
                content = response.content[0].text if response.content else ""

                # Parse JSON if expected
                parsed_json = None
                if expect_json:
                    try:
                        # Handle potential markdown code blocks
                        json_content = content
                        if json_content.startswith('```'):
                            lines = json_content.split('\n')
                            json_content = '\n'.join(lines[1:-1])
                        parsed_json = json.loads(json_content)
                    except json.JSONDecodeError:
                        # Try repairing the JSON
                        try:
                            repaired = repair_json(content)
                            parsed_json = json.loads(repaired)
                            logger.debug(f"Repaired JSON response")
                        except json.JSONDecodeError as e:
                            logger.warning(f"Failed to parse JSON response: {e}")
                            logger.debug(f"Raw content: {content[:500]}")

                # Track usage
                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens
                self.total_input_tokens += input_tokens
                self.total_output_tokens += output_tokens
                self.total_requests += 1

                logger.debug(
                    f"AI request complete: {input_tokens} input, "
                    f"{output_tokens} output tokens"
                )

                return AIResponse(
                    content=content,
                    parsed_json=parsed_json,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    model=model,
                    stop_reason=response.stop_reason
                )

            except RateLimitError as e:
                last_error = e
                delay = self.retry_delay * (2 ** attempt)
                logger.warning(f"Rate limited, retrying in {delay}s (attempt {attempt + 1}/{self.max_retries})")
                time.sleep(delay)

            except APIConnectionError as e:
                last_error = e
                delay = self.retry_delay * (2 ** attempt)
                logger.warning(f"Connection error, retrying in {delay}s (attempt {attempt + 1}/{self.max_retries})")
                time.sleep(delay)

            except APIError as e:
                # Non-retryable API errors
                logger.error(f"API error: {e}")
                raise AIError(f"Anthropic API error: {e}") from e

        # All retries exhausted
        raise AIError(f"Failed after {self.max_retries} retries: {last_error}")

    def calculate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        model: Optional[str] = None
    ) -> float:
        """
        Calculate the cost of a request in USD.

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            model: Model used (defaults to client's model)

        Returns:
            Cost in USD
        """
        model = model or self.model
        pricing = MODEL_PRICING.get(model, MODEL_PRICING[DEFAULT_MODEL])

        input_cost = (input_tokens / 1_000_000) * pricing['input']
        output_cost = (output_tokens / 1_000_000) * pricing['output']

        return input_cost + output_cost

    def get_usage_stats(self) -> Dict[str, Any]:
        """Get cumulative usage statistics"""
        return {
            'total_input_tokens': self.total_input_tokens,
            'total_output_tokens': self.total_output_tokens,
            'total_requests': self.total_requests,
            'total_cost_usd': self.calculate_cost(
                self.total_input_tokens,
                self.total_output_tokens
            )
        }

    def reset_usage_stats(self):
        """Reset usage statistics"""
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_requests = 0
