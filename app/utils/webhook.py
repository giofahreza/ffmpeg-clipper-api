"""Webhook sender with exponential backoff retry logic."""

import logging
import time
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)


async def send_webhook(url: str, payload: Dict[str, Any]) -> None:
    """
    Send JSON payload to webhook URL with retry logic.

    Args:
        url: Webhook endpoint URL (typically n8n)
        payload: JSON-serializable payload

    Retries:
        3 attempts with exponential backoff (0s, 2s, 4s)
        Logs failures but doesn't raise exceptions
    """
    max_attempts = 3
    delays = [0, 2, 4]  # seconds

    for attempt in range(max_attempts):
        try:
            response = requests.post(
                url,
                json=payload,
                timeout=30,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()

            logger.info(f"Webhook sent successfully to {url}")
            return

        except requests.exceptions.RequestException as e:
            logger.warning(
                f"Webhook attempt {attempt + 1}/{max_attempts} failed: {e}"
            )

            if attempt < max_attempts - 1:
                time.sleep(delays[attempt + 1])
            else:
                logger.error(
                    f"Webhook failed after {max_attempts} attempts. "
                    f"URL: {url}, Payload: {payload}"
                )
