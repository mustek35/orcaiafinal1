import logging

DEFAULT_LEVEL = logging.INFO
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'

logging.basicConfig(level=DEFAULT_LEVEL, format=LOG_FORMAT)


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger with the given name."""
    return logging.getLogger(name)