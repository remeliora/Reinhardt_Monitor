import asyncio
import json
import logging
import os
import re
from datetime import datetime
from typing import List, Optional, Dict, Any

from PySide6.QtCore import Signal, QObject

from core.model import Device, Parameter
from infrastructure.db.postgres import PostgresDB
from infrastructure.db.repositories import (
    DeviceRepository,
    ParameterRepository,
    DeviceTypeRepository
)


class PollingService(QObject):
    data_updated = Signal(str, dict, bool)  # Сигнал: имя устройства, данные, статус is_enable

    def __init__(self, db: PostgresDB, polling_interval: int = 15, output_dir: str = "device_data"):
        super().__init__()
        self.db = db
        self._polling_interval = polling_interval
        self.output_dir = output_dir
        self.device_repo = DeviceRepository(db.get_session())
        self.device_type_repo = DeviceTypeRepository(db.get_session())
        self.parameter_repo = ParameterRepository(db.get_session())
        self.logger = logging.getLogger("PollingService")
        self.active_tasks: List[asyncio.Task] = []
        self._is_running = False
        self._polling_task: Optional[asyncio.Task] = None
        self._polling_event: Optional[asyncio.Event] = None
        self._tasks_lock = asyncio.Lock()  # Для синхронизации доступа к active_tasks

        os.makedirs(self.output_dir, exist_ok=True)

    @property
    def polling_interval(self) -> int:
        """Получить текущий интервал опроса"""
        return self._polling_interval

    @polling_interval.setter
    def polling_interval(self, value: int):
        """Установить новый интервал опроса"""
        if value <= 0:
            raise ValueError("Интервал опроса должен быть положительным числом")
        self._polling_interval = value
        if self._polling_event:
            self._polling_event.set()

    async def get_all_devices_with_status(self) -> List[Device]:
        """Получение всех устройств с их статусом"""
        return self.device_repo.get_all_devices()

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

    async def save_device_data(self, device: Device, parameters_data: List[Dict[str, Any]]):
        """Сохранение данных устройства в JSON-файл"""
        try:
            filename = f"{self.output_dir}/{device.name.replace(' ', '_')}.json"
            data = {
                "device_name": device.name,
                "ip_address": device.ip_address,
                "port": device.port,
                "last_update": datetime.now().isoformat(),
                "parameters": parameters_data
            }

            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            self.logger.debug(f"Данные устройства {device.name} сохранены в {filename}")
        except Exception as e:
            self.logger.error(f"Ошибка сохранения данных устройства {device.name}: {e}")

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

                # Получаем параметры
                parameters = await self.get_device_parameters(device)
                parameters_data = {}

                for param in parameters:
                    value = await self.extract_parameter_value(frame_str, param)
                    if value is not None:
                        formatted_value = float(f"{value:.1f}") if param.command == 'DR' else value
                        parameters_data[param.name] = {
                            "value": formatted_value,
                            "metric": param.metric or ""
                        }
                        await self.check_thresholds(device, param, value)

                # Отправляем данные через сигнал
                self.data_updated.emit(device.name, parameters_data, True)
                await self.save_device_data(device, parameters_data)

            except asyncio.TimeoutError:
                self.logger.warning(f"Таймаут ожидания данных от {device.name}")
                self.data_updated.emit(device.name, {}, True)
            except asyncio.CancelledError:
                self.logger.debug(f"Опрос устройства {device.name} отменен")
                raise
            except Exception as e:
                self.logger.error(f"Ошибка при опросе устройства {device.name}: {e}")
                self.data_updated.emit(device.name, {"error": str(e)}, False)
            finally:
                writer.close()
                try:
                    await asyncio.wait_for(writer.wait_closed(), timeout=2.0)
                except asyncio.TimeoutError:
                    self.logger.warning(f"Таймаут при закрытии соединения с {device.name}")

        except Exception as e:
            self.logger.error(f"Ошибка подключения к {device.name}: {e}")
            self.data_updated.emit(device.name, {"error": str(e)}, False)

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

    async def poll_all_devices(self):
        """Один цикл опроса всех устройств с учетом их статуса"""
        try:
            devices = await self.get_all_devices_with_status()
            tasks = []

            for device in devices:
                if device.is_enable:
                    task = asyncio.create_task(self.poll_device(device))
                    tasks.append(task)
                    async with self._tasks_lock:
                        self.active_tasks.append(task)
                else:
                    self.data_updated.emit(device.name, {}, False)

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            self.logger.error(f"Ошибка при опросе устройств: {e}")
        finally:
            async with self._tasks_lock:
                self.active_tasks = []

    async def run(self):
        """Запуск периодического опроса всех устройств"""
        if self._is_running:
            self.logger.warning("Опрос уже запущен")
            return

        if self._polling_task is not None and not self._polling_task.done():
            self.logger.warning("Предыдущая задача опроса еще не завершена")
            return

        self._is_running = True
        self._polling_event = asyncio.Event()
        self._polling_event.clear()
        self._polling_task = asyncio.current_task()

        try:
            while self._is_running:
                start_time = datetime.now()
                await self.poll_all_devices()

                elapsed = (datetime.now() - start_time).total_seconds()
                sleep_time = max(0, self.polling_interval - elapsed)

                try:
                    await asyncio.wait_for(self._polling_event.wait(), timeout=sleep_time)
                    self._polling_event.clear()
                except asyncio.TimeoutError:
                    pass

        except asyncio.CancelledError:
            self.logger.info("Получен запрос на остановку опроса...")
        except Exception as e:
            self.logger.error(f"Критическая ошибка в цикле опроса: {e}")
            raise
        finally:
            self._is_running = False
            self._polling_task = None
            self.logger.info("Опрос полностью остановлен")

    async def stop_polling(self):
        """Корректная остановка опроса"""
        if not self._is_running:
            return

        self._is_running = False

        if self._polling_event:
            self._polling_event.set()

        async with self._tasks_lock:
            current_tasks = list(self.active_tasks)
            self.active_tasks = []

        if current_tasks:
            try:
                await asyncio.gather(*[task.cancel() for task in current_tasks if not task.done()],
                                   return_exceptions=True)
            except Exception as e:
                self.logger.debug(f"Ошибка при отмене задач: {e}")

        if self._polling_task is not None and not self._polling_task.done():
            self._polling_task.cancel()
            try:
                await self._polling_task
            except (asyncio.CancelledError, Exception) as e:
                self.logger.debug(f"Ошибка при отмене основной задачи: {e}")

    async def cleanup(self):
        """Очистка ресурсов"""
        await self.stop_polling()
        if hasattr(self, '_polling_event') and self._polling_event is not None:
            self._polling_event = None