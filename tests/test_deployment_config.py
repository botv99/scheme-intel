"""
Tests for 24/7 Cloud Deployment Configurations and Gateway Runtime Telemetry.
Verifies Dockerfile, docker-compose.yml, systemd service units, and health telemetry.
"""
from pathlib import Path
import yaml
import pytest

from scheme_intel.delivery.telegram_conversation import TelegramConversationHandler
from scheme_intel.delivery.service import get_system_health, SchemeIntelService


REPO_ROOT = Path(__file__).parent.parent


def test_dockerfile_configuration():
    """Verify Dockerfile contains security, healthcheck, and unbuffered configurations."""
    dockerfile_path = REPO_ROOT / "Dockerfile"
    assert dockerfile_path.exists(), "Dockerfile must exist at repository root"

    content = dockerfile_path.read_text(encoding="utf-8")
    assert "FROM python:3.12-slim" in content
    assert "PYTHONUNBUFFERED=1" in content
    assert "useradd" in content and "schemeintel" in content, "Should configure unprivileged non-root user"
    assert "EXPOSE 8080" in content
    assert "HEALTHCHECK" in content
    assert "scheme_intel.delivery.service" in content
    assert 'CMD ["python", "-m", "scheme_intel.delivery.service", "--mode", "all"]' in content


def test_docker_compose_configuration():
    """Verify docker-compose.yml contains required volumes, restart policy, and log limits."""
    compose_path = REPO_ROOT / "docker-compose.yml"
    assert compose_path.exists(), "docker-compose.yml must exist at repository root"

    data = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    assert "services" in data
    assert "gateway" in data["services"]

    gw = data["services"]["gateway"]
    assert gw.get("restart") == "unless-stopped", "Must configure unless-stopped for 24/7 persistence"
    assert "ports" in gw and "8080:8080" in gw["ports"]
    
    # Volumes
    volumes = gw.get("volumes", [])
    assert any("data" in v for v in volumes), "Must mount data directory for SQLite persistence"

    # Logging limits
    logging_cfg = gw.get("logging", {})
    assert logging_cfg.get("driver") == "json-file"
    assert logging_cfg.get("options", {}).get("max-size") == "10m"


def test_systemd_service_definitions():
    """Verify systemd service unit files have required directives."""
    service_path = REPO_ROOT / "deploy" / "scheme-intel.service"
    native_service_path = REPO_ROOT / "deploy" / "scheme-intel-native.service"
    deploy_sh_path = REPO_ROOT / "deploy" / "oracle" / "deploy.sh"

    assert service_path.exists(), "Docker compose systemd unit must exist"
    assert native_service_path.exists(), "Native systemd unit must exist"
    assert deploy_sh_path.exists(), "Oracle deploy script must exist"

    service_content = service_path.read_text(encoding="utf-8")
    assert "[Unit]" in service_content
    assert "[Service]" in service_content
    assert "ExecStart=/usr/bin/docker compose up -d" in service_content
    assert "ExecStop=/usr/bin/docker compose down" in service_content

    native_content = native_service_path.read_text(encoding="utf-8")
    assert "scheme_intel.delivery.service" in native_content
    assert "Restart=always" in native_content

    deploy_sh = deploy_sh_path.read_text(encoding="utf-8")
    assert deploy_sh.startswith("#!/usr/bin/env bash")
    assert "docker compose" in deploy_sh


def test_secrets_exclusion_in_git():
    """Verify .gitignore properly excludes .env and private environment files."""
    gitignore_path = REPO_ROOT / ".gitignore"
    assert gitignore_path.exists()
    content = gitignore_path.read_text(encoding="utf-8")

    assert ".env" in content
    assert "!.env.example" in content

    # Ensure .env.example exists and contains template placeholders without real secrets
    example_path = REPO_ROOT / ".env.example"
    assert example_path.exists()
    example_content = example_path.read_text(encoding="utf-8")
    assert "TELEGRAM_BOT_TOKEN=" in example_content
    assert "TELEGRAM_CHAT_ID=" in example_content
    assert "GITHUB_TOKEN=" in example_content


def test_telegram_conversation_metrics(tmp_path):
    """Verify TelegramConversationHandler records and returns telemetry metrics."""
    import time
    from scheme_intel.delivery.request_store import RequestStore
    from scheme_intel.delivery.telegram_router import TelegramMessageRouter

    req_store = RequestStore(db_path=str(tmp_path / "test_requests.db"))
    router = TelegramMessageRouter(request_store=req_store)
    handler = TelegramConversationHandler(router=router)
    metrics = handler.get_metrics()

    assert "is_running" in metrics
    assert "last_update_id" in metrics
    assert "last_poll_time" in metrics
    assert "processed_count" in metrics
    assert metrics["is_running"] is False
    assert metrics["processed_count"] == 0

    # Simulate an update
    unique_update_id = int(time.time() * 1000) % 100000000
    fake_update = {"update_id": unique_update_id, "message": {"text": "/test"}}
    handler.process_update(fake_update, send_reply=False)

    updated_metrics = handler.get_metrics()
    assert updated_metrics["last_update_id"] == unique_update_id
    assert updated_metrics["processed_count"] == 1


def test_system_health_telemetry_payload():
    """Verify get_system_health outputs telemetry structure and valid status."""
    health = get_system_health()
    assert isinstance(health, dict)
    assert "status" in health
    assert "is_healthy" in health
    assert "components" in health
    assert "telegram" in health
    assert "intelligence_memory" in health
    assert "research_queue" in health
    assert "timestamp" in health

    # When service is active
    service = SchemeIntelService(mode="bot")
    health_with_service = get_system_health(service_instance=service)
    assert health_with_service["telemetry"] is not None
    assert "telegram" in health_with_service["telemetry"]
    assert "snapshot_syncer" in health_with_service["telemetry"]
    assert "research_worker" in health_with_service["telemetry"]
