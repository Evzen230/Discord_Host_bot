import os
import secrets
from pathlib import Path
from typing import Literal

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles

USER = os.getenv("BOTDECK_USER", "admin")
PASSWORD = os.environ["BOTDECK_PASSWORD"]
TOKEN = os.environ["BOTDECK_AGENT_TOKEN"]
AGENT = os.getenv("BOTDECK_AGENT_URL", "http://agent:8081")
if len(PASSWORD) < 16 or len(TOKEN) < 32:
    raise RuntimeError("Use a password of at least 16 and an agent token of at least 32 characters")

STATIC = Path(__file__).parent / "static"
security = HTTPBasic()
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def login(credentials: HTTPBasicCredentials = Depends(security)):
    valid_user = secrets.compare_digest(credentials.username.encode(), USER.encode())
    valid_password = secrets.compare_digest(credentials.password.encode(), PASSWORD.encode())
    if not (valid_user and valid_password):
        raise HTTPException(401, "Nesprávné přihlašovací údaje", headers={"WWW-Authenticate": "Basic"})


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.update({
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
    })
    return response


def forward(path, method="GET"):
    try:
        with httpx.Client(timeout=45, trust_env=False) as client:
            response = client.request(method, f"{AGENT}{path}", headers={"Authorization": f"Bearer {TOKEN}"})
            data = response.json()
        return JSONResponse(data, status_code=response.status_code)
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "Interní agent není dostupný") from None


@app.get("/healthz")
def health():
    return {"ok": True}


@app.get("/", dependencies=[Depends(login)])
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/overview", dependencies=[Depends(login)])
def overview():
    return forward("/overview")


@app.get("/api/bots/{bot_id}/logs", dependencies=[Depends(login)])
def logs(bot_id: str):
    validate_id(bot_id)
    return forward(f"/bots/{bot_id}/logs")


def validate_id(bot_id):
    import re
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", bot_id):
        raise HTTPException(400, "Neplatné ID bota")


@app.post("/api/bots/{bot_id}/{action}", dependencies=[Depends(login)])
def action(bot_id: str, action: Literal["start", "stop", "restart"], request: Request):
    validate_id(bot_id)
    # Cross-origin forms cannot send JSON; browsers preflight cross-origin JSON.
    # No CORS permissions are granted. Reject cross-site fetches explicitly too.
    if request.headers.get("content-type", "").split(";")[0] != "application/json":
        raise HTTPException(415, "Vyžadován JSON požadavek")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Cross-site request rejected")
    return forward(f"/bots/{bot_id}/{action}", "POST")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
