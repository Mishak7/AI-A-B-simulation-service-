import logging
from logging.handlers import RotatingFileHandler

from app.config import Settings


def configure_logging(settings: Settings) -> None:
    log_file = settings.log_file
    log_file.parent.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    file_handler = _find_simab_file_handler(root_logger)
    if file_handler is None:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=settings.log_max_bytes,
            backupCount=settings.log_backup_count,
            encoding="utf-8",
        )
        file_handler._simab_file_handler = True  # type: ignore[attr-defined]
        root_logger.addHandler(file_handler)

    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)


def _find_simab_file_handler(logger: logging.Logger) -> RotatingFileHandler | None:
    for handler in logger.handlers:
        if getattr(handler, "_simab_file_handler", False):
            return handler
    return None
