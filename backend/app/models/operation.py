from sqlalchemy import Column, Integer, String, DateTime, JSON
from sqlalchemy.sql import func
from app.database import Base


class Operation(Base):
    """One row per pipeline operation (sync, index, import, enrich, dedupe, qa).

    The operations journal answers "is the pipeline healthy?" at a glance —
    every run leaves a permanent, timestamped record with its outcome, so
    failures in scheduled/background work are visible instead of silent.
    """
    __tablename__ = "operations"

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String(40), nullable=False, index=True)   # sync|index|import|enrich|dedupe|qa|...
    status = Column(String(20), nullable=False)             # completed | error
    detail = Column(JSON, nullable=True)                    # counts / summary / error message
    created_at = Column(DateTime(timezone=True), server_default=func.now())
