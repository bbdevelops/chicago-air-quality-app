"""
scripts/_socrata.py — Shared Socrata API client setup and token loading.

Provides the common infrastructure used by both Socrata extractors:
  - Token validation (catches placeholder values from .env.example)
  - Client creation with optional HTTP Basic Auth
  - Config loading for the [socrata] section
"""

from __future__ import annotations

import logging
import os

from _common import PROJECT_ROOT, get_config_section
from dotenv import load_dotenv
from sodapy import Socrata

log = logging.getLogger(__name__)


def load_socrata_config() -> dict[str, str | int]:
    """Read the [socrata] section from config.ini and return a plain dict."""
    cfg = get_config_section("socrata")
    return {
        "domain": cfg["domain"],
        "complaints_dataset_id": cfg["complaints_dataset_id"],
        "openair_dataset_id": cfg["openair_dataset_id"],
        "batch_size": int(cfg["batch_size"]),
        "cache_max_age_hours": int(cfg["cache_max_age_hours"]),
        "start_date": cfg["start_date"],
        "app_token_env_var": cfg["app_token_env_var"],
        "app_secret_env_var": cfg["app_secret_env_var"],
    }


def load_token(
    token_env_var: str,
    secret_env_var: str,
) -> tuple[str | None, str | None]:
    """Load and validate a Socrata API token from .env.

    Returns (app_token, app_secret).  Both are None if the token is missing
    or is a placeholder value from .env.example.
    """
    load_dotenv(PROJECT_ROOT / ".env")
    app_token = os.getenv(token_env_var)
    app_secret = os.getenv(secret_env_var)

    if not app_token or app_token.startswith(("PASTE", "YOUR")):
        log.warning(
            "No valid %s found in .env — API requests will be throttled to "
            "1 000/hr.  Register a free token at:\n"
            "  https://data.cityofchicago.org/profile/edit/developer",
            token_env_var,
        )
        return None, None

    return app_token, app_secret


def make_client(
    domain: str,
    app_token: str | None,
    app_secret: str | None,
    timeout: int = 60,
) -> Socrata:
    """Create a Socrata client with optional HTTP Basic Auth.

    Per the Socrata docs:
      - app_token  → sent as X-App-Token header (Key ID / public)
      - app_secret → used with app_token for HTTP Basic Auth (Key Secret)
    """
    if app_token and app_secret:
        return Socrata(
            domain, app_token,
            username=app_token, password=app_secret,
            timeout=timeout,
        )
    return Socrata(domain, app_token, timeout=timeout)
