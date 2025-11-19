from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.config import Settings
from app.db import SessionLocal
from app.models import ModbusReading, RailGrid
from app.schemas import ModbusValue
from app.services.modbus_service import read_modbus

logger = logging.getLogger(__name__)


class ModbusPoller:
    """Background service for periodic Modbus polling with rail grid detection."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._last_error: Optional[str] = None
        self._last_success_time: Optional[datetime] = None
        self._poll_count = 0
        
        # Режимы работы
        self._detection_mode = True  # True = обнаружение движения, False = активный сбор данных
        self._current_rail_grid: Optional[RailGrid] = None
        
        # Базовое значение для сравнения (когда конвейер стоит)
        self._baseline_values: Optional[tuple] = None
        self._baseline_samples: deque = deque(maxlen=3)  # Несколько образцов для стабильности
        
        # Отслеживание стабильности для завершения решетки
        self._stability_samples: deque = deque(maxlen=5)  # 5 одинаковых значений = завершение
        self._stability_threshold: float = 0.1  # Порог для определения "одинаковости" (совпадает с порогом обнаружения движения)
        
    async def start(self) -> None:
        """Start the background polling task."""
        if self._running:
            logger.warning("Modbus poller is already running")
            return
        if not self.settings.modbus_poll_enabled:
            logger.info("Modbus polling is disabled in settings")
            return

        self._running = True
        self._detection_mode = True
        self._current_rail_grid = None
        self._baseline_values = None
        self._baseline_samples.clear()
        self._stability_samples.clear()
        
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(
            f"Started Modbus poller (detection interval: {self.settings.modbus_detection_interval_sec}s, "
            f"active interval: {self.settings.modbus_poll_interval_sec}s)"
        )

    async def stop(self) -> None:
        """Stop the background polling task."""
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        # Завершаем текущую решетку, если она активна
        if self._current_rail_grid:
            await self._complete_rail_grid()
        
        logger.info("Stopped Modbus poller")

    def is_running(self) -> bool:
        """Check if poller is currently running."""
        return self._running

    def get_status(self) -> dict:
        """Get current status of the poller."""
        return {
            "running": self._running,
            "detection_mode": self._detection_mode,
            "current_rail_grid_uuid": (
                self._current_rail_grid.uuid if self._current_rail_grid else None
            ),
            "baseline_established": self._baseline_values is not None,
            "interval_sec": (
                self.settings.modbus_detection_interval_sec
                if self._detection_mode
                else self.settings.modbus_poll_interval_sec
            ),
            "poll_count": self._poll_count,
            "last_success_time": (
                self._last_success_time.isoformat()
                if self._last_success_time
                else None
            ),
            "last_error": self._last_error,
        }

    async def _poll_loop(self) -> None:
        """Main polling loop."""
        # Сначала устанавливаем базовое значение
        await self._establish_baseline()
        
        while self._running:
            try:
                if self._detection_mode:
                    # Режим обнаружения: опрос раз в 15 секунд
                    await self._poll_for_detection()
                    await asyncio.sleep(self.settings.modbus_detection_interval_sec)
                else:
                    # Режим активного сбора: опрос каждую секунду
                    await self._poll_active_collection()
                    await asyncio.sleep(self.settings.modbus_poll_interval_sec)
                    
            except asyncio.CancelledError:
                logger.info("[POLLER] Поллинг отменен")
                break
            except Exception as e:
                error_msg = (
                    f"[POLLER] КРИТИЧЕСКАЯ ОШИБКА в цикле поллинга: {e}. "
                    f"Режим: {'обнаружение' if self._detection_mode else 'активный сбор'}"
                )
                logger.error(error_msg, exc_info=True)
                self._last_error = error_msg
                # При ошибке делаем паузу перед повтором
                logger.warning("[POLLER] Пауза 5 секунд перед повтором...")
                await asyncio.sleep(5.0)

    async def _establish_baseline(self) -> None:
        """Устанавливает базовое значение (когда конвейер стоит)."""
        logger.info(
            f"[POLLER] Установка базового значения (конвейер стоит). "
            f"Устройство: {self.settings.modbus_ip}:{self.settings.modbus_port}"
        )
        from fastapi.concurrency import run_in_threadpool
        
        for i in range(3):  # Делаем 3 опроса для стабильности
            try:
                logger.debug(f"[POLLER] Базовый опрос {i+1}/3...")
                values: list[ModbusValue] = await run_in_threadpool(
                    read_modbus, self.settings, None
                )
                numeric_values = self._extract_numeric_values(values)
                if numeric_values:
                    self._baseline_samples.append(tuple(sorted(numeric_values)))
                    logger.debug(
                        f"[POLLER] Базовый образец {i+1}: {tuple(sorted(numeric_values))}"
                    )
                else:
                    logger.warning(f"[POLLER] Базовый опрос {i+1}: нет числовых значений")
                await asyncio.sleep(2.0)  # Пауза между опросами
            except Exception as e:
                logger.error(
                    f"[POLLER] ОШИБКА при установке базового образца {i+1}: {e}",
                    exc_info=True
                )
        
        if self._baseline_samples:
            # Берем последнее значение как базовое
            self._baseline_values = self._baseline_samples[-1]
            logger.info(
                f"[POLLER] ✓ Базовое значение установлено: {self._baseline_values} "
                f"(на основе {len(self._baseline_samples)} образцов)"
            )
        else:
            logger.warning(
                f"[POLLER] Не удалось установить базовое значение. "
                f"Будет использовано первое прочитанное значение."
            )

    async def _poll_for_detection(self) -> None:
        """Опрос в режиме обнаружения движения."""
        from fastapi.concurrency import run_in_threadpool
        
        logger.debug(
            f"[POLLER] Режим обнаружения: опрос Modbus "
            f"({self.settings.modbus_ip}:{self.settings.modbus_port})..."
        )
        
        try:
            values: list[ModbusValue] = await run_in_threadpool(
                read_modbus, self.settings, None
            )
        except Exception as e:
            logger.error(
                f"[POLLER] ОШИБКА при опросе в режиме обнаружения: {e}",
                exc_info=True
            )
            return
        
        numeric_values = self._extract_numeric_values(values)
        if not numeric_values:
            logger.debug("[POLLER] Нет числовых значений для сравнения")
            return
        
        current_values_tuple = tuple(sorted(numeric_values))
        logger.debug(f"[POLLER] Текущие значения: {current_values_tuple}")
        
        # Если базовое значение еще не установлено, используем текущее
        if self._baseline_values is None:
            self._baseline_values = current_values_tuple
            logger.info(
                f"[POLLER] Базовое значение установлено из первого чтения: "
                f"{self._baseline_values}"
            )
            return
        
        # Сравниваем с базовым значением
        if self._values_differ(current_values_tuple, self._baseline_values):
            logger.info(
                f"[POLLER] ✓ ДВИЖЕНИЕ ОБНАРУЖЕНО!\n"
                f"  Базовое значение: {self._baseline_values}\n"
                f"  Текущее значение: {current_values_tuple}\n"
                f"  Создание новой решетки..."
            )
            await self._start_rail_grid()
            self._detection_mode = False
            self._stability_samples.clear()
            logger.info("[POLLER] Переключение в режим активного сбора данных")
        else:
            logger.debug(
                f"[POLLER] Движение не обнаружено "
                f"(значения совпадают с базовым: {self._baseline_values})"
            )

    async def _poll_active_collection(self) -> None:
        """Опрос в режиме активного сбора данных."""
        from fastapi.concurrency import run_in_threadpool
        
        if not self._current_rail_grid:
            logger.error("Active collection mode but no rail grid!")
            self._detection_mode = True
            return
        
        values: list[ModbusValue] = await run_in_threadpool(
            read_modbus, self.settings, None
        )
        
        # Сохраняем данные в текущую решетку
        db: Session = SessionLocal()
        try:
            timestamp = datetime.now(timezone.utc)
            reading = ModbusReading(
                timestamp=timestamp,
                values=[value.model_dump() for value in values],
                rail_grid_id=self._current_rail_grid.id,
                extra={"source": "active_collection"},
            )
            db.add(reading)
            db.commit()
            self._poll_count += 1
            self._last_success_time = timestamp
            self._last_error = None
            
            # Проверяем стабильность для определения завершения
            numeric_values = self._extract_numeric_values(values)
            if numeric_values:
                current_values_tuple = tuple(sorted(numeric_values))
                self._stability_samples.append(current_values_tuple)
                
                # Если достаточно образцов и все одинаковые - завершаем решетку
                if len(self._stability_samples) >= 5:
                    if self._all_values_similar(self._stability_samples):
                        logger.info("Values stabilized, completing rail grid...")
                        await self._complete_rail_grid()
                        self._detection_mode = True
                        # Обновляем базовое значение
                        self._baseline_values = current_values_tuple
                        self._baseline_samples.clear()
                        self._baseline_samples.append(current_values_tuple)
                        
        except Exception as e:
            db.rollback()
            raise
        finally:
            db.close()

    async def _start_rail_grid(self) -> None:
        """Создает новую решетку и запускает сбор фотографий."""
        db: Session = SessionLocal()
        try:
            rail_grid = RailGrid(
                status="active",
                started_at=datetime.now(timezone.utc),
            )
            db.add(rail_grid)
            db.commit()
            db.refresh(rail_grid)
            
            self._current_rail_grid = rail_grid
            logger.info(f"Started new rail grid: {rail_grid.uuid}")
            
            # Запускаем сбор фотографий в фоне
            asyncio.create_task(self._start_camera_capture(rail_grid))
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create rail grid: {e}", exc_info=True)
            raise
        finally:
            db.close()

    async def _complete_rail_grid(self) -> None:
        """Завершает текущую решетку."""
        if not self._current_rail_grid:
            return
        
        db: Session = SessionLocal()
        try:
            self._current_rail_grid.status = "completed"
            self._current_rail_grid.completed_at = datetime.now(timezone.utc)
            db.add(self._current_rail_grid)
            db.commit()
            
            logger.info(
                f"Completed rail grid: {self._current_rail_grid.uuid} "
                f"(duration: {self._current_rail_grid.completed_at - self._current_rail_grid.started_at})"
            )
            self._current_rail_grid = None
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to complete rail grid: {e}", exc_info=True)
        finally:
            db.close()

    async def _start_camera_capture(self, rail_grid: RailGrid) -> None:
        """Запускает сбор фотографий для решетки."""
        try:
            from app.services.camera_service import capture_with_cameras
            from app.schemas import CaptureRequest
            from fastapi.concurrency import run_in_threadpool
            
            # Создаем запрос на сбор фотографий
            # Используем значения из .env для параметров захвата
            capture_request = CaptureRequest(
                uid=rail_grid.uuid,
                connection_class="auto",  # Можно сделать настраиваемым
                use_default_cameras=True,
                front_count=100,  # Большое количество для непрерывного сбора
                top_count=100,
                interval_sec=self.settings.hikvision_capture_interval,  # Из .env
                # Остальные параметры будут взяты из .env, так как они Optional
                show_preview=None,  # Используется из .env
                crop_top=None,  # Используется из .env
                crop_bottom=None,  # Используется из .env
                crop_left=None,  # Используется из .env
                crop_right=None,  # Используется из .env
                jpeg_quality=None,  # Используется из .env
                archive_after_capture=None,  # Используется из .env
                archive_remove_originals=None,  # Используется из .env
            )
            
            # Запускаем в отдельном потоке (блокирующая операция)
            result = await run_in_threadpool(
                capture_with_cameras, capture_request, self.settings
            )
            
            # Сохраняем сессию фотографирования в базу
            db: Session = SessionLocal()
            try:
                from app.models import CaptureSession
                session = CaptureSession(
                    uid=rail_grid.uuid,
                    connection_class=capture_request.connection_class,
                    front_saved=result.front_saved,
                    top_saved=result.top_saved,
                    front_dir=result.front_dir,
                    top_dir=result.top_dir,
                    front_archive=result.front_archive,
                    top_archive=result.top_archive,
                    errors=result.errors,
                    camera_config=capture_request.model_dump(),
                    rail_grid_id=rail_grid.id,
                )
                db.add(session)
                db.commit()
                logger.info(
                    f"Camera capture completed for rail grid {rail_grid.uuid}: "
                    f"{result.front_saved} front, {result.top_saved} top images"
                )
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to save camera session: {e}", exc_info=True)
            finally:
                db.close()
                
        except Exception as e:
            logger.error(
                f"Failed to start camera capture for rail grid {rail_grid.uuid}: {e}",
                exc_info=True
            )

    def _extract_numeric_values(self, values: list[ModbusValue]) -> list[float]:
        """Извлекает числовые значения из ModbusValue."""
        numeric = []
        for value in values:
            if isinstance(value.value, (int, float)):
                numeric.append(float(value.value))
        return numeric

    def _values_differ(self, values1: tuple, values2: tuple, threshold: float = 0.1) -> bool:
        """Проверяет, отличаются ли два набора значений."""
        if len(values1) != len(values2):
            return True
        
        for v1, v2 in zip(values1, values2):
            if abs(v1 - v2) > threshold:
                return True
        return False

    def _all_values_similar(self, samples: deque, threshold: Optional[float] = None) -> bool:
        """Проверяет, все ли образцы в deque похожи друг на друга."""
        if len(samples) < 2:
            return False
        
        if threshold is None:
            threshold = self._stability_threshold
        
        samples_list = list(samples)
        first = samples_list[0]
        
        for sample in samples_list[1:]:
            if self._values_differ(first, sample, threshold):
                return False
        return True


# Global poller instance
_poller: Optional[ModbusPoller] = None


def get_poller(settings: Settings) -> ModbusPoller:
    """Get or create the global Modbus poller instance."""
    global _poller
    if _poller is None:
        _poller = ModbusPoller(settings)
    return _poller
