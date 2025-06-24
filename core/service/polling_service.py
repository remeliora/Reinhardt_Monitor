import asyncio
import json
import logging
import os
import re
from datetime import datetime
from typing import List, Optional, Dict, Any

from core.model import Device, Parameter
from infrastructure.db.postgres import PostgresDB
from infrastructure.db.repositories import (
    DeviceRepository,
    ParameterRepository,
    DeviceTypeRepository
)


class PollingService:
    def __init__(self, db: PostgresDB, polling_interval: int = 15, output_dir: str = "device_data"):
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
        # Убрали создание Event здесь, будем создавать его при запуске

        os.makedirs(self.output_dir, exist_ok=True)

    @property
    def polling_interval(self) -> int:
        """Получить текущий интервал опроса"""
        return self._polling_interval

    @polling_interval.setter
    def polling_interval(self, value: int):
        """Установить новый интервал опроса и уведомить цикл опроса"""
        if value <= 0:
            raise ValueError("Интервал опроса должен быть положительным числом")
        self._polling_interval = value
        self._polling_event.set()  # Прерываем sleep для применения нового интервала

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

                # Получаем актуальные параметры из БД
                parameters = await self.get_device_parameters(device)
                parameters_data = []

                # Обрабатываем каждый параметр
                for param in parameters:
                    value = await self.extract_parameter_value(frame_str, param)
                    if value is not None:
                        formatted_value = float(f"{value:.1f}") if param.command == 'DR' else value
                        # self.logger.info(
                        #     f"{device.name} | {param.name}: {formatted_value} {param.metric or ''}"
                        # )

                        param_data = {
                            "name": param.name,
                            "command": param.command,
                            "value": formatted_value,
                            "metric": param.metric or "",
                            "timestamp": datetime.now().isoformat()
                        }
                        parameters_data.append(param_data)

                        await self.check_thresholds(device, param, value)

                # Сохраняем данные устройства
                await self.save_device_data(device, parameters_data)

            except asyncio.TimeoutError:
                self.logger.warning(f"Таймаут ожидания данных от {device.name}")
            except Exception as e:
                self.logger.error(f"Ошибка чтения данных от {device.name}: {e}")
            finally:
                writer.close()
                await writer.wait_closed()

        except Exception as e:
            self.logger.error(f"Ошибка подключения к {device.name}: {e}")

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
        """Один цикл опроса всех активных устройств"""
        devices = await self.get_active_devices()
        # self.logger.info(f"Начинаем опрос {len(devices)} устройств")

        tasks = []
        for device in devices:
            task = asyncio.create_task(self.poll_device(device))
            tasks.append(task)
            self.active_tasks.append(task)

        await asyncio.gather(*tasks, return_exceptions=True)
        self.active_tasks = []

    async def start_polling(self):
        """Запуск периодического опроса всех устройств"""
        if self._is_running:
            self.logger.warning("Опрос уже запущен")
            return

        self._is_running = True
        self._polling_event.clear()

        try:
            while self._is_running:
                start_time = datetime.now()
                await self.poll_all_devices()

                # Рассчитываем время до следующего опроса
                elapsed = (datetime.now() - start_time).total_seconds()
                sleep_time = max(0, self.polling_interval - elapsed)

                try:
                    # Используем событие для прерывания sleep при изменении интервала
                    await asyncio.wait_for(self._polling_event.wait(), timeout=sleep_time)
                    self._polling_event.clear()  # Сбрасываем событие для следующего цикла
                except asyncio.TimeoutError:
                    pass  # Нормальное завершение sleep

        except asyncio.CancelledError:
            self.logger.info("Получен запрос на остановку опроса...")
        except Exception as e:
            self.logger.error(f"Критическая ошибка: {e}")
            raise
        finally:
            self._is_running = False
            # Отменяем все активные задачи
            await self.stop_polling()
            self.logger.info("Опрос полностью остановлен")

    async def stop_polling(self):
        """Корректная остановка опроса"""
        self._is_running = False
        self._polling_event.set()  # Прерываем sleep

        # Отменяем все активные задачи
        for task in self.active_tasks:
            if not task.done():
                task.cancel()

        # Дожидаемся завершения всех задач
        if self.active_tasks:
            try:
                await asyncio.gather(*self.active_tasks)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                self.logger.error(f"Ошибка при отмене задач: {e}")
            finally:
                self.active_tasks = []

        # Отменяем основную задачу опроса
        if self._polling_task and not self._polling_task.done():
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass

    async def run(self):
        """Запуск периодического опроса всех устройств"""
        if self._is_running:
            self.logger.warning("Опрос уже запущен")
            return

        self._is_running = True
        self._polling_event = asyncio.Event()  # Создаем новый Event для текущего loop
        self._polling_event.clear()

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
            self.logger.error(f"Критическая ошибка: {e}")
            raise
        finally:
            self._is_running = False
            await self.stop_polling()
            self.logger.info("Опрос полностью остановлен")

    async def cleanup(self):
        """Очистка ресурсов"""
        self._is_running = False
        if hasattr(self, '_polling_event'):
            del self._polling_event
        if self._polling_task and not self._polling_task.done():
            self._polling_task.cancel()