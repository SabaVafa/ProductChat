from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.sql import func
from app.database import Base


class Interaction(Base):
    """One chat exchange, logged for review and quality improvement.

    Captures what the user asked, the (context-enriched) query actually searched,
    which products were retrieved, what the assistant answered/recommended, and
    the user's thumbs feedback — the raw material for the eval/feedback loop.
    """
    __tablename__ = "interactions"

    id = Column(Integer, primary_key=True, index=True)
    message = Column(Text, nullable=False)            # the user's message
    retrieval_query = Column(Text, nullable=True)     # context-enriched search query
    retrieved = Column(JSON, nullable=True)           # [{product_id, name, score}]
    answer = Column(Text, nullable=True)              # assistant answer text
    recommended_ids = Column(JSON, nullable=True)     # product ids shown as cards
    follow_up = Column(Text, nullable=True)
    feedback = Column(Integer, nullable=True)         # 1 = up, -1 = down, null = none
    feedback_comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
