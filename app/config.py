"""Application configuration via pydantic-settings.

All values can be set via environment variables or a .env file.
See .env.example for the full list.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- API security ---
    api_key: str = "changeme"

    # --- OpenStack connection ---
    os_auth_url: str = "http://localhost:5000/v3"
    os_username: str = "admin"
    os_password: str = "secret"
    os_project_name: str = "admin"
    os_user_domain_name: str = "Default"
    os_project_domain_name: str = "Default"
    os_region_name: str = "RegionOne"

    # --- App settings ---
    app_title: str = "OpenStack VM Manager"
    app_version: str = "0.1.0"
    debug: bool = False


# Module-level singleton — import this everywhere
settings = Settings()
