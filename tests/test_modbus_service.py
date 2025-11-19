"""
Тесты для modbus_service.py
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException

from app.config import get_settings
from app.services.modbus_service import read_modbus, DEFAULT_VARIABLES
from app.schemas import ModbusVariableConfig


@pytest.fixture
def settings():
    """Получает настройки из .env файла."""
    return get_settings()


@pytest.fixture
def mock_client():
    """Создает мок Modbus клиента."""
    client = Mock(spec=ModbusTcpClient)
    client.connect.return_value = True
    return client


class TestReadModbus:
    """Тесты для функции read_modbus."""
    
    @patch('app.services.modbus_service.ModbusTcpClient')
    def test_read_modbus_success(self, mock_client_class, settings):
        """Тест успешного чтения Modbus."""
        # Настройка мока
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.connect.return_value = True
        
        # Мок ответа для каждой переменной
        mock_response = Mock()
        mock_response.isError.return_value = False
        mock_response.registers = [100, 200]  # Для float_swapped нужны 2 регистра
        mock_client.read_holding_registers.return_value = mock_response
        
        # Вызов функции
        result = read_modbus(settings, None)
        
        # Проверки
        assert len(result) == len(DEFAULT_VARIABLES)
        assert mock_client.connect.called
        assert mock_client.close.called
        
        # Проверяем, что для каждой переменной был вызов чтения
        assert mock_client.read_holding_registers.call_count == len(DEFAULT_VARIABLES)
    
    @patch('app.services.modbus_service.ModbusTcpClient')
    def test_read_modbus_connection_failed(self, mock_client_class, settings):
        """Тест ошибки подключения к Modbus."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.connect.return_value = False
        
        # Должно выбросить RuntimeError
        with pytest.raises(RuntimeError) as exc_info:
            read_modbus(settings, None)
        
        assert "ОШИБКА ПОДКЛЮЧЕНИЯ" in str(exc_info.value)
        assert settings.modbus_ip in str(exc_info.value)
        assert mock_client.close.called
    
    @patch('app.services.modbus_service.ModbusTcpClient')
    def test_read_modbus_read_error(self, mock_client_class, settings):
        """Тест ошибки чтения регистра."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.connect.return_value = True
        
        # Мок ответа с ошибкой
        mock_response = Mock()
        mock_response.isError.return_value = True
        mock_response.__str__ = Mock(return_value="Modbus Error")
        mock_client.read_holding_registers.return_value = mock_response
        
        # Вызов функции
        result = read_modbus(settings, None)
        
        # Проверки - должны быть значения с ошибками
        assert len(result) == len(DEFAULT_VARIABLES)
        # Проверяем, что есть ошибки в значениях
        error_values = [v for v in result if "Error" in str(v.value)]
        assert len(error_values) == len(DEFAULT_VARIABLES)
    
    @patch('app.services.modbus_service.ModbusTcpClient')
    def test_read_modbus_custom_variables(self, mock_client_class, settings):
        """Тест чтения с пользовательскими переменными."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.connect.return_value = True
        
        mock_response = Mock()
        mock_response.isError.return_value = False
        mock_response.registers = [42]
        mock_client.read_holding_registers.return_value = mock_response
        
        custom_vars = [
            ModbusVariableConfig(name="test_var", address=10, count=1, value_type="int")
        ]
        
        result = read_modbus(settings, custom_vars)
        
        assert len(result) == 1
        assert result[0].name == "test_var"
        assert result[0].address == 10
    
    @patch('app.services.modbus_service.ModbusTcpClient')
    def test_read_modbus_exception_handling(self, mock_client_class, settings):
        """Тест обработки исключений при чтении."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.connect.return_value = True
        mock_client.read_holding_registers.side_effect = ModbusException("Test error")
        
        result = read_modbus(settings, None)
        
        # Должны быть значения с ошибками
        assert len(result) == len(DEFAULT_VARIABLES)
        error_values = [v for v in result if "ModbusException" in str(v.value)]
        assert len(error_values) == len(DEFAULT_VARIABLES)


class TestModbusValueDecoding:
    """Тесты для декодирования значений Modbus."""
    
    @patch('app.services.modbus_service.ModbusTcpClient')
    def test_int_value_decoding(self, mock_client_class, settings):
        """Тест декодирования int значения."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.connect.return_value = True
        
        mock_response = Mock()
        mock_response.isError.return_value = False
        mock_response.registers = [12345]
        mock_client.read_holding_registers.return_value = mock_response
        
        custom_vars = [
            ModbusVariableConfig(name="int_var", address=1, count=1, value_type="int")
        ]
        
        result = read_modbus(settings, custom_vars)
        
        assert result[0].value == 12345
        assert isinstance(result[0].value, int)

