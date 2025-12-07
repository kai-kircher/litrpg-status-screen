"""Track AI API costs and usage in the database"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from ..db import get_connection, return_connection
from .client import AIResponse, MODEL_PRICING, DEFAULT_MODEL

logger = logging.getLogger(__name__)


class CostTracker:
    """Track and log AI API usage to the database"""

    def __init__(self):
        """Initialize the cost tracker"""
        self.session_costs = []

    def log_request(
        self,
        response: AIResponse,
        chapter_id: Optional[int],
        processing_type: str,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> Optional[int]:
        """
        Log an AI request to the database.

        Args:
            response: AIResponse from the client
            chapter_id: Chapter being processed (if applicable)
            processing_type: Type of processing ('character_extraction', 'event_attribution')
            success: Whether the request succeeded
            error_message: Error message if failed

        Returns:
            Log entry ID if successful
        """
        cost = self._calculate_cost(
            response.input_tokens,
            response.output_tokens,
            response.model
        )

        # Track in session
        self.session_costs.append({
            'chapter_id': chapter_id,
            'processing_type': processing_type,
            'input_tokens': response.input_tokens,
            'output_tokens': response.output_tokens,
            'cost': cost
        })

        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO ai_processing_log (
                    chapter_id, processing_type, model_used,
                    input_tokens, output_tokens, cost_estimate,
                    success, error_message
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    chapter_id,
                    processing_type,
                    response.model,
                    response.input_tokens,
                    response.output_tokens,
                    cost,
                    success,
                    error_message
                )
            )

            log_id = cursor.fetchone()[0]
            conn.commit()
            cursor.close()

            logger.debug(
                f"Logged AI request: {processing_type}, "
                f"{response.input_tokens}+{response.output_tokens} tokens, "
                f"${cost:.6f}"
            )

            return log_id

        except Exception as e:
            logger.error(f"Failed to log AI request: {e}")
            if conn:
                conn.rollback()
            return None
        finally:
            if conn:
                return_connection(conn)

    def _calculate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str
    ) -> float:
        """Calculate cost in USD"""
        pricing = MODEL_PRICING.get(model, MODEL_PRICING[DEFAULT_MODEL])
        input_cost = (input_tokens / 1_000_000) * pricing['input']
        output_cost = (output_tokens / 1_000_000) * pricing['output']
        return input_cost + output_cost

    def get_session_summary(self) -> Dict[str, Any]:
        """Get summary of costs for the current session"""
        if not self.session_costs:
            return {
                'total_requests': 0,
                'total_input_tokens': 0,
                'total_output_tokens': 0,
                'total_cost_usd': 0.0,
                'by_type': {}
            }

        total_input = sum(c['input_tokens'] for c in self.session_costs)
        total_output = sum(c['output_tokens'] for c in self.session_costs)
        total_cost = sum(c['cost'] for c in self.session_costs)

        # Group by processing type
        by_type = {}
        for c in self.session_costs:
            pt = c['processing_type']
            if pt not in by_type:
                by_type[pt] = {
                    'requests': 0,
                    'input_tokens': 0,
                    'output_tokens': 0,
                    'cost': 0.0
                }
            by_type[pt]['requests'] += 1
            by_type[pt]['input_tokens'] += c['input_tokens']
            by_type[pt]['output_tokens'] += c['output_tokens']
            by_type[pt]['cost'] += c['cost']

        return {
            'total_requests': len(self.session_costs),
            'total_input_tokens': total_input,
            'total_output_tokens': total_output,
            'total_cost_usd': total_cost,
            'by_type': by_type
        }

    def reset_session(self):
        """Reset session tracking"""
        self.session_costs = []


def get_cost_stats(
    days: int = 30,
    processing_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get cost statistics from the database.

    Args:
        days: Number of days to look back
        processing_type: Filter by processing type (optional)

    Returns:
        Dictionary with cost statistics
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cutoff = datetime.now() - timedelta(days=days)

        # Base query
        base_where = "WHERE processed_at >= %s"
        params = [cutoff]

        if processing_type:
            base_where += " AND processing_type = %s"
            params.append(processing_type)

        # Total stats
        cursor.execute(
            f"""
            SELECT
                COUNT(*) as total_requests,
                COALESCE(SUM(input_tokens), 0) as total_input_tokens,
                COALESCE(SUM(output_tokens), 0) as total_output_tokens,
                COALESCE(SUM(cost_estimate), 0) as total_cost,
                COUNT(DISTINCT chapter_id) as chapters_processed
            FROM ai_processing_log
            {base_where}
            """,
            params
        )
        row = cursor.fetchone()
        stats = {
            'period_days': days,
            'total_requests': row[0],
            'total_input_tokens': row[1],
            'total_output_tokens': row[2],
            'total_cost_usd': float(row[3]),
            'chapters_processed': row[4]
        }

        # By model
        cursor.execute(
            f"""
            SELECT
                model_used,
                COUNT(*) as requests,
                SUM(input_tokens) as input_tokens,
                SUM(output_tokens) as output_tokens,
                SUM(cost_estimate) as cost
            FROM ai_processing_log
            {base_where}
            GROUP BY model_used
            ORDER BY cost DESC
            """,
            params
        )
        stats['by_model'] = {
            row[0]: {
                'requests': row[1],
                'input_tokens': row[2],
                'output_tokens': row[3],
                'cost': float(row[4])
            }
            for row in cursor.fetchall()
        }

        # By type
        cursor.execute(
            f"""
            SELECT
                processing_type,
                COUNT(*) as requests,
                SUM(input_tokens) as input_tokens,
                SUM(output_tokens) as output_tokens,
                SUM(cost_estimate) as cost
            FROM ai_processing_log
            {base_where}
            GROUP BY processing_type
            ORDER BY cost DESC
            """,
            params
        )
        stats['by_type'] = {
            row[0]: {
                'requests': row[1],
                'input_tokens': row[2],
                'output_tokens': row[3],
                'cost': float(row[4])
            }
            for row in cursor.fetchall()
        }

        cursor.close()
        return stats

    except Exception as e:
        logger.error(f"Failed to get cost stats: {e}")
        return {
            'error': str(e),
            'total_requests': 0,
            'total_cost_usd': 0.0
        }
    finally:
        if conn:
            return_connection(conn)
