"""Shared client configuration. Never expose the API key in the interface."""
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
from typing import Any
from dotenv import load_dotenv
from core.contracts import CategorySearchError

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8108
    protocol: str = "http"
    api_key: str = field(default="", repr=False)
    prefix: str = "overlap_local"

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(ROOT / ".env", override=False)
        try:
            settings = cls(os.getenv("TYPESENSE_HOST", "127.0.0.1"),
                           int(os.getenv("TYPESENSE_PORT", "8108")),
                           os.getenv("TYPESENSE_PROTOCOL", "http"),
                           os.getenv("TYPESENSE_API_KEY", ""),
                           os.getenv("TYPESENSE_COLLECTION_PREFIX", "overlap_local"))
        except ValueError as exc:
            raise CategorySearchError("TYPESENSE_PORT must be a number in .env.") from exc
        if settings.protocol not in ("http", "https"):
            raise CategorySearchError("TYPESENSE_PROTOCOL must be http or https.")
        if not 1 <= settings.port <= 65535 or not settings.host:
            raise CategorySearchError("Check the Typesense host and port in .env.")
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", settings.prefix):
            raise CategorySearchError("The collection prefix may contain letters, digits, underscores, and hyphens.")
        return settings


@dataclass
class AppServices:
    settings: Settings
    mode: str = "typesense"
    _client: Any = field(default=None, repr=False)

    @property
    def client(self):
        if not self.settings.api_key:
            raise CategorySearchError("Typesense needs an API key. Configure .env and start the local server, or explicitly select Sample preview in Developer settings.")
        if self._client is None:
            import typesense
            self._client = typesense.Client({
                "nodes": [{"host": self.settings.host, "port": self.settings.port,
                           "protocol": self.settings.protocol}],
                "api_key": self.settings.api_key,
                "connection_timeout_seconds": 3,
                "num_retries": 0,
            })
        return self._client

    def collection_name(self, category_id: str) -> str:
        if not re.fullmatch(r"[a-z_]+", category_id):
            raise CategorySearchError("Invalid category ID.")
        return f"{self.settings.prefix}_{category_id}"

    def health(self) -> bool:
        return self.client.operations.is_healthy()
