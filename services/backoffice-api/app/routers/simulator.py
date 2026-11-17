"""Simulateur de trafic temps réel : démarrage, arrêt et état (le service `simulator` fait le travail)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.events import Publisher, get_publisher
from app.security import get_current_user, require_role
from shared.database.models import BackofficeUser

router = APIRouter(prefix="/simulator", tags=["simulator"])
SIMULATOR_URL = os.getenv("SIMULATOR_URL", "http://simulator:8010")


class StartRequest(BaseModel):
    mode: str = Field("trafic", pattern="^(trafic|fraude)$")
    rate: float = Field(20, ge=0.5, le=100)
    count: int | None = Field(None, ge=1, le=1_000_000)


def call(path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(f"{SIMULATOR_URL}{path}", method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read()).get("error", "erreur du simulateur")
        except ValueError:
            detail = "erreur du simulateur"
        raise HTTPException(e.code, detail)
    except (urllib.error.URLError, OSError):
        raise HTTPException(503, "service simulateur indisponible")


@router.get("/status")
def status(_=Depends(get_current_user)):
    return call("/status")


@router.post("/start")
def start(req: StartRequest, user: BackofficeUser = Depends(require_role("SUPERVISEUR")),
          pub: Publisher = Depends(get_publisher)):
    res = call("/start", req.model_dump())
    pub.audit(user.email, "SIMULATEUR_DEMARRE", "simulator", None, req.model_dump())
    return res


@router.post("/stop")
def stop(user: BackofficeUser = Depends(require_role("SUPERVISEUR")), pub: Publisher = Depends(get_publisher)):
    res = call("/stop", {})
    pub.audit(user.email, "SIMULATEUR_ARRETE", "simulator", None, {})
    return res
