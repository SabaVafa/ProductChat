"""Mistral embeddings via the REST API.

Uses `requests` directly instead of the `mistralai` SDK so the app runs on
Python versions the pinned SDK (and its old `orjson` dependency) has no wheels
for. The public interface is unchanged.
"""

from typing import List, Optional
from app.config import settings
import requests
import logging
import time

logger = logging.getLogger(__name__)

MISTRAL_API_BASE = "https://api.mistral.ai/v1"
REQUEST_TIMEOUT = 60
MAX_RETRIES = 5


class EmbeddingsService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.MISTRAL_API_KEY
        self.model = "mistral-embed"

    def set_api_key(self, api_key: str):
        """Update the API key."""
        self.api_key = api_key

    def _embed(self, inputs: List[str]) -> List[List[float]]:
        """Call the embeddings API, retrying on rate limits (429) and 5xx.

        Without retries, a 429 during a large indexing run silently drops
        products from the vector index — they exist in the DB but can never be
        found by search.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(MAX_RETRIES):
            resp = requests.post(
                f"{MISTRAL_API_BASE}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={"model": self.model, "input": inputs},
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = resp.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else min(2 ** attempt, 15)
                logger.warning(
                    f"Embeddings HTTP {resp.status_code}, retry {attempt+1}/{MAX_RETRIES} in {wait}s"
                )
                time.sleep(wait)
                last_exc = requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
                continue
            resp.raise_for_status()
            data = resp.json()
            return [item["embedding"] for item in data["data"]]
        raise last_exc or RuntimeError("Embeddings request failed after retries")

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        try:
            return self._embed([text])[0]
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        try:
            return self._embed(texts)
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            raise

    @staticmethod
    def compose_product_text(product: dict) -> str:
        """Build the text that represents a product for embedding."""
        return EmbeddingsService._compose(product)

    def embed_product(self, product: dict) -> List[float]:
        """Generate embedding for a product by combining relevant fields."""
        return self.embed_text(self._compose(product))

    @staticmethod
    def _compose(product: dict) -> str:
        text_parts = []

        if product.get("name"):
            text_parts.append(f"Name: {product['name']}")

        if product.get("description"):
            text_parts.append(f"Description: {product['description']}")

        if product.get("category"):
            text_parts.append(f"Category: {product['category']}")

        if product.get("brand"):
            text_parts.append(f"Brand: {product['brand']}")

        if product.get("attributes"):
            attrs = product["attributes"]
            if isinstance(attrs, dict):
                for key, value in attrs.items():
                    text_parts.append(f"{key}: {value}")
            elif isinstance(attrs, list):
                for attr in attrs:
                    text_parts.append(str(attr))

        if product.get("price"):
            # EUR shop — "$" was wrong here too (harmless for similarity, but
            # keep the composed text truthful). Only affects future embeddings.
            text_parts.append(f"Price: {product['price']} EUR")

        return " | ".join(text_parts)
