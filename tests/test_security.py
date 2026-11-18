import importlib
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from botdeck.registry import ID_LABEL, MANAGED_LABEL, PROJECT, Bot, is_managed


def container(project=PROJECT, managed="true", bot_id="alpha", oneoff="False"):
    item = MagicMock()
    item.labels = {"com.docker.compose.project": project, MANAGED_LABEL: managed,
                   ID_LABEL: bot_id, "com.docker.compose.oneoff": oneoff}
    item.attrs = {"State": {"Status": "running"}}
    return item


@pytest.fixture
def agent(monkeypatch, tmp_path):
    monkeypatch.setenv("BOTDECK_AGENT_TOKEN", "t" * 64)
    config = tmp_path / "bots.json"
    config.write_text(json.dumps([{"id": "alpha", "name": "Alpha"}]), encoding="utf-8")
    monkeypatch.setenv("BOTDECK_CONFIG", str(config))
    module = importlib.import_module("botdeck.agent")
    return importlib.reload(module)


@pytest.mark.parametrize("kwargs", [
    {"project": "existing-important-project"}, {"managed": "false"},
    {"bot_id": "other"}, {"oneoff": "True"},
])
def test_foreign_containers_rejected(kwargs):
    assert not is_managed(container(**kwargs), "alpha")


def test_expected_container_allowed():
    assert is_managed(container(), "alpha")


@pytest.mark.parametrize("method,path", [("get", "/overview"), ("get", "/bots/alpha/logs"), ("post", "/bots/alpha/stop")])
def test_agent_requires_token(agent, method, path):
    with TestClient(agent.app) as client:
        assert getattr(client, method)(path).status_code == 401


def test_unregistered_id_does_not_query_docker(agent):
    engine = MagicMock()
    with pytest.raises(HTTPException) as exc:
        agent.find_container(engine, "important-project")
    assert exc.value.status_code == 404
    engine.containers.list.assert_not_called()


@pytest.mark.parametrize("action", ["start", "stop", "restart"])
def test_mutations_cannot_touch_foreign_containers(agent, monkeypatch, action):
    foreign = container(project="important-project")
    engine = MagicMock()
    engine.containers.list.return_value = [foreign]
    monkeypatch.setattr(agent, "client", lambda: engine)
    engine.__enter__.return_value = engine
    with TestClient(agent.app) as client:
        response = client.post(f"/bots/alpha/{action}", headers={"Authorization": "Bearer " + "t" * 64})
    assert response.status_code == 404
    foreign.start.assert_not_called()
    foreign.stop.assert_not_called()
    foreign.restart.assert_not_called()


def test_duplicate_identity_refused(agent):
    engine = MagicMock()
    engine.containers.list.return_value = [container(), container()]
    with pytest.raises(HTTPException) as exc:
        agent.find_container(engine, "alpha")
    assert exc.value.status_code == 409


def test_valid_action_targets_only_registered_container(agent, monkeypatch):
    target = container()
    engine = MagicMock()
    engine.containers.list.return_value = [target]
    engine.__enter__.return_value = engine
    monkeypatch.setattr(agent, "client", lambda: engine)
    with TestClient(agent.app) as client:
        response = client.post("/bots/alpha/stop", headers={"Authorization": "Bearer " + "t" * 64})
    assert response.status_code == 200
    target.stop.assert_called_once_with(timeout=10)
    filters = engine.containers.list.call_args.kwargs["filters"]["label"]
    assert f"com.docker.compose.project={PROJECT}" in filters


@pytest.mark.parametrize("url", ["javascript:alert(1)", "//evil.example", "https://user:pass@example.org", "file:///etc/passwd"])
def test_unsafe_dashboard_links_rejected(url):
    with pytest.raises(ValueError):
        Bot(id="alpha", name="Alpha", dashboard_url=url)


@pytest.fixture
def web(monkeypatch):
    monkeypatch.setenv("BOTDECK_PASSWORD", "p" * 64)
    monkeypatch.setenv("BOTDECK_AGENT_TOKEN", "t" * 64)
    module = importlib.import_module("botdeck.web")
    return importlib.reload(module)


def test_dashboard_requires_login(web):
    with TestClient(web.app) as client:
        assert client.get("/").status_code == 401
        response = client.get("/", auth=("admin", "p" * 64))
        assert response.status_code == 200
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


@pytest.mark.parametrize("headers", [{"Content-Type": "application/x-www-form-urlencoded"}, {"Content-Type": "application/json", "Sec-Fetch-Site": "cross-site"}])
def test_cross_site_mutations_refused(web, headers):
    with TestClient(web.app) as client:
        response = client.post("/api/bots/alpha/stop", auth=("admin", "p" * 64), headers=headers, content="{}")
        assert response.status_code in {403, 415}


def test_docker_outage_is_reported(agent, monkeypatch):
    def unavailable():
        raise agent.DockerException("sensitive internal details")
    monkeypatch.setattr(agent, "client", unavailable)
    with TestClient(agent.app) as client:
        response = client.get("/overview", headers={"Authorization": "Bearer " + "t" * 64})
    assert response.status_code == 503
    assert "sensitive" not in response.text


def test_host_ram_uses_host_proc(agent, monkeypatch, tmp_path):
    (tmp_path / "meminfo").write_text("MemTotal: 4096000 kB\nMemAvailable: 2048000 kB\n")
    (tmp_path / "loadavg").write_text("0.42 0.10 0.05 1/200 1234")
    (tmp_path / "uptime").write_text("3600.0 7200.0")
    monkeypatch.setenv("BOTDECK_HOST_PROC", str(tmp_path))
    assert agent.host_metrics()["memory_used_bytes"] == 2048000 * 1024
