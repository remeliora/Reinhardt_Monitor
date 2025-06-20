import asyncio
import logging
import re
from typing import Dict, List, Optional

from core.model import Device, Parameter
from infrastructure.db.postgres import PostgresDB
from infrastructure.db.repositories import (
    DeviceRepository,
    ParameterRepository,
    DeviceTypeRepository
)


class PollingService:
    def __init__(self, db: PostgresDB, interval: int = 15):
        """
        Инициализация сервиса опроса с поддержкой параметров устройств
        :param db: Объект для работы с базой данных
        :param interval: Интервал между опросами в секундах
        """
        self.db = db
        self.interval = interval
        self.device_repo = DeviceRepository(db.get_session())
        self.device_type_repo = DeviceTypeRepository(db.get_session())
        self.parameter_repo = ParameterRepository(db.get_session())
        self.logger = logging.getLogger("PollingService")

        # Кэш для хранения параметров по типам устройств
        self.device_parameters_cache: Dict[int, List[Parameter]] = {}

        # Кэш для хранения последних значений параметров
        self.last_values_cache: Dict[int, Dict[int, float]] = {}

    async def get_device_parameters(self, device: Device) -> List[Parameter]:
        """Получение параметров устройства через его тип с использованием кэша"""
        if not device.device_type_id:
            self.logger.warning(f"Устройство {device.name} не имеет назначенного типа")
            return []

        # Проверяем кэш
        if device.device_type_id in self.device_parameters_cache:
            return self.device_parameters_cache[device.device_type_id]

        # Получаем параметры для типа устройства
        parameters = self.parameter_repo.get_parameters_by_device_type(device.device_type_id)

        # Кэшируем результат
        self.device_parameters_cache[device.device_type_id] = parameters

        self.logger.info(f"Загружено {len(parameters)} параметров для {device.name}")
        return parameters

    async def extract_parameter_value(self, frame: str, parameter: Parameter) -> Optional[float]:
        """Извлечение значения параметра из фрейма данных"""
        try:
            # Создаем шаблон для поиска значения параметра
            pattern = re.compile(
                fr"{re.escape(parameter.command)}\s*([+-]?\d+\.\d+)"
            )

            match = pattern.search(frame)
            if not match:
                return None

            return float(match.group(1))
        except Exception as e:
            self.logger.error(f"Ошибка извлечения параметра {parameter.name}: {e}")
            return None

    async def check_thresholds(self, device: Device, parameter: Parameter, value: float):
        """Проверка выхода значений за пороговые пределы"""
        try:
            thresholds = device.thresholds
            if not thresholds:
                return

            for threshold in thresholds:
                if threshold.parameter_id == parameter.id and threshold.is_enable:
                    if threshold.low_value is not None and value < threshold.low_value:
                        self.logger.warning(
                            f"ПРЕДУПРЕЖДЕНИЕ: {device.name} {parameter.name} "
                            f"({value}) ниже минимального порога ({threshold.low_value})"
                        )
                    if threshold.high_value is not None and value > threshold.high_value:
                        self.logger.warning(
                            f"ПРЕДУПРЕЖДЕНИЕ: {device.name} {parameter.name} "
                            f"({value}) выше максимального порога ({threshold.high_value})"
                        )
        except Exception as e:
            self.logger.error(f"Ошибка проверки порогов для {parameter.name}: {e}")

    async def process_parameter(self, frame: str, device: Device, parameter: Parameter):
        """Асинхронная задача для обработки одного параметра"""
        value = await self.extract_parameter_value(frame, parameter)
        if value is None:
            self.logger.debug(f"Параметр {parameter.name} не найден в данных")
            return

        # Проверяем и обновляем кэш последних значений
        if device.id not in self.last_values_cache:
            self.last_values_cache[device.id] = {}

        last_value = self.last_values_cache[device.id].get(parameter.id)
        if last_value == value:
            return  # Пропускаем если значение не изменилось

        self.last_values_cache[device.id][parameter.id] = value

        # Логируем полученное значение
        self.logger.info(
            f"{device.name} | {parameter.name}: {value} {parameter.metric or ''}"
        )

        # Проверяем пороговые значения
        await self.check_thresholds(device, parameter, value)

    def process_frame(self, frame: str, device: Device, parameters: List[Parameter]):
        """Обработка одного фрейма данных с запуском задач для параметров"""
        self.logger.debug(f"Raw frame from {device.name}: {frame}")

        # Создаем задачи для обработки каждого параметра
        tasks = []
        for param in parameters:
            task = asyncio.create_task(
                self.process_parameter(frame, device, param)
            )
            tasks.append(task)

        return tasks

    async def listen_device(self, device: Device):
        """Слушаем устройство и обрабатываем данные"""
        ip = device.ip_address
        port = device.port
        parameters = await self.get_device_parameters(device)

        if not parameters:
            self.logger.warning(f"Для устройства {device.name} не найдены параметры")
            return

        try:
            reader, writer = await asyncio.open_connection(ip, port)
            buffer = bytearray()
            self.logger.info(f"Слушаем {device.name} ({ip}:{port})")

            while True:
                try:
                    chunk = await reader.read(1024)
                    if not chunk:
                        raise ConnectionError("Соединение закрыто")

                    buffer.extend(chunk)

                    # Обработка буфера данных
                    while b"\r\n" in buffer:
                        end_pos = buffer.index(b"\r\n")
                        frame_str = buffer[:end_pos].decode('latin1').strip()
                        del buffer[:end_pos + 2]

                        if frame_str:
                            tasks = self.process_frame(frame_str, device, parameters)
                            await asyncio.gather(*tasks)

                except (asyncio.TimeoutError, ConnectionError) as e:
                    self.logger.error(f"Ошибка чтения: {e}")
                    break

                except Exception as e:
                    self.logger.exception(f"Неожиданная ошибка: {e}")
                    await asyncio.sleep(1)

        except Exception as e:
            self.logger.error(f"Ошибка подключения: {e}")
        finally:
            if 'writer' in locals():
                writer.close()
                await writer.wait_closed()
            self.logger.info(f"Остановлено прослушивание {device.name}")

    async def check_device_connection(self, ip: str, port: int) -> bool:
        """Проверка подключения к устройству"""
        try:
            reader, writer = await asyncio.open_connection(ip, port)
            writer.close()
            await writer.wait_closed()
            return True
        except Exception as e:
            self.logger.error(f"Ошибка подключения к {ip}:{port}: {e}")
            return False

    async def poll_device(self, device: Device):
        """Задача для опроса одного устройства"""
        if await self.check_device_connection(device.ip_address, device.port):
            await self.listen_device(device)
        else:
            self.logger.warning(f"{device.name} недоступно!")

    async def get_enabled_devices(self):
        """Получение списка активных устройств"""
        try:
            devices = self.device_repo.get_devices_by_is_enable_true()
            self.logger.info(f"Найдено {len(devices)} активных устройств")

            tasks = [self.poll_device(device) for device in devices]
            await asyncio.gather(*tasks)

        except Exception as e:
            self.logger.error(f"Ошибка получения устройств: {e}")

    async def start_polling(self):
        """Запуск периодического опроса"""
        while True:
            await self.get_enabled_devices()
            await asyncio.sleep(self.interval)
