"""CORS configuration for DCM Backend API."""

import json

from pydantic_settings import BaseSettings, SettingsConfigDict


class CORSSettings(BaseSettings):
    """Load CORS allowed origins from DCM_CORS_ALLOWED_ORIGINS."""

    model_config = SettingsConfigDict(
        env_prefix="DCM_",
        env_file=".env",
        extra="ignore",  # Databricks/Entra vars belong to Settings, not CORSSettings
    )

    cors_allowed_origins: str = "http://localhost:4000 https://dcm.alzp.tgscloud.net"

    def get_allowed_origins(self) -> list[str]:
        """Return list of allowed origins from environment variable.
        
        Tries to parse as JSON array first, falls back to space-separated string.
        """
        if not self.cors_allowed_origins:
            return []
        
        # Try JSON format first
        try:
            origins = json.loads(self.cors_allowed_origins)
            if isinstance(origins, list):
                return [str(origin).strip() for origin in origins if origin]
        except (json.JSONDecodeError, TypeError):
            pass
        
        # Fall back to space-separated format
        return [origin.strip() for origin in self.cors_allowed_origins.split() if origin.strip()]
