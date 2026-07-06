"""
Ocean Engine OAuth2 Authentication Module

Token lifecycle: auth_code → access_token → refresh_token
Priority chain: cached_file → env_token → auth_code → refresh_token
"""

import json
import logging
import os
import time
from pathlib import Path

import requests

from config.settings import (
    OCEAN_ENGINE_APP_ID,
    OCEAN_ENGINE_SECRET,
    OCEAN_ENGINE_AUTH_URL,
    TOKEN_REFRESH_BUFFER,
    DATA_DIR,
)

logger = logging.getLogger(__name__)

TOKEN_CACHE_FILE = Path(DATA_DIR) / ".token_cache.json"


class AuthManager:
    """Manages Ocean Engine OAuth2 tokens with auto-refresh and caching."""

    def __init__(self):
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at: float = 0.0
        self._advertiser_ids: list[str] = []
        self._load_cached_token()

    # ── Public API ─────────────────────────────────────────────

    def get_token(self) -> str:
        """Return a valid access token, obtaining/refreshing as needed."""
        if self._should_refresh():
            logger.info("Token nearing expiry, refreshing...")
            self._refresh_access_token()
        if not self._access_token:
            self._obtain_new_token()
        if not self._access_token:
            raise RuntimeError(
                "No valid access token. Run 'python main.py auth --code <code>' to authorize."
            )
        return self._access_token

    @property
    def advertiser_ids(self) -> list[str]:
        """Authorized advertiser IDs (from OAuth response)."""
        if not self._advertiser_ids:
            self._fetch_advertiser_ids()
        return self._advertiser_ids

    # ── Internal ───────────────────────────────────────────────

    def _should_refresh(self) -> bool:
        if not self._access_token:
            return False
        # expires_at = 0 means unknown/corrupt — treat as expired and force refresh
        if self._expires_at <= 0:
            return True
        return (self._expires_at - time.time()) < TOKEN_REFRESH_BUFFER

    def _load_cached_token(self):
        if not TOKEN_CACHE_FILE.exists():
            return
        try:
            data = json.loads(TOKEN_CACHE_FILE.read_text())
            self._access_token = data.get("access_token")
            self._refresh_token = data.get("refresh_token")
            self._expires_at = data.get("expires_at", 0)
            self._advertiser_ids = data.get("advertiser_ids", [])
            remaining = self._expires_at - time.time()
            if remaining > 0:
                logger.info("Loaded cached token (expires in %.0fh)", remaining / 3600)
        except Exception:
            logger.warning("Failed to load token cache")

    def _save_token_cache(self):
        TOKEN_CACHE_FILE.write_text(json.dumps({
            "access_token": self._access_token,
            "refresh_token": self._refresh_token,
            "expires_at": self._expires_at,
            "advertiser_ids": self._advertiser_ids,
        }, indent=2))

    def _obtain_new_token(self):
        """Try all available auth methods in priority order."""
        # 1. Pre-configured token from environment
        access_token = os.getenv("OCEAN_ENGINE_ACCESS_TOKEN", "")
        if access_token:
            logger.info("Using pre-configured access token from env")
            self._access_token = access_token
            self._expires_at = time.time() + 86400
            self._save_token_cache()
            return

        # 2. Auth code exchange
        auth_code = os.getenv("OCEAN_ENGINE_AUTH_CODE", "")
        if auth_code and OCEAN_ENGINE_APP_ID and OCEAN_ENGINE_SECRET:
            self._exchange_auth_code()
            return

        # 3. Refresh existing token
        if self._refresh_token:
            try:
                self._refresh_access_token()
                return
            except Exception:
                pass

        raise RuntimeError(
            "No valid auth method. Options:\n"
            "  1. Set OCEAN_ENGINE_ACCESS_TOKEN in .env\n"
            "  2. Set OCEAN_ENGINE_AUTH_CODE in .env\n"
            "  3. Run: python main.py auth\n"
        )

    def _refresh_access_token(self):
        """Refresh using refresh_token with retry. Falls back to app_access_token."""
        app_id = int(OCEAN_ENGINE_APP_ID) if OCEAN_ENGINE_APP_ID else 0
        max_retries = 3

        for attempt in range(max_retries):
            try:
                if self._refresh_token:
                    resp = requests.post(
                        f"{OCEAN_ENGINE_AUTH_URL}/refresh_token/",
                        json={
                            "app_id": app_id,
                            "secret": OCEAN_ENGINE_SECRET,
                            "grant_type": "refresh_token",
                            "refresh_token": self._refresh_token,
                        },
                        timeout=30,
                    )
                else:
                    resp = requests.post(
                        f"{OCEAN_ENGINE_AUTH_URL}/access_token/",
                        json={
                            "app_id": app_id,
                            "secret": OCEAN_ENGINE_SECRET,
                            "grant_type": "app_access_token",
                        },
                        timeout=30,
                    )

                data = resp.json()
                if data.get("code") != 0:
                    msg = data.get("message", str(data))
                    if "refresh_token" in str(msg).lower():
                        raise RuntimeError(f"Token refresh failed (permanent): {msg}")
                    if attempt < max_retries - 1:
                        wait = 2 ** attempt
                        logger.warning("Token refresh attempt %d failed: %s, retry in %ds", attempt + 1, msg, wait)
                        time.sleep(wait)
                        continue
                    raise RuntimeError(f"Token refresh failed: {msg}")

                result = data["data"]
                self._access_token = result["access_token"]
                self._refresh_token = result.get("refresh_token", self._refresh_token)
                self._expires_at = time.time() + result.get("expires_in", 86400)
                self._advertiser_ids = result.get("advertiser_ids", self._advertiser_ids)
                self._save_token_cache()
                logger.info("Token refreshed (expires in %ds)", result.get("expires_in", 86400))
                return

            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    logger.warning("Token refresh network error (attempt %d): %s, retry in %ds", attempt + 1, e, wait)
                    time.sleep(wait)
                else:
                    raise RuntimeError(f"Token refresh failed after {max_retries} attempts: {e}")
            except (json.JSONDecodeError, KeyError) as e:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    logger.warning("Token refresh malformed response (attempt %d): %s", attempt + 1, e)
                    time.sleep(wait)
                else:
                    raise RuntimeError(f"Token refresh failed: malformed response")

    def _exchange_auth_code(self):
        """Exchange authorization code for access token."""
        auth_code = os.getenv("OCEAN_ENGINE_AUTH_CODE", "")
        if not auth_code:
            raise RuntimeError("OCEAN_ENGINE_AUTH_CODE is not set")

        logger.info("Exchanging auth_code for access token...")
        app_id = int(OCEAN_ENGINE_APP_ID) if OCEAN_ENGINE_APP_ID else 0
        resp = requests.post(
            f"{OCEAN_ENGINE_AUTH_URL}/access_token/",
            json={
                "app_id": app_id,
                "secret": OCEAN_ENGINE_SECRET,
                "grant_type": "auth_code",
                "auth_code": auth_code,
            },
            timeout=30,
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(
                f"Auth code exchange failed: {data.get('message', data)}. "
                "The auth_code may have expired. Run 'python main.py auth' to get a new URL."
            )

        result = data["data"]
        self._access_token = result["access_token"]
        self._refresh_token = result.get("refresh_token")
        self._expires_at = time.time() + result.get("expires_in", 86400)
        raw_ids = result.get("advertiser_ids", [])
        if raw_ids and isinstance(raw_ids[0], dict):
            self._advertiser_ids = [str(adv["advertiser_id"]) for adv in raw_ids]
        else:
            self._advertiser_ids = [str(aid) for aid in raw_ids]
        self._save_token_cache()
        logger.info(
            "Auth code exchanged. Token expires in %ds, %d advertisers authorized.",
            result.get("expires_in", 0), len(self._advertiser_ids),
        )

    @staticmethod
    def get_auth_url() -> str:
        """Generate OAuth authorization URL."""
        return (
            "https://open.oceanengine.com/audit/oauth.html?"
            f"app_id={OCEAN_ENGINE_APP_ID}"
            f"&state=local_ad_agent"
            f"&material_auth=1"
            f"&redirect_uri=https://www.example.com/callback"
        )

    def _fetch_advertiser_ids(self):
        if not self._access_token:
            self.get_token()

        resp = requests.get(
            f"{OCEAN_ENGINE_AUTH_URL}/advertiser/get/",
            headers={"Access-Token": self._access_token},
            timeout=30,
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Failed to fetch advertisers: {data.get('message')}")

        self._advertiser_ids = [
            str(adv["advertiser_id"]) for adv in data.get("data", {}).get("list", [])
        ]
        self._save_token_cache()
