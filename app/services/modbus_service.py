from __future__ import annotations

import logging
import struct
from typing import Iterable, List

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException

from app.config import Settings
from app.schemas import ModbusValue, ModbusVariableConfig

logger = logging.getLogger(__name__)


def _regs_to_float_swapped_words(regs: List[int]) -> float | None:
    if len(regs) != 2:
        return None
    packed = struct.pack(">HH", regs[1], regs[0])
    return struct.unpack(">f", packed)[0]


DEFAULT_VARIABLES = [
    ModbusVariableConfig(name="wrench_1", address=1, count=1, value_type="int"),
    ModbusVariableConfig(name="wrench_2", address=2, count=1, value_type="int"),
    ModbusVariableConfig(name="wrench_3", address=3, count=1, value_type="int"),
    ModbusVariableConfig(name="wrench_4", address=4, count=1, value_type="int"),
    ModbusVariableConfig(name="resistance", address=5, count=2, value_type="float_swapped"),
]


def _decode_value(variable: ModbusVariableConfig, registers: List[int]) -> int | float | str | None:
    if not registers:
        return None
    if variable.value_type == "int" and variable.count == 1:
        return registers[0]
    if variable.value_type == "float_swapped" and len(registers) == 2:
        value = _regs_to_float_swapped_words(registers)
        return value
    return str(registers)


def read_modbus(settings: Settings, variables: Iterable[ModbusVariableConfig] | None = None) -> List[ModbusValue]:
    """
    Читает значения из Modbus устройства.
    
    Args:
        settings: Настройки приложения с параметрами Modbus
        variables: Список переменных для чтения (если None, используются DEFAULT_VARIABLES)
    
    Returns:
        Список ModbusValue с прочитанными значениями
    
    Raises:
        RuntimeError: При ошибке подключения к Modbus устройству
        Exception: При других ошибках чтения
    """
    vars_to_read = list(variables) if variables else DEFAULT_VARIABLES
    
    logger.info(
        f"[MODBUS] Подключение к устройству: {settings.modbus_ip}:{settings.modbus_port} "
        f"(unit_id={settings.modbus_unit_id}, timeout={settings.modbus_timeout}s)"
    )
    logger.debug(f"[MODBUS] Чтение {len(vars_to_read)} переменных: {[v.name for v in vars_to_read]}")
    
    client = ModbusTcpClient(
        host=settings.modbus_ip,
        port=settings.modbus_port,
        timeout=settings.modbus_timeout,
    )
    
    try:
        logger.debug(f"[MODBUS] Попытка подключения к {settings.modbus_ip}:{settings.modbus_port}...")
        connected = client.connect()
        
        if not connected:
            error_msg = (
                f"[MODBUS] ОШИБКА ПОДКЛЮЧЕНИЯ: Не удалось подключиться к Modbus устройству "
                f"{settings.modbus_ip}:{settings.modbus_port}. "
                f"Проверьте:\n"
                f"  - Доступность устройства по сети (ping {settings.modbus_ip})\n"
                f"  - Правильность IP адреса и порта\n"
                f"  - Настройки firewall\n"
                f"  - Работает ли Modbus сервер на устройстве"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        logger.info(f"[MODBUS] ✓ Успешно подключено к {settings.modbus_ip}:{settings.modbus_port}")
        
        values: List[ModbusValue] = []
        errors_count = 0
        
        for var in vars_to_read:
            try:
                logger.debug(
                    f"[MODBUS] Чтение переменной '{var.name}' "
                    f"(address={var.address}, count={var.count}, type={var.value_type})"
                )
                
                response = client.read_holding_registers(
                    address=var.address,
                    count=var.count,
                    unit=settings.modbus_unit_id,
                )
                
                if response.isError():
                    error_msg = (
                        f"[MODBUS] ОШИБКА чтения '{var.name}' (address={var.address}): {response}"
                    )
                    logger.error(error_msg)
                    errors_count += 1
                    values.append(
                        ModbusValue(
                            name=var.name,
                            address=var.address,
                            raw_registers=[],
                            value=f"Error: {response}",
                        )
                    )
                    continue
                
                raw = list(response.registers)
                decoded = _decode_value(var, raw)
                
                logger.debug(
                    f"[MODBUS] ✓ '{var.name}': raw={raw}, decoded={decoded}"
                )
                
                values.append(
                    ModbusValue(
                        name=var.name,
                        address=var.address,
                        raw_registers=raw,
                        value=decoded,
                    )
                )
                
            except ModbusException as e:
                error_msg = (
                    f"[MODBUS] ОШИБКА Modbus при чтении '{var.name}' (address={var.address}): {e}"
                )
                logger.error(error_msg, exc_info=True)
                errors_count += 1
                values.append(
                    ModbusValue(
                        name=var.name,
                        address=var.address,
                        raw_registers=[],
                        value=f"ModbusException: {e}",
                    )
                )
            except Exception as e:
                error_msg = (
                    f"[MODBUS] НЕОЖИДАННАЯ ОШИБКА при чтении '{var.name}' (address={var.address}): {e}"
                )
                logger.error(error_msg, exc_info=True)
                errors_count += 1
                values.append(
                    ModbusValue(
                        name=var.name,
                        address=var.address,
                        raw_registers=[],
                        value=f"Exception: {e}",
                    )
                )
        
        if errors_count > 0:
            logger.warning(
                f"[MODBUS] Завершено с ошибками: {errors_count}/{len(vars_to_read)} переменных "
                f"не удалось прочитать"
            )
        else:
            logger.info(
                f"[MODBUS] ✓ Успешно прочитано {len(values)} переменных"
            )
        
        return values
        
    except RuntimeError:
        raise
    except Exception as e:
        error_msg = (
            f"[MODBUS] КРИТИЧЕСКАЯ ОШИБКА при работе с Modbus устройством "
            f"{settings.modbus_ip}:{settings.modbus_port}: {e}"
        )
        logger.error(error_msg, exc_info=True)
        raise RuntimeError(error_msg) from e
    finally:
        try:
            client.close()
            logger.debug(f"[MODBUS] Соединение закрыто")
        except Exception as e:
            logger.warning(f"[MODBUS] Ошибка при закрытии соединения: {e}")



