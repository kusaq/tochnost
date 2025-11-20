import logging
import sys
from pathlib import Path
from typing import Literal


def setup_logging(
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO",
    log_to_file: bool = False,
    log_file_path: str | None = "logs/app.log",
):
    """
    Настраивает логирование с возможностью логов в файл.

    :param level: Уровень логирования
    :param log_to_file: Писать ли в файл
    :param log_file_path: Путь к лог-файлу (если включено)
    """
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()  # Чтобы не было дубликатов
    root_logger.addHandler(console_handler)

    if log_to_file:
        Path(log_file_path).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
