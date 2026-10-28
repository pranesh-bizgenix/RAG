"""Knowledge Assistant web server: customer chat at /, admin dashboard at /admin."""

from __future__ import annotations

import argparse
import logging
import signal
import threading
import webbrowser
from pathlib import Path

from api.application import Application
from core.config import PROJECT_ROOT, Settings
from core.logging_setup import configure_logging

logger = logging.getLogger("app")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the RAG knowledge assistant web server.")
    parser.add_argument("--host", help="Server host (default: APP_HOST or 127.0.0.1)")
    parser.add_argument("--port", type=int, help="Server port (default: APP_PORT or 8000)")
    parser.add_argument("--store", type=Path, help="Path to the vector store JSON (default: VECTOR_STORE_PATH)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser automatically")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    overrides: dict[str, object] = {}
    if args.host:
        overrides["host"] = args.host
    if args.port:
        overrides["port"] = args.port
    if args.store:
        overrides["store_path"] = args.store if args.store.is_absolute() else PROJECT_ROOT / args.store
    settings = Settings.from_env(**overrides)
    configure_logging(settings.log_level, settings.log_format)

    app = Application(settings)
    if settings.host not in {"127.0.0.1", "localhost", "::1"}:
        logger.warning("There are no accounts: anyone who can reach %s can use the admin dashboard.", settings.host)

    app.start()
    server = app.make_server()
    url = f"http://{settings.host}:{settings.port}"
    logger.info("Knowledge Assistant running at %s (admin dashboard: %s/admin)", url, url)

    def shutdown(*_: object) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    if not args.no_browser and not settings.is_production:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.stop()
        logger.info("Server stopped")


if __name__ == "__main__":
    main()
