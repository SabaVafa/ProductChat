from sqlalchemy import Column, Integer, String, Text, Float, DateTime, JSON
from sqlalchemy.sql import func
from app.database import Base


class Product(Base):
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(255), nullable=True)
    attributes = Column(JSON, nullable=True)
    price = Column(Float, nullable=True)
    brand = Column(String(255), nullable=True)
    image_url = Column(String(1000), nullable=True)
    # Canonical link back to the source product page (shown on the card).
    product_url = Column(String(1000), nullable=True)
    # Scraper change-detection fields: sitemap <lastmod> and a content hash.
    source = Column(String(50), nullable=True)  # e.g. "scraper", "manual"
    lastmod = Column(String(64), nullable=True)
    content_hash = Column(String(64), nullable=True)
    indexed = Column(Integer, default=0)  # 0 = not indexed, 1 = indexed
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
