"""Anthropic Batch API client for cost-effective bulk processing"""

import os
import time
import logging
import json
from typing import Optional, Dict, Any, List, Generator
from dataclasses import dataclass
from enum import Enum

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

from .client import AIError, MODEL_PRICING, DEFAULT_MODEL

logger = logging.getLogger(__name__)


class BatchStatus(Enum):
    """Status of a batch job"""
    IN_PROGRESS = "in_progress"
    CANCELING = "canceling"
    ENDED = "ended"


class BatchResultType(Enum):
    """Result type for individual batch requests"""
    SUCCEEDED = "succeeded"
    ERRORED = "errored"
    CANCELED = "canceled"
    EXPIRED = "expired"


@dataclass
class BatchRequest:
    """A single request to include in a batch"""
    custom_id: str
    system_prompt: str
    user_message: str
    max_tokens: int = 4096
    temperature: float = 0.0
    model: str = DEFAULT_MODEL
    # Metadata for tracking
    chapter_id: Optional[int] = None
    processing_type: Optional[str] = None


@dataclass
class BatchResult:
    """Result from a single batch request"""
    custom_id: str
    result_type: BatchResultType
    content: Optional[str] = None
    parsed_json: Optional[Dict[str, Any]] = None
    input_tokens: int = 0
    output_tokens: int = 0
    model: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class BatchJob:
    """Represents a batch job"""
    batch_id: str
    processing_status: BatchStatus
    request_counts: Dict[str, int]
    created_at: str
    expires_at: str
    ended_at: Optional[str] = None
    results_url: Optional[str] = None


# Batch pricing is 50% of standard pricing
BATCH_PRICING = {
    model: {'input': pricing['input'] / 2, 'output': pricing['output'] / 2}
    for model, pricing in MODEL_PRICING.items()
}


class BatchClient:
    """Client for Anthropic's Message Batches API

    The Batch API offers 50% cost savings but processes asynchronously
    with results available within 24 hours (usually much faster).

    Use cases:
    - Large-scale processing of many chapters
    - Non-time-sensitive bulk operations
    - Cost optimization for batch operations
    """

    # Maximum requests per batch (API limit is 100,000 but we use a reasonable default)
    MAX_BATCH_SIZE = 10000

    # Default polling interval in seconds
    DEFAULT_POLL_INTERVAL = 60

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL
    ):
        """
        Initialize the batch client.

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            model: Default model to use for requests
        """
        self.api_key = api_key or os.environ.get('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise AIError(
                "Anthropic API key not found. Set ANTHROPIC_API_KEY environment variable "
                "or pass api_key parameter."
            )

        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.model = model

    def create_batch(
        self,
        requests: List[BatchRequest]
    ) -> BatchJob:
        """
        Create a new message batch for asynchronous processing.

        Args:
            requests: List of BatchRequest objects to process

        Returns:
            BatchJob with the batch ID and initial status
        """
        if len(requests) > self.MAX_BATCH_SIZE:
            raise AIError(f"Batch size {len(requests)} exceeds maximum {self.MAX_BATCH_SIZE}")

        if not requests:
            raise AIError("Cannot create empty batch")

        # Convert to API format
        api_requests = []
        for req in requests:
            api_requests.append(
                Request(
                    custom_id=req.custom_id,
                    params=MessageCreateParamsNonStreaming(
                        model=req.model,
                        max_tokens=req.max_tokens,
                        temperature=req.temperature,
                        system=req.system_prompt,
                        messages=[{
                            "role": "user",
                            "content": req.user_message
                        }]
                    )
                )
            )

        try:
            response = self.client.messages.batches.create(requests=api_requests)

            logger.info(f"Created batch {response.id} with {len(requests)} requests")

            return BatchJob(
                batch_id=response.id,
                processing_status=BatchStatus(response.processing_status),
                request_counts={
                    'processing': response.request_counts.processing,
                    'succeeded': response.request_counts.succeeded,
                    'errored': response.request_counts.errored,
                    'canceled': response.request_counts.canceled,
                    'expired': response.request_counts.expired,
                },
                created_at=str(response.created_at),
                expires_at=str(response.expires_at),
                ended_at=str(response.ended_at) if response.ended_at else None,
                results_url=response.results_url
            )

        except anthropic.APIError as e:
            logger.error(f"Failed to create batch: {e}")
            raise AIError(f"Failed to create batch: {e}") from e

    def get_batch_status(self, batch_id: str) -> BatchJob:
        """
        Get the current status of a batch.

        Args:
            batch_id: The batch ID to check

        Returns:
            BatchJob with current status
        """
        try:
            response = self.client.messages.batches.retrieve(batch_id)

            return BatchJob(
                batch_id=response.id,
                processing_status=BatchStatus(response.processing_status),
                request_counts={
                    'processing': response.request_counts.processing,
                    'succeeded': response.request_counts.succeeded,
                    'errored': response.request_counts.errored,
                    'canceled': response.request_counts.canceled,
                    'expired': response.request_counts.expired,
                },
                created_at=str(response.created_at),
                expires_at=str(response.expires_at),
                ended_at=str(response.ended_at) if response.ended_at else None,
                results_url=response.results_url
            )

        except anthropic.APIError as e:
            logger.error(f"Failed to get batch status: {e}")
            raise AIError(f"Failed to get batch status: {e}") from e

    def wait_for_batch(
        self,
        batch_id: str,
        poll_interval: int = DEFAULT_POLL_INTERVAL,
        timeout: Optional[int] = None,
        progress_callback: Optional[callable] = None
    ) -> BatchJob:
        """
        Wait for a batch to complete processing.

        Args:
            batch_id: The batch ID to wait for
            poll_interval: Seconds between status checks (default 60)
            timeout: Maximum seconds to wait (default None = no timeout)
            progress_callback: Optional callback(BatchJob) called on each poll

        Returns:
            BatchJob with final status
        """
        start_time = time.time()

        while True:
            batch = self.get_batch_status(batch_id)

            if progress_callback:
                progress_callback(batch)

            if batch.processing_status == BatchStatus.ENDED:
                logger.info(f"Batch {batch_id} completed: {batch.request_counts}")
                return batch

            if timeout and (time.time() - start_time) > timeout:
                raise AIError(f"Batch {batch_id} timed out after {timeout} seconds")

            logger.info(
                f"Batch {batch_id} still processing: "
                f"{batch.request_counts['processing']} remaining"
            )
            time.sleep(poll_interval)

    def get_batch_results(
        self,
        batch_id: str,
        expect_json: bool = False
    ) -> Generator[BatchResult, None, None]:
        """
        Stream results from a completed batch.

        Args:
            batch_id: The batch ID to get results for
            expect_json: If True, attempt to parse content as JSON

        Yields:
            BatchResult for each request in the batch
        """
        try:
            for result in self.client.messages.batches.results(batch_id):
                batch_result = self._parse_batch_result(result, expect_json)
                yield batch_result

        except anthropic.APIError as e:
            logger.error(f"Failed to get batch results: {e}")
            raise AIError(f"Failed to get batch results: {e}") from e

    def _parse_batch_result(
        self,
        result,
        expect_json: bool
    ) -> BatchResult:
        """Parse a single batch result into our BatchResult format"""
        custom_id = result.custom_id
        result_type = BatchResultType(result.result.type)

        if result_type == BatchResultType.SUCCEEDED:
            message = result.result.message
            content = message.content[0].text if message.content else ""

            parsed_json = None
            if expect_json and content:
                try:
                    json_content = content
                    if json_content.startswith('```'):
                        lines = json_content.split('\n')
                        json_content = '\n'.join(lines[1:-1])
                    parsed_json = json.loads(json_content)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON for {custom_id}: {e}")

            return BatchResult(
                custom_id=custom_id,
                result_type=result_type,
                content=content,
                parsed_json=parsed_json,
                input_tokens=message.usage.input_tokens,
                output_tokens=message.usage.output_tokens,
                model=message.model
            )

        elif result_type == BatchResultType.ERRORED:
            error = result.result.error
            error_msg = f"{error.type}: {error.message}" if hasattr(error, 'message') else str(error)
            return BatchResult(
                custom_id=custom_id,
                result_type=result_type,
                error_message=error_msg
            )

        else:  # CANCELED or EXPIRED
            return BatchResult(
                custom_id=custom_id,
                result_type=result_type,
                error_message=f"Request {result_type.value}"
            )

    def cancel_batch(self, batch_id: str) -> BatchJob:
        """
        Cancel a batch that is currently processing.

        Args:
            batch_id: The batch ID to cancel

        Returns:
            BatchJob with canceling status
        """
        try:
            response = self.client.messages.batches.cancel(batch_id)

            logger.info(f"Initiated cancellation for batch {batch_id}")

            return BatchJob(
                batch_id=response.id,
                processing_status=BatchStatus(response.processing_status),
                request_counts={
                    'processing': response.request_counts.processing,
                    'succeeded': response.request_counts.succeeded,
                    'errored': response.request_counts.errored,
                    'canceled': response.request_counts.canceled,
                    'expired': response.request_counts.expired,
                },
                created_at=str(response.created_at),
                expires_at=str(response.expires_at),
                ended_at=str(response.ended_at) if response.ended_at else None,
                results_url=response.results_url
            )

        except anthropic.APIError as e:
            logger.error(f"Failed to cancel batch: {e}")
            raise AIError(f"Failed to cancel batch: {e}") from e

    def list_batches(self, limit: int = 20) -> List[BatchJob]:
        """
        List recent batches.

        Args:
            limit: Maximum number of batches to return

        Returns:
            List of BatchJob objects
        """
        try:
            batches = []
            for batch in self.client.messages.batches.list(limit=limit):
                batches.append(BatchJob(
                    batch_id=batch.id,
                    processing_status=BatchStatus(batch.processing_status),
                    request_counts={
                        'processing': batch.request_counts.processing,
                        'succeeded': batch.request_counts.succeeded,
                        'errored': batch.request_counts.errored,
                        'canceled': batch.request_counts.canceled,
                        'expired': batch.request_counts.expired,
                    },
                    created_at=str(batch.created_at),
                    expires_at=str(batch.expires_at),
                    ended_at=str(batch.ended_at) if batch.ended_at else None,
                    results_url=batch.results_url
                ))
            return batches

        except anthropic.APIError as e:
            logger.error(f"Failed to list batches: {e}")
            raise AIError(f"Failed to list batches: {e}") from e

    def calculate_batch_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        model: Optional[str] = None
    ) -> float:
        """
        Calculate the cost of batch processing in USD.
        Batch processing is 50% cheaper than standard API.

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            model: Model used (defaults to client's model)

        Returns:
            Cost in USD
        """
        model = model or self.model
        pricing = BATCH_PRICING.get(model, BATCH_PRICING[DEFAULT_MODEL])

        input_cost = (input_tokens / 1_000_000) * pricing['input']
        output_cost = (output_tokens / 1_000_000) * pricing['output']

        return input_cost + output_cost
