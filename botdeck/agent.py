import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import docker
from docker.errors import DockerException
from fastapi import Depends, FastAPI, Header, HTTPException

from botdeck.registry import ID_LABEL, MANAGED_LABEL, PROJECT, is_managed, load_bots

TOKEN = os.environ["BOTDECK_AGENT_TOKEN"]
if len(TOKEN) < 32:
    raise RuntimeError("BOTDECK_AGENT_TOKEN must contain at least 32 characters")

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def authorize(authorization: str = Header(default="")):
    if not secrets.compare_digest(authorization.encode(), f"Bearer {TOKEN}".encode()):
        raise HTTPException(401, "Unauthorized")


def client():
    return docker.from_env(timeout=25)


def registry():
    try:
        return load_bots()
    except (OSError, ValueError, TypeError, KeyError):
        raise HTTPException(503, "Neplatný nebo chybějící config/bots.json") from None


def find_container(engine, bot_id):
    # Never accept a container ID or name supplied by the browser.
    if bot_id not in {bot.id for bot in registry()}:
        raise HTTPException(404, "Neznámý bot")
    matches = engine.containers.list(all=True, filters={"label": [
        f"com.docker.compose.project={PROJECT}", f"{MANAGED_LABEL}=true", f"{ID_LABEL}={bot_id}",
    ]})
    matches = [item for item in matches if is_managed(item, bot_id)]
    if not matches:
        raise HTTPException(404, "Kontejner bota není nasazený")
    if len(matches) != 1:
        raise HTTPException(409, "Více kontejnerů se stejným ID; operace odmítnuta")
    return matches[0]


def usage(stats):
    current, previous = stats.get("cpu_stats", {}), stats.get("precpu_stats", {})
    delta = current.get("cpu_usage", {}).get("total_usage", 0) - previous.get("cpu_usage", {}).get("total_usage", 0)
    system = current.get("system_cpu_usage", 0) - previous.get("system_cpu_usage", 0)
    cores = current.get("online_cpus") or len(current.get("cpu_usage", {}).get("percpu_usage", [])) or 1
    cpu = round(delta / system * cores * 100, 1) if previous.get("system_cpu_usage") and system > 0 and delta >= 0 else None
    memory = stats.get("memory_stats", {})
    cache = memory.get("stats", {}).get("inactive_file", 0)
    return {"cpu_percent": cpu, "memory_bytes": max(0, memory.get("usage", 0) - cache), "memory_limit_bytes": memory.get("limit", 0)}


def host_metrics():
    # Read the host procfs explicitly: container-local memory limits are not host RAM.
    try:
        proc = Path(os.getenv("BOTDECK_HOST_PROC", "/host/proc"))
        memory = {}
        for line in (proc / "meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            memory[key] = int(value.strip().split()[0]) * 1024
        return {
            "memory_total_bytes": memory["MemTotal"],
            "memory_used_bytes": memory["MemTotal"] - memory["MemAvailable"],
            "load_1m": float((proc / "loadavg").read_text().split()[0]),
            "uptime_seconds": float((proc / "uptime").read_text().split()[0]),
        }
    except (OSError, ValueError, KeyError):
        return None


@app.get("/healthz")
def health():
    return {"ok": True}


@app.get("/overview", dependencies=[Depends(authorize)])
def overview():
    bots = registry()
    result = []
    try:
        with client() as engine:
            for bot in bots:
                row = {**bot.model_dump(), "status": "not_deployed", "discord_status": "unknown"}
                try:
                    container = find_container(engine, bot.id)
                    state = container.attrs.get("State", {})
                    row.update(status=state.get("Status", "unknown"), started_at=state.get("StartedAt"),
                               health=state.get("Health", {}).get("Status", "unknown"),
                               restart_count=container.attrs.get("RestartCount", 0))
                    if row["status"] == "running":
                        try:
                            row.update(usage(container.stats(stream=False, one_shot=True)))
                        except DockerException:
                            row["metrics_error"] = True
                except HTTPException as exc:
                    if exc.status_code != 404:
                        row.update(status="error", error=exc.detail)
                result.append(row)
    except DockerException:
        raise HTTPException(503, "Docker není dostupný; zkontroluj agenta a socket") from None
    return {"bots": result, "host": host_metrics(), "updated_at": datetime.now(timezone.utc).isoformat()}


@app.get("/bots/{bot_id}/logs", dependencies=[Depends(authorize)])
def logs(bot_id: str):
    try:
        with client() as engine:
            container = find_container(engine, bot_id)
            # Bound response size even for applications writing very long log lines.
            output = container.logs(tail=200, timestamps=True)[-131072:]
            return {"logs": output.decode("utf-8", errors="replace")}
    except DockerException:
        raise HTTPException(503, "Logy nejsou dostupné") from None


@app.post("/bots/{bot_id}/{action}", dependencies=[Depends(authorize)])
def action(bot_id: str, action: Literal["start", "stop", "restart"]):
    try:
        with client() as engine:
            container = find_container(engine, bot_id)
            if action == "start":
                container.start()
            elif action == "stop":
                container.stop(timeout=10)
            else:
                container.restart(timeout=10)
    except DockerException:
        raise HTTPException(503, "Operace selhala; ověř stav kontejneru a Dockeru") from None
    return {"ok": True}

