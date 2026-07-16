"""Entry point for the 1BT Business Intel web server.

Usage:
    uv run python -m frontend.server

    # Or after installing: uvicorn frontend.main:app --host 127.0.0.1 --port 8080
"""


if __name__ == "__main__":
    import uvicorn

    from frontend.config import settings
    uvicorn.run(
        "frontend.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info",
    )
