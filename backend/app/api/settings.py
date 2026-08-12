from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any
from app.database import get_db
from app.schemas.settings import SettingsResponse, SettingsUpdate, CategorySettings
from app.services.settings_service import SettingsService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
async def get_settings(db: Session = Depends(get_db)):
    """
    Get all application settings.
    """
    try:
        settings_service = SettingsService(db)
        settings_service.initialize_default_settings()
        all_settings = settings_service.get_all_settings()
        return SettingsResponse(**all_settings)
    except Exception as e:
        logger.error(f"Settings retrieval error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=Dict[str, str])
async def update_settings(
    request: SettingsUpdate,
    db: Session = Depends(get_db)
):
    """
    Update application settings.
    
    Only include the categories you want to update.
    API keys will be encrypted automatically.
    """
    try:
        settings_service = SettingsService(db)
        
        # Update each category if provided
        if request.mistral:
            settings_service.set_category_settings(
                "mistral", 
                request.mistral, 
                ["api_key"]
            )
        
        if request.qdrant:
            settings_service.set_category_settings("qdrant", request.qdrant)
        
        if request.retrieval:
            settings_service.set_category_settings("retrieval", request.retrieval)
        
        if request.output:
            settings_service.set_category_settings("output", request.output)
        
        if request.product_data:
            settings_service.set_category_settings("product_data", request.product_data)
        
        return {"message": "Settings updated successfully"}
    except Exception as e:
        logger.error(f"Settings update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{category}", response_model=Dict[str, Any])
async def get_category_settings(category: str, db: Session = Depends(get_db)):
    """
    Get settings for a specific category.
    """
    try:
        settings_service = SettingsService(db)
        settings_dict = settings_service.get_category_settings(category)
        return settings_dict
    except Exception as e:
        logger.error(f"Category settings retrieval error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{category}", response_model=Dict[str, str])
async def update_category_settings(
    category: str,
    request: CategorySettings,
    db: Session = Depends(get_db)
):
    """
    Update settings for a specific category.
    """
    try:
        settings_service = SettingsService(db)
        
        # Determine which keys to encrypt
        encryption_keys = []
        if category == "mistral":
            encryption_keys = ["api_key"]
        
        settings_service.set_category_settings(
            category, 
            request.settings, 
            encryption_keys
        )
        
        return {"message": f"{category} settings updated successfully"}
    except Exception as e:
        logger.error(f"Category settings update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
