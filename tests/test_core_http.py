"""
Unit tests for core HTTP utilities and token masking security.
"""
import requests
from requests.adapters import HTTPAdapter
from scheme_intel.core.http import create_retry_session, mask_telegram_token, DEFAULT_RETRY_STATUSES


def test_mask_telegram_token():
    # Mask standard telegram bot token URL
    url = "https://api.telegram.org/bot123456789:ABCdefGh-IJKlmNo12345/getMe"
    masked = mask_telegram_token(url)
    assert "123456789:ABCdefGh-IJKlmNo12345" not in masked
    assert "bot***:***" in masked

    # Mask with explicit token passed
    secret_token = "987654321:XYZ987SecretKey"
    raw_error = f"HTTPConnectionPool: Max retries exceeded with url /bot{secret_token}/sendMessage"
    masked_err = mask_telegram_token(raw_error, token=secret_token)
    assert secret_token not in masked_err
    assert "***" in masked_err

    # Edge cases
    assert mask_telegram_token("") == ""
    assert mask_telegram_token(None) == ""


def test_create_retry_session():
    session = create_retry_session(retries=4, backoff_factor=0.3, headers={"X-App": "scheme-intel"})
    assert isinstance(session, requests.Session)
    assert session.headers.get("X-App") == "scheme-intel"

    # Verify adapter mounted
    http_adapter = session.adapters.get("http://")
    https_adapter = session.adapters.get("https://")
    assert isinstance(http_adapter, HTTPAdapter)
    assert isinstance(https_adapter, HTTPAdapter)
    assert http_adapter.max_retries.total == 4
    assert http_adapter.max_retries.backoff_factor == 0.3
    assert 429 in http_adapter.max_retries.status_forcelist
    assert 503 in http_adapter.max_retries.status_forcelist
