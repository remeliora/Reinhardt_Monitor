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

        if device.device_type_id in self.device_parameters_cache:
            return self.device_parameters_cache[device.device_type_id]

        parameters = self.parameter_repo.get_parameters_by_device_type(device.device_type_id)
        self.device_parameters_cache[device.device_type_id] = parameters
        self.logger.info(f"Загружено {len(parameters)} параметров для {device.name}")
        return parameters

    async def extract_parameter_value(self, frame: str, parameter: Parameter) -> Optional[float]:
        """Извлечение значения параметра из фрейма данных"""
        try:
            pattern = re.compile(fr"{re.escape(parameter.command)}\s*([+-]?\d+\.\d+)")
            match = pattern.search(frame)
            if not match:
                return None

            value = float(match.group(1))

            # Специальная обработка для параметра DR
            if parameter.command == 'DR':
                value = value / 10
                self.logger.debug(f"Применено деление на 10 для параметра DR: {value}")

            return value
        except Exception as e:
            self.logger.error(f"Ошибка извлечения параметра {parameter.name}: {e}")
            return None

    async def check_thresholds(self, device: Device, parameter: Parameter, value: float):
        """Проверка выхода значений за пороговые пределы"""
        try:
            for threshold in device.thresholds:
                if threshold.parameter_id == parameter.id and threshold.is_enable:
                    # Для параметра DR пороги также должны быть поделены на 10
                    threshold_value = threshold.low_value if parameter.command == 'DR' else threshold.low_value
                    if threshold_value is not None and value < threshold_value:
                        self.logger.warning(
                            f"ПРЕДУПРЕЖДЕНИЕ: {device.name} {parameter.name} "
                            f"({value}) ниже минимального порога ({threshold_value})"
                        )

                    threshold_value = threshold.high_value if parameter.command == 'DR' else threshold.high_value
                    if threshold_value is not None and value > threshold_value:
                        self.logger.warning(
                            f"ПРЕДУПРЕЖДЕНИЕ: {device.name} {parameter.name} "
                            f"({value}) выше максимального порога ({threshold_value})"
                        )
        except Exception as e:
            self.logger.error(f"Ошибка проверки порогов для {parameter.name}: {e}")

    async def process_device_data(self, device: Device):
        """Получение и обработка данных от устройства с немедленным закрытием соединения"""
        ip = device.ip_address
        port = device.port
        parameters = await self.get_device_parameters(device)

        if not parameters:
            self.logger.warning(f"Для устройства {device.name} не найдены параметры")
            return

        try:
            # Устанавливаем соединение
            reader, writer = await asyncio.open_connection(ip, port)
            self.logger.debug(f"Подключено к {device.name} ({ip}:{port})")

            try:
                # Читаем данные с таймаутом
                data = await asyncio.wait_for(reader.readuntil(b'\r\n'), timeout=5.0)
                frame_str = data.decode('latin1').strip()
                self.logger.debug(f"Получены данные от {device.name}: {frame_str}")

                # Обрабатываем параметры
                tasks = []
                for param in parameters:
                    tasks.append(
                        self.process_parameter(frame_str, device, param)
                    )
                await asyncio.gather(*tasks)

            except asyncio.TimeoutError:
                self.logger.warning(f"Таймаут ожидания данных от {device.name}")
            except Exception as e:
                self.logger.error(f"Ошибка чтения данных от {device.name}: {e}")
            finally:
                # Всегда закрываем соединение
                writer.close()
                await writer.wait_closed()

        except Exception as e:
            self.logger.error(f"Ошибка подключения к {device.name}: {e}")

    async def process_parameter(self, frame: str, device: Device, parameter: Parameter):
        """Обработка одного параметра"""
        value = await self.extract_parameter_value(frame, parameter)
        if value is None:
            return

        # Обновляем кэш и проверяем изменение значения
        if device.id not in self.last_values_cache:
            self.last_values_cache[device.id] = {}

        if self.last_values_cache[device.id].get(parameter.id) != value:
            self.last_values_cache[device.id][parameter.id] = value

            # Форматируем значение для вывода
            formatted_value = f"{value:.1f}" if parameter.command == 'DR' else str(value)
            self.logger.info(
                f"{device.name} | {parameter.name}: {formatted_value} {parameter.metric or ''}"
            )
            await self.check_thresholds(device, parameter, value)

    async def poll_device(self, device: Device):
        """Периодический опрос одного устройства"""
        while True:
            try:
                await self.process_device_data(device)
            except Exception as e:
                self.logger.error(f"Ошибка при опросе {device.name}: {e}")

            await asyncio.sleep(self.interval)

    async def start_polling(self):
        """Запуск периодического опроса всех устройств"""
        try:
            devices = self.device_repo.get_devices_by_is_enable_true()
            self.logger.info(f"Найдено {len(devices)} активных устройств")

            tasks = [self.poll_device(device) for device in devices]
            await asyncio.gather(*tasks)

        except Exception as e:
            self.logger.error(f"Ошибка при запуске опроса: {e}")
            raise