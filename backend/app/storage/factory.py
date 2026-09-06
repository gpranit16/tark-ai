import logging

from app.core.config import get_settings
from app.storage.base import StorageProvider
from app.storage.local import LocalStorageProvider
from app.storage.b2 import B2StorageProvider

logger = logging.getLogger(__name__)


def get_storage_provider(provider_name: str | None = None) -> StorageProvider:
    """Return configured or requested storage provider instance."""
    settings = get_settings()
    selected = (provider_name or settings.storage_provider or "local").lower()
    
    if selected == "b2":
        # If B2 credentials are missing, fallback to LocalStorageProvider gracefully
        if not (settings.b2_key_id and settings.b2_application_key and settings.b2_bucket_name):
            if settings.app_env != "test":
                logger.warning(
                    "STORAGE_PROVIDER is set to 'b2' but B2 credentials (B2_KEY_ID, B2_APPLICATION_KEY, B2_BUCKET_NAME) "
                    "are not configured. Falling back to LocalStorageProvider."
                )
            return LocalStorageProvider()
        return B2StorageProvider()
    
    return LocalStorageProvider()
