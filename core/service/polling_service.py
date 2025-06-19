import asyncio
import logging

from infrastructure.db.postgres import PostgresDB
from infrastructure.db.repositories import DeviceRepository


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
        self.logger = logging.getLogger("PollingService")

    async def get_enabled_devices(self):
        """Получение списка включённых устройств"""
        try:
            devices = self.device_repo.get_devices_by_is_enable_true()
            self.logger.info(f"Количество датчиков для опроса: {len(devices)}")
            for device in devices:
                self.logger.info(f"{device.name} (IP: {device.ip_address}, Порт: {device.port})")
        except Exception as e:
            self.logger.error(f"Ошибка при запросе данных: {e}")

    async def start_polling(self):
        """Метод для запуска периодического опроса"""
        while True:
            await self.get_enabled_devices()  # Сбор информации о включённых устройствах
            await asyncio.sleep(self.interval)  # Ждём 15 секунд перед следующим опросом
