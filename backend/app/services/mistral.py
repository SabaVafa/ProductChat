"""Mistral chat completions via the REST API.

Uses `requests` directly instead of the `mistralai` SDK so the app runs on
Python versions the pinned SDK (and its old `orjson` dependency) has no wheels
for. `ChatMessage` is kept as a thin dict shim so existing call sites don't
change.
"""

from typing import List, Dict, Any, Optional
from app.config import settings
import requests
import logging
import json

logger = logging.getLogger(__name__)

MISTRAL_API_BASE = "https://api.mistral.ai/v1"
REQUEST_TIMEOUT = 60


def ChatMessage(role: str, content: str) -> Dict[str, str]:
    """Compatibility shim for the old mistralai ChatMessage; just a dict."""
    return {"role": role, "content": content}


class MistralService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.MISTRAL_API_KEY
        self.model = settings.MISTRAL_MODEL
        self.temperature = settings.MISTRAL_TEMPERATURE
        self.max_tokens = settings.MISTRAL_MAX_TOKENS

    def set_config(self, api_key: str, model: str, temperature: float, max_tokens: int):
        """Update configuration."""
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def _chat_request(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /chat/completions and return the parsed JSON response."""
        payload: Dict[str, Any] = {
            "model": model or self.model,
            "messages": [dict(m) for m in messages],
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        resp = requests.post(
            f"{MISTRAL_API_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()

    def chat_content(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
    ) -> str:
        """Return just the assistant message content string."""
        data = self._chat_request(messages, temperature, max_tokens, response_format, model)
        return data["choices"][0]["message"]["content"]

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """Generate chat completion."""
        try:
            return self.chat_content(messages, temperature, max_tokens)
        except Exception as e:
            logger.error(f"Error in chat completion: {e}")
            raise

    def generate_recommendation(
        self,
        query: str,
        retrieved_products: List[Dict[str, Any]],
        config: Dict[str, Any],
        debug: Optional[Dict[str, Any]] = None,
        history: Optional[List[Dict[str, Any]]] = None,
        is_refinement: bool = False
    ) -> Dict[str, Any]:
        """Generate a structured recommendation response.

        If a `debug` dict is passed, it is populated with the exact prompt
        sent to the model and the raw response, so the RAG pipeline can be
        inspected step by step (useful for a proof of concept).
        """

        # Build product context
        product_context = ""
        for i, product in enumerate(retrieved_products, 1):
            product_context += f"\nProduct {i}:\n"
            product_context += f"  product_id: {product.get('product_id', 'N/A')}\n"
            product_context += f"  Name: {product.get('name', 'N/A')}\n"
            product_context += f"  Description: {product.get('description', 'N/A')}\n"
            product_context += f"  Price: ${product.get('price', 'N/A')}\n"
            product_context += f"  Category: {product.get('category', 'N/A')}\n"
            product_context += f"  Brand: {product.get('brand', 'N/A')}\n"
            if product.get('attributes'):
                product_context += f"  Attributes: {product['attributes']}\n"

        num_recommendations = config.get('num_recommendations', 3)

        # Build system prompt
        system_prompt = f"""You are a product recommendation assistant. Your task is to help users find the best products based on their needs.

IMPORTANT RULES:
1. Only recommend products from the provided list below, using their exact product_id
2. Do not hallucinate or invent products or product_ids
3. Provide honest, helpful recommendations
4. Match the user's INTENT, not just their literal words. If the exact combination they asked for is not available as a single standalone product, recommend the closest products from the list that satisfy the underlying need, and in "answer" briefly and honestly explain the gap. A requested feature often appears only on a RELATED product type or bundled with another item (for example, a feature the user wants on product type A may only exist on a combined "A + B" product). Surface those and name the difference clearly — do NOT reply as if nothing was found when relevant close matches exist.
5. Only return an empty "recommendations" array when the provided list is genuinely irrelevant to the request; then explain why in "answer".
6. Be concise and direct, and honest about partial matches — say what fits and what does not.
7. Recommend at most {num_recommendations} products, ordered best match first.
8. Set "follow_up_question" when the closest matches differ from what was asked in a way the user should decide on (a different product type, a trade-off, or a choice between options) — ask ONE short question that helps them choose. Otherwise set it to "".
9. Earlier turns of the conversation may appear before this message. Use them to resolve references like "it", "that one", "cheaper", or "with LED" so follow-ups make sense in context. Recommendations must STILL come only from the Available products list below, which reflects the current request.

You must respond with a JSON object matching exactly this schema:
{{
  "answer": string,               // your explanation to the user
  "recommendations": [
    {{
      "product_id": string,       // must exactly match a product_id from the list below
      "reason": string,           // why this product fits the user's request
      "score": number             // confidence 0.0-1.0
    }}
  ],
  "follow_up_question": string    // a clarifying question to help narrow results further, or "" if not needed
}}

Available products:
{product_context}
"""

        if is_refinement:
            system_prompt += (
                "\n\nREFINEMENT MODE: The user's latest message is a refinement of the "
                "PREVIOUS results — they tapped a filter chip such as \"With LED\", "
                "\"Under €90\", or \"Only show Mailboxes\". Stay within the SAME product "
                "domain/topic as the conversation so far and apply this added constraint. "
                "NEVER start a fresh, unrelated search: if the topic is mailboxes, do not "
                "jump to standalone lamps just because \"LED\" was tapped. Following rule 4, "
                "if the exact item lacks the constraint, still recommend the closest RELATED "
                "products in that same domain (e.g. a combined mailbox+package box with LED) "
                "and explain the difference — do not return an empty result."
            )

        user_message = f"User query: {query}"

        # System rules + product context, then the recent conversation turns
        # (bounded), then the current question. History gives the model context
        # to resolve references; the product list it may recommend from is the
        # current retrieval, carried in the system prompt.
        messages = [ChatMessage(role="system", content=system_prompt)]
        for turn in (history or [])[-6:]:
            role = turn.get("role")
            content = (turn.get("content") or "").strip()
            if role in ("user", "assistant") and content:
                messages.append(ChatMessage(role=role, content=content[:1500]))
        messages.append(ChatMessage(role="user", content=user_message))

        if debug is not None:
            debug["model"] = self.model
            debug["temperature"] = self.temperature
            debug["max_tokens"] = self.max_tokens
            debug["system_prompt"] = system_prompt
            debug["user_message"] = user_message

        try:
            data = self._chat_request(
                messages,
                response_format={"type": "json_object"},
            )

            raw_content = data["choices"][0]["message"]["content"]
            if debug is not None:
                debug["raw_response"] = raw_content
                usage = data.get("usage")
                if usage is not None:
                    debug["token_usage"] = {
                        "prompt_tokens": usage.get("prompt_tokens"),
                        "completion_tokens": usage.get("completion_tokens"),
                        "total_tokens": usage.get("total_tokens"),
                    }

            result = json.loads(raw_content)

            # Ensure we only return products from the retrieved list
            if "recommendations" in result:
                valid_ids = {p.get("product_id") for p in retrieved_products}
                dropped = [
                    r.get("product_id") for r in result["recommendations"]
                    if r.get("product_id") not in valid_ids
                ]
                result["recommendations"] = [
                    r for r in result["recommendations"]
                    if r.get("product_id") in valid_ids
                ]
                if debug is not None and dropped:
                    debug["dropped_hallucinated_ids"] = dropped

            return result

        except Exception as e:
            logger.error(f"Error generating recommendation: {e}")
            if debug is not None:
                debug["error"] = str(e)
            # Fallback to simple response
            return {
                "answer": "I apologize, but I encountered an error generating recommendations. Please try again.",
                "recommendations": [],
                "follow_up_question": ""
            }
