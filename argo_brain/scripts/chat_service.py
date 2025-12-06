"""Run the Argo Brain web chat service (FastAPI + uvicorn)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import uvicorn

# Ensure project root is on sys.path when invoked as a script
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from argo_brain.web.app import DEFAULT_HOST, DEFAULT_PORT


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the Argo Brain web chat service")
    parser.add_argument("--host", default=None, help=f"Host to bind (default: ARGO_WEB_HOST or {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=None, help=f"Port to bind (default: ARGO_WEB_PORT or {DEFAULT_PORT})")
    parser.add_argument("--reload", action="store_true", help="Enable autoreload (dev only)")
    parser.add_argument("--ssl-certfile", help="Path to TLS cert (tailscale cert)")
    parser.add_argument("--ssl-keyfile", help="Path to TLS key")
    args = parser.parse_args(argv)

    host = args.host or os.getenv("ARGO_WEB_HOST", DEFAULT_HOST)
    port = args.port or int(os.getenv("ARGO_WEB_PORT", DEFAULT_PORT))
    ssl_certfile = args.ssl_certfile or os.getenv("ARGO_WEB_TLS_CERT")
    ssl_keyfile = args.ssl_keyfile or os.getenv("ARGO_WEB_TLS_KEY")

    uvicorn.run(
        "argo_brain.web.app:app",
        host=host,
        port=port,
        reload=args.reload,
        ssl_certfile=ssl_certfile,
        ssl_keyfile=ssl_keyfile,
    )


if __name__ == "__main__":
    main()
