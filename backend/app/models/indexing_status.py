from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func
from app.database import Base


class IndexingStatus(Base):
    __tablename__ = "indexing_status"
    
    id = Column(Integer, primary_key=True, index=True)
    status = Column(String(50), default="idle")  # idle, running, completed, error
    processed = Column(Integer, default=0)
    total = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
