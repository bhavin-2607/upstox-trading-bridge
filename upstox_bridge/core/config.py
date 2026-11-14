"""Cross-platform configuration loader for Upstox Trading Bridge."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List
import yaml
from dotenv import load_dotenv

# Detect Project Root (Application directory when frozen by PyInstaller, or source root)
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
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
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.templates_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

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
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    return data if isinstance(data, dict) else {}
            except Exception:
                pass

        # Check PyInstaller bundled location if running as compiled binary
        if getattr(sys, "frozen", False):
            bundled = Path(getattr(sys, "_MEIPASS", self.root_dir)) / "config" / path.name
            if bundled.exists():
                try:
                    with open(bundled, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                        return data if isinstance(data, dict) else {}
                except Exception:
                    pass

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
        raw_path = self.config.get("excel", {}).get("file_path", "")
        if raw_path:
            p = Path(raw_path)
            if not p.is_absolute():
                p = self.root_dir / p
            if p.exists():
                return p

        # Check for bst.xlsx or trial.xlsx in project root
        for candidate in ("bst.xlsx", "BST.xlsx", "trial.xlsx", "Trial.xlsx"):
            p = self.root_dir / candidate
            if p.exists():
                return p

        fallback = self.root_dir / "data" / "Upstox_Live_Market.xlsx"
        if fallback.exists():
            return fallback
        return self.root_dir / "bst.xlsx"

    @property
    def excel_sheet_name(self) -> str:
        configured = self.config.get("excel", {}).get("sheet_name", "BST")
        file_path = self.excel_file_path
        if file_path.name.lower() in ("trial.xlsx", "bst.xlsx"):
            return "BST"
        if file_path.name.lower() == "upstox_live_market.xlsx":
            return "LiveMarket"
        return str(configured)

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


def update_env_variable(key: str, value: str, env_path: Optional[Path] = None) -> None:
    """Update or append an environment variable in the .env file cleanly."""
    target_path = env_path or (settings.root_dir / ".env")
    env_lines = []
    found = False

    if target_path.exists():
        with open(target_path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith(f"{key}=") or stripped.startswith(f"export {key}="):
                    env_lines.append(f'{key}="{value}"\n')
                    found = True
                else:
                    env_lines.append(line)

    if not found:
        if env_lines and not env_lines[-1].endswith("\n"):
            env_lines.append("\n")
        env_lines.append(f'{key}="{value}"\n')

    with open(target_path, "w", encoding="utf-8") as f:
        f.writelines(env_lines)
