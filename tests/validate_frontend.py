"""Run real frontend/API/Streamlit checks without a browser or new test packages.

Requires an existing frontend production build and the ticket_ai interpreter.
All started processes are stopped in finally blocks.
"""

import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import httpx


PROJECT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_DIR / "frontend"
HIDDEN_PROCESS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def free_port():
    with socket.socket() as connection:
        try:
            connection.bind(("127.0.0.1", 8000))
        except OSError:
            connection.bind(("127.0.0.1", 0))
        return connection.getsockname()[1]


def start_api(port, environment, log):
    return subprocess.Popen(
        [sys.executable, "-B", "-m", "uvicorn", "api.main:app",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=PROJECT_DIR, env=environment, stdout=log, stderr=log,
        creationflags=HIDDEN_PROCESS,
    )


def stop(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def wait_for_api(base, process):
    for _ in range(150):
        if process.poll() is not None:
            raise RuntimeError("Validation API exited before startup completed.")
        try:
            if httpx.get(base + "/api/health", timeout=1, trust_env=False).status_code == 200:
                return
        except (httpx.ConnectError, httpx.TimeoutException):
            pass
        time.sleep(0.1)
    raise RuntimeError("Validation API did not become ready.")


def run_node(environment, compile_first=False):
    arguments = [shutil.which("node"), "--test", ".validation/verify.mjs"]
    if compile_first:
        arguments = [shutil.which("node"), "scripts/run-validation.mjs"]
    subprocess.run(arguments, cwd=FRONTEND_DIR, env=environment, check=True)


def main():
    if not (FRONTEND_DIR / "dist" / "index.html").is_file():
        raise SystemExit("Run npm run build in frontend/ before validation.")
    environment = dict(
        os.environ, PYTHONDONTWRITEBYTECODE="1", TICKET_PYTHON=sys.executable,
        STREAMLIT_BROWSER_GATHER_USAGE_STATS="false",
    )
    with tempfile.TemporaryDirectory(prefix=".test_tmp_frontend_", dir=PROJECT_DIR) as temporary:
        environment.update(TEMP=temporary, TMP=temporary)
        environment["REVIEW_LOG_PATH"] = str(Path(temporary) / "manual_review.jsonl")
        review_token = secrets.token_urlsafe(32)
        environment["ADMIN_REVIEW_TOKEN"] = review_token
        environment["VERIFY_REVIEW_TOKEN"] = review_token
        port = free_port()
        base = f"http://127.0.0.1:{port}"
        environment["VERIFY_API_URL"] = base
        environment["VERIFY_MODE"] = "normal"
        api = None
        missing_api = None
        vite = None
        with (Path(temporary) / "server.log").open("w", encoding="utf-8") as log:
            try:
                api = start_api(port, environment, log)
                wait_for_api(base, api)
                with httpx.Client(base_url=base, trust_env=False) as client:
                    home = client.get("/")
                    assert home.status_code == 200
                    assert '<div id="root">' in home.text
                    assert client.get("/performance").text == home.text
                    assert client.get("/about").text == home.text
                    assert client.get("/review-log").text == home.text
                    for asset in re.findall(r'(?:src|href)="(/assets/[^"]+)"', home.text):
                        response = client.get(asset)
                        assert response.status_code == 200
                        if asset.endswith(".css"):
                            for font in re.findall(r'url\((/assets/[^)]+)\)', response.text):
                                assert client.get(font).status_code == 200
                    assert client.get("/api/health").json()["models_loaded"] is True
                    triage = client.post("/api/triage", json={"text": "My payment was deducted twice."})
                    assert triage.status_code == 200
                    assert client.get("/api/not-a-route").status_code == 404
                    actual = client.get("/api/evaluation").json()
                    assert actual == json.loads((PROJECT_DIR / "models" / "evaluation.json").read_bytes())
                    print("Built frontend, SPA fallback, assets, and API routes: PASS", flush=True)
                if port == 8000:
                    vite = subprocess.Popen(
                        [shutil.which("node"), "node_modules/vite/bin/vite.js",
                         "--host", "127.0.0.1", "--port", "5173", "--strictPort"],
                        cwd=FRONTEND_DIR, env=environment, stdout=log, stderr=log,
                        creationflags=HIDDEN_PROCESS,
                    )
                    wait_for_api("http://127.0.0.1:5173", vite)
                    with httpx.Client(trust_env=False) as client:
                        assert client.get("http://127.0.0.1:5173/").status_code == 200
                        payload = {"text": "My payment was deducted twice."}
                        proxied = client.post("http://127.0.0.1:5173/api/triage", json=payload)
                        direct = client.post(base + "/api/triage", json=payload)
                        assert proxied.status_code == 200 and proxied.json() == direct.json()
                    print("Vite development proxy health and triage: PASS", flush=True)
                    stop(vite)
                else:
                    print("Port 8000 was occupied; development proxy check skipped.", flush=True)
                run_node(environment, compile_first=True)
                stop(api)
                environment["VERIFY_MODE"] = "unreachable"
                run_node(environment)
                missing_environment = dict(environment, EVALUATION_PATH=str(Path(temporary) / "absent.json"))
                missing_environment["VERIFY_MODE"] = "missing-evaluation"
                missing_api = start_api(port, missing_environment, log)
                wait_for_api(base, missing_api)
                run_node(missing_environment)
            finally:
                stop(api)
                stop(missing_api)
                stop(vite)
                print("All validation API processes stopped.", flush=True)


if __name__ == "__main__":
    main()
