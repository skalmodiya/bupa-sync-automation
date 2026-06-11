"""Settings management for BUPA Sync backend.

Settings are persisted to SQLite database. Legacy settings.json is migrated
on first load. In production mode, env vars serve as a fallback.
"""

import json
import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

DATA_DIR = Path(__file__).parent / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"


class LLMConfig(BaseModel):
    provider: str = "local_proxy"  # "local_proxy" or "sap_ai_core"
    base_url: str = "http://localhost:6655/litellm/v1"
    model: str = "anthropic--claude-4.6-sonnet"
    api_key: str = ""


class N8nConfig(BaseModel):
    url: str = "http://localhost:5678"
    api_key: str = ""
    workflow_id: str = ""  # Main sync workflow ID
    retry_workflow_id: str = ""  # Retry sync workflow ID
    agent_fix_workflow_id: str = ""  # Agent fix workflow ID
    monitored_workflow_ids: list[str] = []  # All workflow IDs to show in Workflows page
    webhook_url: str = ""  # Override webhook base URL (e.g. ngrok tunnel URL)


class MockS4Config(BaseModel):
    url: str = "http://localhost:8090"


class SmtpConfig(BaseModel):
    host: str = "localhost"
    port: int = 1025
    username: str = ""
    password: str = ""


class AgentConfig(BaseModel):
    url: str = "http://localhost:5000"


class AuthConfig(BaseModel):
    ias_url: str = ""  # e.g. https://mytenant.accounts.ondemand.com
    client_id: str = ""
    client_secret: str = ""


class NgrokConfig(BaseModel):
    enabled: bool = False  # Whether ngrok tunnel is active
    authtoken: str = ""  # ngrok authentication token
    domain: str = ""  # ngrok static domain (e.g. my-app.ngrok-free.app)


class QdrantConfig(BaseModel):
    url: str = "http://localhost:6333"  # Qdrant vector DB endpoint


class Settings(BaseModel):
    deployment_mode: str = "local"  # "local", "docker", "production"
    llm: LLMConfig = LLMConfig()
    n8n: N8nConfig = N8nConfig()
    mock_s4: MockS4Config = MockS4Config()
    smtp: SmtpConfig = SmtpConfig()
    agent: AgentConfig = AgentConfig()
    auth: AuthConfig = AuthConfig()
    ngrok: NgrokConfig = NgrokConfig()
    qdrant: QdrantConfig = QdrantConfig()


def _sync_settings_file(settings: Settings) -> None:
    """Write settings to settings.json so the agent container can read them."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
    except Exception:
        pass  # Non-critical


def load_settings() -> Settings:
    """Load settings from SQLite database. Falls back to settings.json migration.

    In production mode, falls back to environment variables if no settings exist.
    """
    from database import get_setting

    raw = get_setting("app_settings", "")
    if raw:
        try:
            settings = Settings(**json.loads(raw))
            # Sync to settings.json for agent container to read
            _sync_settings_file(settings)
            return settings
        except Exception:
            pass

    # Check if old settings.json exists (migration)
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            settings = Settings(**data)
            save_settings(settings)  # migrate to SQLite
            return settings
        except Exception:
            pass

    # If production mode env var is set, try to build settings from env
    if os.environ.get("DEPLOYMENT_MODE") == "production":
        settings = Settings(
            deployment_mode="production",
            llm=LLMConfig(
                provider=os.environ.get("LLM_PROVIDER", "sap_ai_core"),
                base_url=os.environ.get(
                    "LLM_BASE_URL", "http://localhost:6655/litellm/v1"
                ),
                model=os.environ.get("LLM_MODEL", "anthropic--claude-4.6-sonnet"),
                api_key=os.environ.get("LLM_API_KEY", ""),
            ),
            n8n=N8nConfig(
                url=os.environ.get("N8N_URL", "http://localhost:5678"),
                api_key=os.environ.get("N8N_API_KEY", ""),
            ),
            mock_s4=MockS4Config(
                url=os.environ.get("MOCK_S4_URL", "http://localhost:8090"),
            ),
            smtp=SmtpConfig(
                host=os.environ.get("SMTP_HOST", "localhost"),
                port=int(os.environ.get("SMTP_PORT", "1025")),
                username=os.environ.get("SMTP_USERNAME", ""),
                password=os.environ.get("SMTP_PASSWORD", ""),
            ),
            agent=AgentConfig(
                url=os.environ.get("AGENT_URL", "http://localhost:5000"),
            ),
        )
        save_settings(settings)
        return settings

    return Settings()


def save_settings(settings: Settings, user: str = "system") -> None:
    """Persist settings to database and sync to shared settings.json for agent."""
    from database import set_setting

    set_setting("app_settings", settings.model_dump_json(), user=user)
    _sync_settings_file(settings)


def get_settings() -> Settings:
    """FastAPI dependency that returns current settings."""
    return load_settings()


def mask_api_key(key: str) -> str:
    """Mask an API key, showing only the last 4 characters."""
    if not key or len(key) <= 4:
        return "****" if key else ""
    return "*" * (len(key) - 4) + key[-4:]


def mask_settings(settings: Settings) -> dict:
    """Return settings dict with API keys masked for safe frontend consumption."""
    data = settings.model_dump()
    if data["llm"]["api_key"]:
        data["llm"]["api_key"] = mask_api_key(data["llm"]["api_key"])
    if data["n8n"]["api_key"]:
        data["n8n"]["api_key"] = mask_api_key(data["n8n"]["api_key"])
    if data["smtp"]["password"]:
        data["smtp"]["password"] = mask_api_key(data["smtp"]["password"])
    if data["auth"]["client_secret"]:
        data["auth"]["client_secret"] = mask_api_key(data["auth"]["client_secret"])
    if data["ngrok"]["authtoken"]:
        data["ngrok"]["authtoken"] = mask_api_key(data["ngrok"]["authtoken"])
    return data
