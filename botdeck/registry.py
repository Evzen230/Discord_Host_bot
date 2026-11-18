import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator

PROJECT = "botdeck-bots"
MANAGED_LABEL = "cz.botdeck.managed"
ID_LABEL = "cz.botdeck.bot-id"


class Bot(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,47}$")
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=200)
    dashboard_url: str | None = None

    @field_validator("dashboard_url")
    @classmethod
    def safe_url(cls, value):
        if value is not None:
            url = urlsplit(value)
            if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
                raise ValueError("Dashboard URL must be an HTTP(S) URL without credentials")
        return value


def load_bots():
    path = Path(os.getenv("BOTDECK_CONFIG", "config/bots.json"))
    bots = [Bot.model_validate(row) for row in json.loads(path.read_text(encoding="utf-8"))]
    if len({bot.id for bot in bots}) != len(bots):
        raise ValueError("Duplicate bot IDs in configuration")
    return bots


def is_managed(container, bot_id):
    labels = container.labels
    return (
        labels.get("com.docker.compose.project") == PROJECT
        and labels.get(MANAGED_LABEL) == "true"
        and labels.get(ID_LABEL) == bot_id
        and labels.get("com.docker.compose.oneoff", "false").lower() == "false"
    )

