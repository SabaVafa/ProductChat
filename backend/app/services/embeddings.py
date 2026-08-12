"""Mistral embeddings via the REST API.

Uses `requests` directly instead of the `mistralai` SDK so the app runs on
Python versions the pinned SDK (and its old `orjson` dependency) has no wheels
for. The public interface is unchanged.
"""

from typing import List, Optional
from app.config import settings
import requests
import logging

logger = logging.getLogger(__name__)

MISTRAL_API_BASE = "https://api.mistral.ai/v1"
REQUEST_TIMEOUT = 60


class EmbeddingsService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.MISTRAL_API_KEY
        self.model = "mistral-embed"

    def set_api_key(self, api_key: str):
        """Update the API key."""
        self.api_key = api_key

    def _embed(self, inputs: List[str]) -> List[List[float]]:
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
        resp.raise_for_status()
        data = resp.json()
        return [item["embedding"] for item in data["data"]]

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

    def embed_product(self, product: dict) -> List[float]:
        """Generate embedding for a product by combining relevant fields."""
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
            text_parts.append(f"Price: ${product['price']}")

        combined_text = " | ".join(text_parts)
        return self.embed_text(combined_text)
