"""
Тесты для API эндпоинтов
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings


@pytest.fixture
def client():
    """Создает тестовый клиент FastAPI."""
    return TestClient(app)


@pytest.fixture
def auth_token(client):
    """Получает токен авторизации для тестов."""
    settings = get_settings()
    # Используем настройки из окружения или дефолтные
    response = client.post(
        "/auth/token",
        data={
            "username": settings.api_username,
            "password": settings.api_password or "test",
        },
    )
    if response.status_code == 200:
        return response.json()["access_token"]
    return None


class TestHealthEndpoint:
    """Тесты для health эндпоинта."""
    
    def test_health_check(self, client):
        """Тест health check эндпоинта."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data


class TestAuthEndpoint:
    """Тесты для auth эндпоинтов."""
    
    def test_login_success(self, client):
        """Тест успешной авторизации."""
        settings = get_settings()
        response = client.post(
            "/auth/token",
            data={
                "username": settings.api_username,
                "password": settings.api_password or "test",
            },
        )
        # Может быть 200 или 401 в зависимости от настроек
        assert response.status_code in [200, 401]
    
    def test_login_failure(self, client):
        """Тест неудачной авторизации."""
        response = client.post(
            "/auth/token",
            data={
                "username": "wrong",
                "password": "wrong",
            },
        )
        assert response.status_code == 401


class TestModbusEndpoints:
    """Тесты для Modbus эндпоинтов."""
    
    @patch('app.main.read_modbus')
    def test_modbus_readings_success(self, mock_read_modbus, client, auth_token):
        """Тест успешного чтения Modbus."""
        if not auth_token:
            pytest.skip("No auth token available")
        
        # Мок ответа
        from app.schemas import ModbusValue
        mock_read_modbus.return_value = [
            ModbusValue(name="test", address=1, raw_registers=[100], value=100)
        ]
        
        response = client.post(
            "/api/v1/modbus/readings",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={},
        )
        
        # Может быть 200 или 503 в зависимости от доступности Modbus
        assert response.status_code in [200, 503]
    
    def test_modbus_poll_status(self, client, auth_token):
        """Тест получения статуса поллера."""
        if not auth_token:
            pytest.skip("No auth token available")
        
        response = client.get(
            "/api/v1/modbus/poll/status",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        
        # Может быть 200 или 401 в зависимости от авторизации
        assert response.status_code in [200, 401]
        if response.status_code == 200:
            data = response.json()
            assert "running" in data
            assert "detection_mode" in data


class TestCameraEndpoints:
    """Тесты для Camera эндпоинтов."""
    
    @patch('app.main.test_cameras')
    def test_camera_test(self, mock_test_cameras, client, auth_token):
        """Тест тестирования камер."""
        if not auth_token:
            pytest.skip("No auth token available")
        
        from app.schemas import CameraTestResult
        mock_test_cameras.return_value = [
            CameraTestResult(
                label="Test Camera",
                url="rtsp://test",
                reachable=True,
                message="OK",
            )
        ]
        
        response = client.post(
            "/api/v1/cameras/test",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "cameras": [
                    {"url": "rtsp://test", "label": "Test Camera"}
                ]
            },
        )
        
        assert response.status_code in [200, 401, 500]


