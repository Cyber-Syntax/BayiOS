def main() -> None:
    """Run the app with uvicorn (no reload). For development use `uvicorn ... --reload`."""
    import uvicorn
    from pydantic import ValidationError

    from bayios.bootstrap import ApplicationSettings
    from bayios.main import create_app

    try:
        settings = ApplicationSettings()
    except ValidationError as exc:
        raise SystemExit(f"Invalid configuration:\n{exc}") from exc

    # log_config=None: uvicorn loggers propagate to the root handler set up by configure_logging.
    uvicorn.run(
        create_app(settings), host=settings.host, port=settings.port, log_config=None
    )
