"""Start Overlap and, when necessary, its project-local Typesense server."""
import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.request
from core.services import ROOT, AppServices, Settings
from scripts.setup_local import setup


def healthy(url):
    try:
        with urllib.request.urlopen(url, timeout=1) as response:
            return response.status == 200
    except Exception:
        return False


def start(seed=False):
    setup()
    settings = Settings.from_env()
    children = []
    handles = []
    try:
        health_url = f"{settings.protocol}://{settings.host}:{settings.port}/health"
        if not healthy(health_url):
            if settings.host not in ("127.0.0.1", "localhost") or settings.protocol != "http":
                raise RuntimeError("Configured search server is unavailable. Check .env.")
            binary = ROOT / ".tools" / "typesense-server"
            if not binary.exists():
                raise RuntimeError("Run python -m scripts.setup_local --download first, or start Typesense using Docker.")
            env = os.environ.copy()
            env.update({"TYPESENSE_API_KEY": settings.api_key,
                        "TYPESENSE_DATA_DIR": str(ROOT / ".runtime" / "typesense-data"),
                        "TYPESENSE_API_ADDRESS": "127.0.0.1", "TYPESENSE_API_PORT": str(settings.port),
                        "TYPESENSE_PEERING_ADDRESS": "127.0.0.1", "TYPESENSE_THREAD_POOL_SIZE": "8"})
            log = (ROOT / ".runtime" / "typesense.log").open("a")
            handles.append(log)
            server = subprocess.Popen([str(binary)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            children.append(server)
            print("Starting local Typesense…", flush=True)
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline:
                if server.poll() is not None:
                    raise RuntimeError("Typesense exited. See .runtime/typesense.log.")
                if healthy(health_url):
                    break
                time.sleep(.3)
            else:
                raise RuntimeError("Typesense startup timed out. See .runtime/typesense.log.")
        if seed:
            from scripts.seed import seed_categories
            seed_categories(AppServices(settings))
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", 8501)) == 0:
                raise RuntimeError("Port 8501 is already in use. Stop the existing app before starting another copy.")
        print("Overlap is starting at http://localhost:8501 — press Ctrl+C to stop.", flush=True)
        app = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "main.py"], cwd=ROOT)
        children.append(app)
        app.wait()
    except KeyboardInterrupt:
        print("\nStopping Overlap…")
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
        for handle in handles:
            handle.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", action="store_true", help="Explicitly import/update catalogs before launching")
    try:
        start(parser.parse_args().seed)
    except Exception as exc:
        print(f"Could not start Overlap: {exc}", file=sys.stderr)
        sys.exit(1)
