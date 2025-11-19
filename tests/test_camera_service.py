"""
Тесты для camera_service.py
"""
import pytest
from unittest.mock import Mock, patch, MagicMock

from app.config import get_settings
from app.services.camera_service import (
    _resolve_camera_sources,
    capture_with_cameras,
    test_cameras,
)
from app.schemas import CaptureRequest, CameraTarget


@pytest.fixture
def settings():
    """Получает настройки из .env файла."""
    return get_settings()


class TestResolveCameraSources:
    """Тесты для функции _resolve_camera_sources."""
    
    @patch('app.services.camera_service.build_rtsp_url')
    def test_resolve_default_cameras(self, mock_build_url, settings):
        """Тест разрешения камер по умолчанию."""
        # Используем реальные значения из .env для построения URL
        top_url_expected = (
            f"rtsp://{settings.hikvision_user}:{settings.hikvision_pass}@"
            f"{settings.hikvision_top_ip}:{settings.hikvision_rtsp_port}/"
            f"Streaming/Channels/{settings.hikvision_top_channel}"
        )
        front_url_expected = (
            f"rtsp://{settings.hikvision_user}:{settings.hikvision_pass}@"
            f"{settings.hikvision_front_ip}:{settings.hikvision_rtsp_port}/"
            f"Streaming/Channels/{settings.hikvision_front_channel}"
        )
        mock_build_url.side_effect = [top_url_expected, front_url_expected]
        
        request = CaptureRequest(
            uid="test-uid",
            connection_class="test-class",
            use_default_cameras=True,
        )
        
        top_url, front_url = _resolve_camera_sources(request, settings)
        
        assert top_url.startswith("rtsp://")
        assert front_url.startswith("rtsp://")
        assert mock_build_url.call_count == 2
    
    def test_resolve_custom_cameras(self, settings):
        """Тест разрешения пользовательских камер."""
        request = CaptureRequest(
            uid="test-uid",
            connection_class="test-class",
            use_default_cameras=False,
            top_camera_url="rtsp://custom-top",
            front_camera_url="rtsp://custom-front",
        )
        
        top_url, front_url = _resolve_camera_sources(request, settings)
        
        assert top_url == "rtsp://custom-top"
        assert front_url == "rtsp://custom-front"
    
    def test_resolve_cameras_missing_urls(self, settings):
        """Тест ошибки при отсутствии URL камер."""
        request = CaptureRequest(
            uid="test-uid",
            connection_class="test-class",
            use_default_cameras=False,
            top_camera_url="",
            front_camera_url="",
        )
        
        with pytest.raises(ValueError) as exc_info:
            _resolve_camera_sources(request, settings)
        
        assert "ОШИБКА" in str(exc_info.value)


class TestTestCameras:
    """Тесты для функции test_cameras."""
    
    @patch('app.services.camera_service.test_ip_camera')
    def test_test_cameras_success(self, mock_test_ip):
        """Тест успешного тестирования камер."""
        mock_test_ip.return_value = True
        
        cameras = [
            CameraTarget(url="rtsp://test1", label="Camera 1"),
            CameraTarget(url="rtsp://test2", label="Camera 2"),
        ]
        
        results = test_cameras(cameras)
        
        assert len(results) == 2
        assert all(r.reachable for r in results)
        assert mock_test_ip.call_count == 2
    
    @patch('app.services.camera_service.test_ip_camera')
    def test_test_cameras_failure(self, mock_test_ip):
        """Тест неудачного тестирования камер."""
        mock_test_ip.return_value = False
        
        cameras = [CameraTarget(url="rtsp://test", label="Camera")]
        
        results = test_cameras(cameras)
        
        assert len(results) == 1
        assert not results[0].reachable
        assert "FAILED" in results[0].message
    
    @patch('app.services.camera_service.test_ip_camera')
    def test_test_cameras_exception(self, mock_test_ip):
        """Тест обработки исключений при тестировании."""
        mock_test_ip.side_effect = Exception("Connection error")
        
        cameras = [CameraTarget(url="rtsp://test", label="Camera")]
        
        results = test_cameras(cameras)
        
        assert len(results) == 1
        assert not results[0].reachable
        assert "ОШИБКА" in results[0].message


class TestCaptureWithCameras:
    """Тесты для функции capture_with_cameras."""
    
    @patch('app.services.camera_service.DataCollector')
    @patch('app.services.camera_service._resolve_camera_sources')
    def test_capture_success(self, mock_resolve, mock_collector_class, settings):
        """Тест успешного захвата изображений."""
        mock_resolve.return_value = ("rtsp://top", "rtsp://front")
        
        mock_collector = Mock()
        mock_collector.capture.return_value = {
            "front_saved": 3,
            "top_saved": 1,
            "front_dir": "/test/front",
            "top_dir": "/test/top",
            "errors": [],
        }
        mock_collector_class.return_value = mock_collector
        
        request = CaptureRequest(
            uid="test-uid",
            connection_class="test-class",
            use_default_cameras=True,
            front_count=3,
            top_count=1,
        )
        
        result = capture_with_cameras(request, settings)
        
        assert result.front_saved == 3
        assert result.top_saved == 1
        assert mock_collector.capture.called
    
    @patch('app.services.camera_service._resolve_camera_sources')
    def test_capture_resolve_error(self, mock_resolve, settings):
        """Тест ошибки разрешения источников камер."""
        mock_resolve.side_effect = ValueError("Camera URL error")
        
        request = CaptureRequest(
            uid="test-uid",
            connection_class="test-class",
            use_default_cameras=True,
        )
        
        with pytest.raises(ValueError):
            capture_with_cameras(request, settings)

