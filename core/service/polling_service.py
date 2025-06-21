import asyncio
import logging
import re
from typing import List, Optional

from core.model import Device, Parameter
from infrastructure.db.postgres import PostgresDB
from infrastructure.db.repositories import (
    DeviceRepository,
    ParameterRepository,
    DeviceTypeRepository
)


class PollingService:
    def __init__(self, db: PostgresDB, polling_interval: int = 15):
        self.db = db
        self.polling_interval = polling_interval
        self.device_repo = DeviceRepository(db.get_session())
        self.device_type_repo = DeviceTypeRepository(db.get_session())
        self.parameter_repo = ParameterRepository(db.get_session())
        self.logger = logging.getLogger("PollingService")
        self.active_tasks: List[asyncio.Task] = []

    async def get_active_devices(self) -> List[Device]:
        """Получение списка активных устройств из БД"""
        return self.device_repo.get_devices_by_is_enable_true()

    async def get_device_parameters(self, device: Device) -> List[Parameter]:
        """Получение параметров устройства из БД"""
        if not device.device_type_id:
            self.logger.warning(f"Устройство {device.name} не имеет назначенного типа")
            return []

        return self.parameter_repo.get_parameters_by_device_type(device.device_type_id)

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

    async def poll_device(self, device: Device):
        """Один цикл опроса устройства"""
        try:
            # Устанавливаем соединение
            reader, writer = await asyncio.open_connection(device.ip_address, device.port)
            self.logger.debug(f"Подключено к {device.name} ({device.ip_address}:{device.port})")

            try:
                # Читаем данные с таймаутом
                data = await asyncio.wait_for(reader.readuntil(b'\r\n'), timeout=5.0)
                frame_str = data.decode('latin1').strip()
                self.logger.debug(f"Получены данные от {device.name}: {frame_str}")

                # Получаем актуальные параметры из БД
                parameters = await self.get_device_parameters(device)

                # Обрабатываем каждый параметр
                for param in parameters:
                    value = await self.extract_parameter_value(frame_str, param)
                    if value is not None:
                        formatted_value = f"{value:.1f}" if param.command == 'DR' else str(value)
                        # self.logger.info(
                        #     f"{device.name} | {param.name}: {formatted_value} {param.metric or ''}"
                        # )
                        await self.check_thresholds(device, param, value)

            except asyncio.TimeoutError:
                self.logger.warning(f"Таймаут ожидания данных от {device.name}")
            except Exception as e:
                self.logger.error(f"Ошибка чтения данных от {device.name}: {e}")
            finally:
                writer.close()
                await writer.wait_closed()

        except Exception as e:
            self.logger.error(f"Ошибка подключения к {device.name}: {e}")

    async def poll_all_devices(self):
        """Один цикл опроса всех активных устройств"""
        devices = await self.get_active_devices()
        self.logger.debug(f"Начинаем опрос {len(devices)} устройств")

        tasks = []
        for device in devices:
            task = asyncio.create_task(self.poll_device(device))
            tasks.append(task)

        await asyncio.gather(*tasks)

    async def start_polling(self):
        """Запуск периодического опроса всех устройств"""
        try:
            while True:
                await self.poll_all_devices()
                await asyncio.sleep(self.polling_interval)
        except asyncio.CancelledError:
            self.logger.info("Остановка опроса...")
            # Дожидаемся завершения текущих задач
            await asyncio.gather(*self.active_tasks, return_exceptions=True)
            self.logger.info("Опрос остановлен")
        except Exception as e:
            self.logger.error(f"Критическая ошибка: {e}")
            raise