import asyncio
import logging
import re
from datetime import datetime

from infrastructure.db.postgres import PostgresDB
from infrastructure.db.repositories import DeviceRepository, ParameterRepository


class PollingService:
    def __init__(self, db: PostgresDB, interval: int = 15):
        """
        Инициализация сервиса опроса
        :param db: Объект для работы с базой данных
        :param interval: Интервал между опросами в секундах (по умолчанию 15 секунд)
        """
        self.db = db
        self.interval = interval
        self.device_repo = DeviceRepository(db.get_session())
        self.parameter_repo = ParameterRepository(db.get_session())
        self.logger = logging.getLogger("PollingService")

    async def check_device_connection(self, ip: str, port: int) -> bool:
        """Проверка подключения к устройству"""
        try:
            reader, writer = await asyncio.open_connection(ip, port)
            writer.close()  # Закрываем соединение
            await writer.wait_closed()
            return True
        except (asyncio.TimeoutError, ConnectionRefusedError, OSError) as e:
            self.logger.error(f"Ошибка подключения к устройству с IP: {ip}, Порт: {port}: {e}")
            return False

    async def listen_device(self, ip: str, port: int):
        """Слушаем устройство, получаем данные и выводим их"""
        try:
            reader, writer = await asyncio.open_connection(ip, port)
            buffer = bytearray()

            while True:
                try:
                    # Чтение данных из сокета
                    chunk = await reader.read(1024)
                    if not chunk:
                        raise ConnectionError("Connection closed by remote host")

                    buffer.extend(chunk)
                    self.process_buffer(buffer)

                except (asyncio.TimeoutError, ConnectionError) as e:
                    self.logger.error(f"Read error: {e}")
                    break  # Закрываем соединение, если ошибка

                except Exception as e:
                    self.logger.exception(f"Unexpected error: {e}")
                    await asyncio.sleep(1)

        except Exception as e:
            self.logger.error(f"Ошибка подключения или чтения с устройства: {e}")

    def process_buffer(self, buffer):
        """Обработка буфера данных с разделением на фреймы"""
        while b"\r\n" in buffer:
            end_pos = buffer.index(b"\r\n")
            frame = buffer[:end_pos].decode('latin1').strip()
            del buffer[:end_pos + 2]  # Удаляем обработанные данные

            if frame:
                self.process_frame(frame)

    def process_frame(self, frame):
        """Обработка одного фрейма данных"""
        self.logger.debug(f"Raw frame: {frame}")
        measurements = self.decode_data(frame)

        if measurements:
            self.print_measurements(measurements)
        else:
            self.logger.warning(f"Invalid frame format: {frame}")

    def decode_data(self, data):
        """Парсинг данных с использованием регулярных выражений"""
        pattern = re.compile(
            r'^\s*(\d{2}):(\d{2}):(\d{2})\s*,\s*'
            r'(\d{2})\.(\d{2})\.(\d{2})\s*,\s*'
            r'TE([+-]?\d+\.\d+)\s*,\s*'
            r'DR(\d+\.\d+)\s*,\s*'
            r'FE(\d+\.\d+)\s*,?$'
        )

        match = pattern.match(data)
        if not match:
            return None

        try:
            # Парсинг времени и даты
            hour, minute, second = map(int, match.groups()[:3])
            day, month, year2 = map(int, match.groups()[3:6])

            # Преобразование года (YY -> YYYY)
            year = 2000 + year2 if year2 < 50 else 1900 + year2

            # Парсинг измерений
            temperature = float(match.group(7))
            pressure = float(match.group(8))
            humidity = float(match.group(9))

            return {
                'datetime': datetime(year, month, day, hour, minute, second),
                'temperature': temperature,
                'pressure': pressure,
                'humidity': humidity
            }

        except (ValueError, TypeError) as e:
            self.logger.error(f"Parsing error: {e}")
            return None

    def print_measurements(self, data):
        """Вывод полученных измерений"""
        dt_str = data['datetime'].strftime("%d.%m.%Y %H:%M:%S")
        print("\n" + "=" * 40)
        print(f"Time:        {dt_str}")
        print(f"Temperature: {data['temperature']} °C")
        print(f"Humidity:    {data['humidity']} %")
        print(f"Pressure:    {data['pressure']} gPa")
        print("=" * 40 + "\n")

    async def poll_device(self, device):
        """Задача для опроса одного устройства"""
        ip = device.ip_address
        port = device.port

        if await self.check_device_connection(ip, port):
            self.logger.info(f"Начинаем слушать устройство {device.name} (IP: {ip}, Порт: {port})")
            # Слушаем устройство и получаем данные
            await self.listen_device(ip, port)
        else:
            self.logger.info(f"{device.name} (IP: {ip}, Порт: {port}) соединение отсутствует!")

    async def get_enabled_devices(self):
        """Получение списка включённых устройств"""
        try:
            devices = self.device_repo.get_devices_by_is_enable_true()
            self.logger.info(f"Количество датчиков для опроса: {len(devices)}")

            # Создаём задачи для каждого устройства
            tasks = []
            for device in devices:
                tasks.append(self.poll_device(device))  # Добавляем задачу для каждого устройства

            # Ожидаем завершения всех задач
            await asyncio.gather(*tasks)

        except Exception as e:
            self.logger.error(f"Ошибка при запросе данных: {e}")

    async def start_polling(self):
        """Метод для запуска периодического опроса"""
        while True:
            await self.get_enabled_devices()  # Сбор информации о включённых устройствах
            await asyncio.sleep(self.interval)  # Ждём 15 секунд перед следующим опросом
