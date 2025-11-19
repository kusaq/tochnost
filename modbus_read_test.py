from pymodbus.client import ModbusTcpClient
import time
import struct

IP = "192.168.1.106"
PORT = 502
UNIT_ID = 1

# Переменные: (количество, внутр. регистр, тип)
# type: 'int' | 'float_swapped' (float32, big-endian bytes, но слова в порядке low-word, high-word)
VARIABLES = [
    (1, 1, 'int'),
    (1, 2, 'int'),
    (1, 3, 'int'),
    (1, 4, 'int'),
    (2, 5, 'float_swapped'),  # из 2 регистров, порядок как на скриншоте (младший регистр вперёд)
]

def regs_to_float_swapped_words(regs):
    """
    Декодирует два регистра Modbus в float32 при настройке:
    - Старшим байтом вперёд (внутри регистра) — big-endian bytes
    - Младший регистр вперёд (слова поменяны местами) — low-word first
    """
    if len(regs) != 2:
        return None
    # Поменять местами слова: (low-word, high-word) -> (high-word, low-word)
    packed = struct.pack('>HH', regs[1], regs[0])
    return struct.unpack('>f', packed)[0]

def main():
    client = ModbusTcpClient(IP, port=PORT)
    try:
        client.connect()
        print("Нажмите Ctrl+C (или abort), чтобы остановить.")
        while True:
            readings = []
            for count, address, vtype in VARIABLES:
                result = client.read_holding_registers(address, count, unit=UNIT_ID)
                if not result.isError():
                    if vtype == 'int' and count == 1:
                        display_value = str(result.registers[0])
                    elif vtype == 'float_swapped' and count == 2:
                        raw = result.registers
                        flt = regs_to_float_swapped_words(raw)
                        display_value = f"{raw} -> {flt}"
                    else:
                        display_value = str(result.registers)
                    readings.append((address, display_value))
                else:
                    readings.append((address, f"Ошибка: {result}"))
            ts = time.strftime('%H:%M:%S')
            line = " | ".join([f"R{addr}={val}" for addr, val in readings])
            print(f"[{ts}] {line}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nОстановка по Ctrl+C/abort. Программа завершена.")
    except Exception as e:
        print(f"Ошибка: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    main()
