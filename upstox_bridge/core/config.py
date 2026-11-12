"""Cross-platform configuration loader for Upstox Trading Bridge."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List
import yaml
from dotenv import load_dotenv

# Detect Project Root (two levels above upstox_bridge/core)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings:
    """Manages application settings loaded from .env, config.yaml, and watchlist.yaml."""

    def __init__(self, root_dir: Path | None = None):
        self.root_dir = root_dir or PROJECT_ROOT
        self.config_dir = self.root_dir / "config"
        self.data_dir = self.root_dir / "data"
        self.templates_dir = self.root_dir / "templates"
        self.token_cache_path = self.root_dir / ".token_cache.json"

        # Ensure essential directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.templates_dir.mkdir(parents=True, exist_ok=True)

        # Load environment variables
        env_path = self.root_dir / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        else:
            load_dotenv()

        # Load YAML config
        self.config = self._load_yaml(self.config_dir / "config.yaml")
        self.watchlist = self._load_yaml(self.config_dir / "watchlist.yaml")

    def _load_yaml(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return data if isinstance(data, dict) else {}
        except Exception as e:
            print(f"[Warning] Failed to load {path}: {e}")
            return {}

    # Upstox settings
    @property
    def upstox_api_key(self) -> str:
        return os.getenv("UPSTOX_API_KEY", "").strip()

    @property
    def upstox_api_secret(self) -> str:
        return os.getenv("UPSTOX_API_SECRET", "").strip()

    @property
    def upstox_redirect_uri(self) -> str:
        return os.getenv("UPSTOX_REDIRECT_URI", "http://127.0.0.1:5000/callback").strip()

    @property
    def upstox_access_token(self) -> str:
        return os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()

    @property
    def upstox_mobile_no(self) -> str:
        return os.getenv("UPSTOX_MOBILE_NO", "").strip()

    @property
    def upstox_pin(self) -> str:
        return os.getenv("UPSTOX_PIN", "").strip()

    @property
    def upstox_totp_key(self) -> str:
        return os.getenv("UPSTOX_TOTP_KEY", "").strip()

    @property
    def upstox_mode(self) -> str:
        return self.config.get("upstox", {}).get("mode", "full")

    @property
    def instrument_cache_hours(self) -> int:
        return int(self.config.get("upstox", {}).get("instrument_cache_hours", 24))

    # Google Sheets settings
    @property
    def gsheet_webhook_url(self) -> str:
        return os.getenv("GOOGLE_SHEET_WEBHOOK_URL", "").strip()

    @property
    def gsheet_enabled(self) -> bool:
        return bool(self.config.get("google_sheets", {}).get("enabled", True))

    @property
    def gsheet_refresh_sec(self) -> float:
        return float(self.config.get("google_sheets", {}).get("refresh_interval_sec", 3.0))

    @property
    def gsheet_sheet_name(self) -> str:
        return str(self.config.get("google_sheets", {}).get("sheet_name", "LiveMarket"))

    # Excel settings
    @property
    def excel_enabled(self) -> bool:
        return bool(self.config.get("excel", {}).get("enabled", True))

    @property
    def excel_mode(self) -> str:
        return str(self.config.get("excel", {}).get("mode", "auto"))

    @property
    def excel_file_path(self) -> Path:
        raw_path = self.config.get("excel", {}).get("file_path", "data/Upstox_Live_Market.xlsx")
        p = Path(raw_path)
        if not p.is_absolute():
            p = self.root_dir / p
        return p

    @property
    def excel_sheet_name(self) -> str:
        return str(self.config.get("excel", {}).get("sheet_name", "LiveMarket"))

    @property
    def excel_refresh_sec(self) -> float:
        return float(self.config.get("excel", {}).get("refresh_interval_sec", 0.5))

    @property
    def sync_watchlist_from_excel(self) -> bool:
        return bool(self.config.get("excel", {}).get("sync_watchlist_from_excel", True))

    # Local Feed Server settings
    @property
    def local_server_enabled(self) -> bool:
        return bool(self.config.get("local_feed_server", {}).get("enabled", True))

    @property
    def local_server_host(self) -> str:
        return str(self.config.get("local_feed_server", {}).get("host", "127.0.0.1"))

    @property
    def local_server_port(self) -> int:
        return int(self.config.get("local_feed_server", {}).get("port", 8080))

    # Watchlist symbols
    @property
    def watchlist_txt_path(self) -> Path:
        return self.root_dir / "watchlist.txt"

    def read_watchlist_txt(self) -> List[str]:
        """Read symbols from watchlist.txt (one symbol per line, # for comments)."""
        if not self.watchlist_txt_path.exists():
            return []
        try:
            with open(self.watchlist_txt_path, "r", encoding="utf-8") as f:
                symbols = []
                for line in f:
                    clean = line.strip()
                    if clean and not clean.startswith("#"):
                        symbols.append(clean)
                return symbols
        except Exception:
            return []

    @property
    def watchlist_symbols(self) -> List[str]:
        """
        Get active symbols to stream.
        Priority:
        1. watchlist.txt (in project root - plain text, one per line)
        2. config/watchlist.yaml
        """
        from_txt = self.read_watchlist_txt()
        if from_txt:
            return from_txt

        syms = self.watchlist.get("symbols", [])
        return [str(s).strip() for s in syms if str(s).strip()]


# Global default settings instance
settings = Settings()
