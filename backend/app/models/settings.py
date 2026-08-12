from sqlalchemy import Column, Integer, String, Text, Boolean, Float, DateTime, JSON
from sqlalchemy.sql import func
from app.database import Base
import json


class Settings(Base):
    __tablename__ = "settings"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(255), unique=True, index=True, nullable=False)
    value = Column(Text, nullable=True)
    category = Column(String(100), nullable=False)
    is_encrypted = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def set_value(self, value):
        if isinstance(value, (dict, list)):
            self.value = json.dumps(value)
        else:
            self.value = str(value)
    
    def get_value(self):
        if not self.value:
            return None
        try:
            return json.loads(self.value)
        except (json.JSONDecodeError, TypeError):
            return self.value
