"""
Тесты для modbus_poller.py
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timezone

from app.config import get_settings
from app.services.modbus_poller import ModbusPoller
from app.schemas import ModbusValue


@pytest.fixture
def settings():
    """Получает настройки из .env файла."""
    return get_settings()


@pytest.fixture
def poller(settings):
    """Создает экземпляр ModbusPoller для тестов."""
    return ModbusPoller(settings)


class TestModbusPoller:
    """Тесты для класса ModbusPoller."""
    
    def test_poller_initialization(self, poller):
        """Тест инициализации поллера."""
        assert poller._running is False
        assert poller._detection_mode is True
        assert poller._current_rail_grid is None
        assert poller._baseline_values is None
    
    @pytest.mark.asyncio
    async def test_start_stop(self, poller):
        """Тест запуска и остановки поллера."""
        # Запуск
        await poller.start()
        assert poller._running is True
        
        # Остановка
        await poller.stop()
        assert poller._running is False
    
    def test_get_status(self, poller):
        """Тест получения статуса."""
        status = poller.get_status()
        
        assert "running" in status
        assert "detection_mode" in status
        assert "current_rail_grid_uuid" in status
        assert "baseline_established" in status
        assert "interval_sec" in status
        assert "poll_count" in status
    
    def test_extract_numeric_values(self, poller):
        """Тест извлечения числовых значений."""
        values = [
            ModbusValue(name="int1", address=1, raw_registers=[100], value=100),
            ModbusValue(name="float1", address=2, raw_registers=[], value=3.14),
            ModbusValue(name="str1", address=3, raw_registers=[], value="error"),
        ]
        
        numeric = poller._extract_numeric_values(values)
        
        assert len(numeric) == 2
        assert 100 in numeric
        assert 3.14 in numeric
    
    def test_values_differ(self, poller):
        """Тест сравнения значений."""
        values1 = (1.0, 2.0, 3.0)
        values2 = (1.0, 2.0, 3.0)
        values3 = (1.0, 2.5, 3.0)  # Отличается на 0.5
        
        assert not poller._values_differ(values1, values2, threshold=0.1)
        assert poller._values_differ(values1, values3, threshold=0.1)
        assert not poller._values_differ(values1, values3, threshold=1.0)  # Больший порог
    
    def test_all_values_similar(self, poller):
        """Тест проверки схожести всех значений."""
        from collections import deque
        
        similar_samples = deque([(1.0, 2.0), (1.0, 2.0), (1.0, 2.0)], maxlen=5)
        different_samples = deque([(1.0, 2.0), (1.0, 2.5), (1.0, 2.0)], maxlen=5)
        
        assert poller._all_values_similar(similar_samples)
        assert not poller._all_values_similar(different_samples, threshold=0.1)

