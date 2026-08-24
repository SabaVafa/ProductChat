from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class ProductCard(BaseModel):
    id: str
    name: str
    price: Optional[float] = None
    image: Optional[str] = None
    url: Optional[str] = None
    reason: str = ""
    score: Optional[float] = None


class ChatTurn(BaseModel):
    role: str = Field(..., description='"user" or "assistant"')
    content: str = ""


class ChatRequest(BaseModel):
    message: str = Field(..., description="User message")
    # Prior conversation turns, oldest first, so follow-ups like "and with LED?"
    # or "cheaper?" are understood in context. Optional and bounded server-side.
    history: List[ChatTurn] = Field(default_factory=list)
    # True when the user tapped a recommended refine chip (e.g. "With LED").
    # A refinement MUST keep the current subject/context — the backend widens the
    # retrieval context and instructs the model not to switch product category.
    is_refinement: bool = False
    # Launch context from the embedding page (e.g. the JTL widget on a product
    # page passes the current product's id, read from the page's JSON-LD `sku`).
    # When present, the assistant answers anchored to that product without the
    # user having to restate what they're looking at.
    product_id: Optional[str] = None
    category: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    products: List[ProductCard] = []
    follow_up_question: Optional[str] = None
    # Cheap, template-based chips to refine the current result (no LLM cost).
    refine_suggestions: List[str] = []
    # Id of the logged interaction, so the UI can attach thumbs feedback to it.
    interaction_id: Optional[int] = None
    # Full RAG trace (retrieval + prompt + raw LLM response), for inspection.
    debug: Optional[Dict[str, Any]] = None


class FeedbackRequest(BaseModel):
    interaction_id: int
    rating: str = Field(..., description='"up", "down", or "none" to clear')
    comment: Optional[str] = None
