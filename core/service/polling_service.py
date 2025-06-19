import asyncio
import logging

from infrastructure.db.postgres import PostgresDB
from infrastructure.db.repositories import DeviceRepository, DeviceTypeRepository, ParameterRepository


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
        self.device_type_repo = DeviceTypeRepository(db.get_session())
        self.parameter_repo = ParameterRepository(db.get_session())
        self.logger = logging.getLogger("PollingService")

    async def check_device_connection(self, ip: str, port: int) -> bool:
        """Проверка подключения к устройству"""
        try:
            # Попытка соединения через сокет
            reader, writer = await asyncio.open_connection(ip, port)
            writer.close()  # Закрываем соединение
            await writer.wait_closed()
            # self.logger.info(f"Устройство с IP: {ip}, Порт: {port} доступно.")
            return True
        except (asyncio.TimeoutError, ConnectionRefusedError, OSError) as e:
            self.logger.error(f"Ошибка подключения к устройству с IP: {ip}, Порт: {port}: {e}")
            return False

    async def get_device_parameters(self, device):
        """Получение параметров устройства через его тип"""
        device_type = device.device_type
        if device_type:
            self.logger.info(f"Сбор параметров для устройства {device.name} ({device_type.name})")
            parameters = self.parameter_repo.get_parameters_by_device_type(device_type.id)
            if parameters:
                for param in parameters:
                    self.logger.info(f"Параметр устройства {device.name}: {param.name} - {param.command}")
            else:
                self.logger.info(f"Нет параметров для устройства {device.name}")
        else:
            self.logger.info(f"Не удалось найти тип устройства для {device.name}")

    async def poll_device(self, device):
        """Задача для опроса одного устройства"""
        ip = device.ip_address
        port = device.port

        if await self.check_device_connection(ip, port):
            # self.logger.info(f"Опрос устройства {device.name} (IP: {ip}, Порт: {port})")
            await self.get_device_parameters(device)  # Получаем параметры устройства
        else:
            self.logger.info(f"{device.name} (IP: {ip}, Порт: {port}) соединение отсутствует!")

    async def get_enabled_devices(self):
        """Получение списка включённых устройств"""
        try:
            devices = self.device_repo.get_devices_by_is_enable_true()
            self.logger.info(f"Количество датчиков для опроса: {len(devices)}")
            # for device in devices:
            #     self.logger.info(f"{device.name} (IP: {device.ip_address}, Порт: {device.port})")

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
