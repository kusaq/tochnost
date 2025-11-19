import logging
from typing import Iterable, List, Tuple

from collect_data import DataCollector, build_rtsp_url, test_ip_camera

from app.config import Settings
from app.schemas import (
    CameraTarget,
    CameraTestResult,
    CaptureRequest,
    CaptureResponse,
)

logger = logging.getLogger(__name__)


def _resolve_camera_sources(request: CaptureRequest, settings: Settings) -> Tuple[str, str]:
    """
    Разрешает URL источников камер из запроса или настроек.
    
    Args:
        request: Запрос на захват с параметрами камер
        settings: Настройки приложения с параметрами камер по умолчанию
    
    Returns:
        Кортеж (top_url, front_url)
    
    Raises:
        ValueError: Если URL камер не предоставлены
    """
    logger.info(f"[CAMERA] Разрешение источников камер (use_default={request.use_default_cameras})")
    
    if request.use_default_cameras:
        logger.debug(
            f"[CAMERA] Использование камер по умолчанию:\n"
            f"  Top: {settings.hikvision_top_ip}:{settings.hikvision_rtsp_port} "
            f"(channel={settings.hikvision_top_channel})\n"
            f"  Front: {settings.hikvision_front_ip}:{settings.hikvision_rtsp_port} "
            f"(channel={settings.hikvision_front_channel})"
        )
        
        try:
            top_url = build_rtsp_url(
                settings.hikvision_top_ip,
                settings.hikvision_user,
                settings.hikvision_pass,
                channel=settings.hikvision_top_channel,
                port=settings.hikvision_rtsp_port,
            )
            logger.debug(f"[CAMERA] Top camera URL: {top_url}")
        except Exception as e:
            error_msg = (
                f"[CAMERA] ОШИБКА построения URL для top камеры "
                f"({settings.hikvision_top_ip}): {e}"
            )
            logger.error(error_msg, exc_info=True)
            raise ValueError(error_msg) from e
        
        try:
            front_url = build_rtsp_url(
                settings.hikvision_front_ip,
                settings.hikvision_user,
                settings.hikvision_pass,
                channel=settings.hikvision_front_channel,
                port=settings.hikvision_rtsp_port,
            )
            logger.debug(f"[CAMERA] Front camera URL: {front_url}")
        except Exception as e:
            error_msg = (
                f"[CAMERA] ОШИБКА построения URL для front камеры "
                f"({settings.hikvision_front_ip}): {e}"
            )
            logger.error(error_msg, exc_info=True)
            raise ValueError(error_msg) from e
    else:
        top_url = request.top_camera_url or ""
        front_url = request.front_camera_url or ""
        logger.debug(
            f"[CAMERA] Использование пользовательских URL:\n"
            f"  Top: {top_url}\n"
            f"  Front: {front_url}"
        )

    if not top_url or not front_url:
        error_msg = (
            f"[CAMERA] ОШИБКА: URL камер не предоставлены. "
            f"Top URL: {'предоставлен' if top_url else 'ОТСУТСТВУЕТ'}, "
            f"Front URL: {'предоставлен' if front_url else 'ОТСУТСТВУЕТ'}. "
            f"Используйте use_default_cameras=True или предоставьте явные URL."
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    logger.info(f"[CAMERA] ✓ Источники камер разрешены успешно")
    return top_url, front_url


def capture_with_cameras(request: CaptureRequest, settings: Settings) -> CaptureResponse:
    """
    Захватывает изображения с камер Hikvision.
    
    Args:
        request: Запрос на захват с параметрами
        settings: Настройки приложения
    
    Returns:
        CaptureResponse с результатами захвата
    
    Raises:
        ValueError: При ошибках разрешения URL камер
        Exception: При ошибках захвата изображений
    """
    logger.info(
        f"[CAMERA] Начало захвата изображений для UID={request.uid}, "
        f"connection_class={request.connection_class}"
    )
    # Определяем фактические значения (из запроса или .env)
    actual_interval = request.interval_sec
    actual_jpeg_quality = request.jpeg_quality if request.jpeg_quality is not None else settings.hikvision_jpeg_quality
    actual_archive = request.archive_after_capture if request.archive_after_capture is not None else settings.hikvision_archive_after_capture
    
    logger.debug(
        f"[CAMERA] Параметры захвата:\n"
        f"  Front: {request.front_count} кадров, интервал {actual_interval}s\n"
        f"  Top: {request.top_count} кадров, интервал {request.top_interval_sec or actual_interval}s\n"
        f"  Data root: {request.data_root or settings.data_root}\n"
        f"  JPEG quality: {actual_jpeg_quality} (из {'запроса' if request.jpeg_quality is not None else '.env'})\n"
        f"  Archive: {actual_archive} (из {'запроса' if request.archive_after_capture is not None else '.env'})"
    )
    
    try:
        top_url, front_url = _resolve_camera_sources(request, settings)
    except ValueError as e:
        logger.error(f"[CAMERA] КРИТИЧЕСКАЯ ОШИБКА разрешения источников: {e}")
        raise
    
    interval_top = request.top_interval_sec or request.interval_sec

    try:
        logger.info(f"[CAMERA] Инициализация DataCollector...")
        # Используем значения из запроса, если указаны, иначе из настроек .env
        collector = DataCollector(
            uid=request.uid,
            connection_class=request.connection_class,
            ip1=top_url,
            ip2=front_url,
            data_root=request.data_root or settings.data_root,
            show_preview=request.show_preview if request.show_preview is not None else settings.hikvision_preview,
            crop_top=request.crop_top if request.crop_top is not None else settings.hikvision_crop_top,
            crop_bottom=request.crop_bottom if request.crop_bottom is not None else settings.hikvision_crop_bottom,
            crop_left=request.crop_left if request.crop_left is not None else settings.hikvision_crop_left,
            crop_right=request.crop_right if request.crop_right is not None else settings.hikvision_crop_right,
            jpeg_quality=request.jpeg_quality if request.jpeg_quality is not None else settings.hikvision_jpeg_quality,
            archive_after_capture=request.archive_after_capture if request.archive_after_capture is not None else settings.hikvision_archive_after_capture,
            archive_remove_originals=request.archive_remove_originals if request.archive_remove_originals is not None else settings.hikvision_archive_remove_originals,
        )
        logger.info(f"[CAMERA] ✓ DataCollector инициализирован")
    except Exception as e:
        error_msg = (
            f"[CAMERA] ОШИБКА инициализации DataCollector: {e}. "
            f"Проверьте параметры запроса и настройки."
        )
        logger.error(error_msg, exc_info=True)
        raise RuntimeError(error_msg) from e

    try:
        logger.info(
            f"[CAMERA] Запуск захвата: front={request.front_count} кадров, "
            f"top={request.top_count} кадров..."
        )
        results = collector.capture(
            front_count=request.front_count,
            front_interval_sec=request.interval_sec,
            top_count=request.top_count,
            top_interval_sec=interval_top,
        )
        
        logger.info(
            f"[CAMERA] ✓ Захват завершен:\n"
            f"  Front: {results['front_saved']}/{request.front_count} кадров сохранено "
            f"в {results['front_dir']}\n"
            f"  Top: {results['top_saved']}/{request.top_count} кадров сохранено "
            f"в {results['top_dir']}\n"
            f"  Ошибки: {len(results.get('errors', []))}"
        )
        
        if results.get('errors'):
            logger.warning(
                f"[CAMERA] Предупреждения при захвате:\n" + 
                "\n".join(f"  - {err}" for err in results['errors'])
            )
        
        if results.get('front_archive'):
            logger.info(f"[CAMERA] Front архив создан: {results['front_archive']}")
        if results.get('top_archive'):
            logger.info(f"[CAMERA] Top архив создан: {results['top_archive']}")
        
        return CaptureResponse(**results)
        
    except Exception as e:
        error_msg = (
            f"[CAMERA] КРИТИЧЕСКАЯ ОШИБКА при захвате изображений для UID={request.uid}: {e}. "
            f"Проверьте:\n"
            f"  - Доступность камер по сети\n"
            f"  - Правильность RTSP URL\n"
            f"  - Учетные данные для доступа к камерам\n"
            f"  - Достаточно ли места на диске для сохранения"
        )
        logger.error(error_msg, exc_info=True)
        raise RuntimeError(error_msg) from e


def test_cameras(cameras: Iterable[CameraTarget]) -> List[CameraTestResult]:
    """
    Тестирует доступность камер.
    
    Args:
        cameras: Итерируемый объект с CameraTarget для тестирования
    
    Returns:
        Список CameraTestResult с результатами тестирования каждой камеры
    """
    cameras_list = list(cameras)
    logger.info(f"[CAMERA] Тестирование {len(cameras_list)} камер...")
    
    results: List[CameraTestResult] = []
    
    for i, cam in enumerate(cameras_list, 1):
        label = cam.label or cam.url
        logger.debug(f"[CAMERA] [{i}/{len(cameras_list)}] Тестирование камеры: {label} ({cam.url})")
        
        try:
            reachable = test_ip_camera(cam.url, label=label)
            
            if reachable:
                message = "OK - камера доступна"
                logger.info(f"[CAMERA] ✓ [{i}/{len(cameras_list)}] {label}: {message}")
            else:
                message = (
                    f"FAILED - камера недоступна. Проверьте:\n"
                    f"  - Доступность по сети (ping)\n"
                    f"  - Правильность URL\n"
                    f"  - Работает ли RTSP сервер на камере\n"
                    f"  - Настройки firewall"
                )
                logger.error(f"[CAMERA] ✗ [{i}/{len(cameras_list)}] {label}: {message}")
            
            results.append(
                CameraTestResult(
                    label=cam.label,
                    url=cam.url,
                    reachable=reachable,
                    message=message,
                )
            )
        except Exception as e:
            error_msg = f"ОШИБКА при тестировании: {e}"
            logger.error(
                f"[CAMERA] ✗ [{i}/{len(cameras_list)}] {label}: {error_msg}",
                exc_info=True
            )
            results.append(
                CameraTestResult(
                    label=cam.label,
                    url=cam.url,
                    reachable=False,
                    message=error_msg,
                )
            )
    
    successful = sum(1 for r in results if r.reachable)
    logger.info(
        f"[CAMERA] Тестирование завершено: {successful}/{len(results)} камер доступны"
    )
    
    return results




