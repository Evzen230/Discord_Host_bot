"""Create local credentials without printing them or replacing existing files."""
import json
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
env = root / ".env"
if not env.exists():
    with env.open("x", encoding="utf-8") as file:
        file.write(
            "BOTDECK_USER=admin\n"
            f"BOTDECK_PASSWORD={secrets.token_hex(32)}\n"
            f"BOTDECK_AGENT_TOKEN={secrets.token_hex(32)}\n"
            "BOTDECK_PORT=8095\n"
        )
    env.chmod(0o600)
    print("Vytvořen .env s náhodným heslem a interním tokenem.")
else:
    print("Existující .env ponechán.")

config = root / "config" / "bots.json"
if not config.exists():
    config.parent.mkdir(parents=True, exist_ok=True)
    with config.open("x", encoding="utf-8") as file:
        json.dump([], file)
        file.write("\n")
    print("Vytvořen prázdný config/bots.json.")
else:
    print("Existující registr botů ponechán.")

