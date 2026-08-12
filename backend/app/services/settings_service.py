from sqlalchemy.orm import Session
from app.models.settings import Settings as SettingsModel
from cryptography.fernet import Fernet
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class SettingsService:
    def __init__(self, db: Session):
        self.db = db
        self.encryption_key = self._get_or_create_encryption_key()
        self.cipher = Fernet(self.encryption_key)
    
    def _get_or_create_encryption_key(self) -> bytes:
        """Get the encryption key from settings.

        This key must be stable across requests/processes: encrypted values
        (like the Mistral API key) are persisted in the database, and a
        different key on the next request would make them undecryptable.
        """
        from cryptography.fernet import Fernet
        from app.config import settings
        key = settings.ENCRYPTION_KEY

        try:
            Fernet(key.encode())
            return key.encode()
        except Exception:
            raise ValueError(
                "ENCRYPTION_KEY is not a valid Fernet key. Generate one with "
                "`python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\"` and set it as the "
                "ENCRYPTION_KEY environment variable."
            )
    
    def _encrypt(self, value: str) -> str:
        """Encrypt a value."""
        try:
            encrypted = self.cipher.encrypt(value.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error(f"Encryption error: {e}")
            return value
    
    def _decrypt(self, value: str) -> str:
        """Decrypt a value."""
        try:
            decrypted = self.cipher.decrypt(value.encode())
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Decryption error: {e}")
            return value
    
    def get_setting(self, key: str, category: str) -> Optional[Any]:
        """Get a single setting."""
        setting = self.db.query(SettingsModel).filter(
            SettingsModel.key == key,
            SettingsModel.category == category
        ).first()
        
        if not setting:
            return None
        
        value = setting.get_value()
        if setting.is_encrypted:
            value = self._decrypt(value)
        
        return value
    
    def set_setting(self, key: str, value: Any, category: str, encrypt: bool = False) -> bool:
        """Set a single setting."""
        try:
            setting = self.db.query(SettingsModel).filter(
                SettingsModel.key == key,
                SettingsModel.category == category
            ).first()
            
            if encrypt:
                value_str = self._encrypt(str(value))
            else:
                value_str = str(value)
            
            if setting:
                setting.value = value_str
                setting.is_encrypted = encrypt
            else:
                setting = SettingsModel(
                    key=key,
                    value=value_str,
                    category=category,
                    is_encrypted=encrypt
                )
                self.db.add(setting)
            
            self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error setting value: {e}")
            self.db.rollback()
            return False
    
    def get_category_settings(self, category: str) -> Dict[str, Any]:
        """Get all settings for a category."""
        settings_dict = {}
        settings_records = self.db.query(SettingsModel).filter(
            SettingsModel.category == category
        ).all()
        
        for setting in settings_records:
            value = setting.get_value()
            if setting.is_encrypted:
                value = self._decrypt(value)
            settings_dict[setting.key] = value
        
        return settings_dict
    
    def set_category_settings(self, category: str, settings_dict: Dict[str, Any], encryption_keys: Optional[list] = None) -> bool:
        """Set multiple settings for a category."""
        try:
            encryption_keys = encryption_keys or []

            for key, value in settings_dict.items():
                encrypt = key in encryption_keys
                self.set_setting(key, value, category, encrypt)

            return True
        except Exception as e:
            logger.error(f"Error setting category settings: {e}")
            self.db.rollback()
            return False

    def set_default_category_settings(self, category: str, settings_dict: Dict[str, Any], encryption_keys: Optional[list] = None) -> bool:
        """Set default values for a category, but only for keys that don't already have a stored value.

        Unlike set_category_settings, this never overwrites an existing value. It's used to seed
        first-run defaults (e.g. on every GET /settings or /chat call) without clobbering values the
        user has since configured, like an API key.
        """
        try:
            encryption_keys = encryption_keys or []
            existing_keys = {
                row.key for row in self.db.query(SettingsModel).filter(
                    SettingsModel.category == category
                ).all()
            }

            for key, value in settings_dict.items():
                if key in existing_keys:
                    continue
                encrypt = key in encryption_keys
                self.set_setting(key, value, category, encrypt)

            return True
        except Exception as e:
            logger.error(f"Error setting default category settings: {e}")
            self.db.rollback()
            return False
    
    def get_all_settings(self) -> Dict[str, Any]:
        """Get all settings organized by category."""
        all_settings = {}
        categories = ["mistral", "qdrant", "retrieval", "output", "product_data"]
        
        for category in categories:
            all_settings[category] = self.get_category_settings(category)
        
        return all_settings
    
    def initialize_default_settings(self) -> bool:
        """Initialize default settings if they don't exist."""
        try:
            from app.config import settings as app_settings
            # Mistral settings. Seed the API key from the MISTRAL_API_KEY env
            # var (via .env) on first run so the app is usable without opening
            # the Settings UI. A placeholder default is treated as "unset".
            env_key = app_settings.MISTRAL_API_KEY or ""
            if env_key.lower() in ("your-mistral-api-key-here", "your_api_key_here"):
                env_key = ""
            mistral_defaults = {
                "api_key": env_key,
                "model": app_settings.MISTRAL_MODEL or "mistral-large-latest",
                "temperature": 0.7,
                "max_tokens": 1000
            }
            self.set_default_category_settings("mistral", mistral_defaults, ["api_key"])
            
            # Qdrant settings
            qdrant_defaults = {
                "url": "http://localhost:6333",
                "collection_name": "products",
                "embedding_model": "mistral-embed"
            }
            self.set_default_category_settings("qdrant", qdrant_defaults)
            
            # Retrieval settings
            retrieval_defaults = {
                "num_retrieved": 10,
                "similarity_threshold": 0.0,
                "enable_hybrid_search": False,
                "enable_metadata_filters": False
            }
            self.set_default_category_settings("retrieval", retrieval_defaults)
            
            # Output settings
            output_defaults = {
                "include_explanation": True,
                "include_confidence": False,
                "num_recommendations": 3,
                "include_comparison": False,
                "include_follow_up": False
            }
            self.set_default_category_settings("output", output_defaults)
            
            # Product data settings
            product_defaults = {
                "database_connection": "",
                "import_format": "json",
                "field_mapping": "{}"
            }
            self.set_default_category_settings("product_data", product_defaults)
            
            return True
        except Exception as e:
            logger.error(f"Error initializing default settings: {e}")
            return False
