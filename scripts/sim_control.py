"""Contrôleur du simulateur de trafic (service `simulator`, réseau Docker interne uniquement).

Petit serveur HTTP (bibliothèque standard) qui démarre / arrête `scripts/simulate_transactions.py`
et expose son état. Appelé par le back-office (/simulator/*), jamais publié sur la machine.

  GET  /status            -> état, paramètres, dernières lignes de journal
  POST /start {mode, rate, count}   mode : "trafic" | "fraude"
  POST /stop
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INGEST_URL = "http://integration-layer:8002"
MODES = {"trafic": [], "fraude": ["--only-fraud-episodes"]}
LOCK = threading.Lock()
STATE: dict = {"proc": None, "mode": None, "rate": None, "count": None, "started_at": None, "ended_at": None,
               "exit_code": None, "log": deque(maxlen=60), "sent": 0, "alerts": 0}


def _pump(proc: subprocess.Popen) -> None:
    for line in proc.stdout:  # type: ignore[union-attr]
        line = line.rstrip()
        with LOCK:
            if "p=" in line and "USD" in line:       # une transaction signalée (VERIFY / BLOCK) ou une fraude
                STATE["alerts"] += 1
            STATE["log"].append(line[:240])
    code = proc.wait()
    with LOCK:
        if STATE["proc"] is proc:
            STATE["exit_code"], STATE["ended_at"] = code, time.time()


def start(mode: str, rate: float, count: int | None) -> dict:
    if mode not in MODES:
        return {"error": "mode inconnu"}
    rate = max(0.5, min(float(rate), 100.0))
    with LOCK:
        proc = STATE["proc"]
        if proc is not None and proc.poll() is None:
            return {"error": "un simulateur tourne déjà"}
        cmd = [sys.executable, "-u", str(ROOT / "scripts/simulate_transactions.py"), "--url", INGEST_URL,
               "--rate", str(rate), "--fresh-ids", *MODES[mode]]
        if count:
            cmd += ["--n", str(int(count))]
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        STATE.update(proc=proc, mode=mode, rate=rate, count=count, started_at=time.time(), ended_at=None,
                     exit_code=None, alerts=0)
        STATE["log"].clear()
    threading.Thread(target=_pump, args=(proc,), daemon=True).start()
    return {"ok": True}


def stop() -> dict:
    with LOCK:
        proc = STATE["proc"]
    if proc is None or proc.poll() is not None:
        return {"ok": True, "detail": "aucun simulateur en cours"}
    proc.terminate()
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        proc.kill()
    return {"ok": True}


def status() -> dict:
    with LOCK:
        proc = STATE["proc"]
        running = proc is not None and proc.poll() is None
        return {"running": running, "mode": STATE["mode"], "rate": STATE["rate"], "count": STATE["count"],
                "started_at": STATE["started_at"], "ended_at": STATE["ended_at"], "exit_code": STATE["exit_code"],
                "alerts": STATE["alerts"], "log": list(STATE["log"])[-25:]}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):  # noqa: N802
        self._send(200, status()) if self.path == "/status" else self._send(404, {"error": "inconnu"})

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._send(400, {"error": "JSON invalide"})
        if self.path == "/start":
            res = start(str(body.get("mode", "trafic")), body.get("rate", 20), body.get("count"))
            self._send(409 if "error" in res else 200, res)
        elif self.path == "/stop":
            self._send(200, stop())
        else:
            self._send(404, {"error": "inconnu"})

    def log_message(self, *a):  # pas de bruit dans les journaux
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8010), Handler).serve_forever()
