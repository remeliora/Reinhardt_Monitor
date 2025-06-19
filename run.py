import asyncio
import logging
import sys

from core.service.polling_service import PollingService
from infrastructure.config.config import settings
from infrastructure.db.postgres import PostgresDB


# Настройка логирования
def setup_logging():
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),  # Вывод в консоль
            logging.FileHandler(settings.LOG_FILE, encoding="utf-8")  # Запись в файл
        ],
    )


async def main():
    logger = logging.getLogger("main")

    # 1) Инициализация БД
    db = PostgresDB(settings.DATABASE_URL)

    # Проверяем соединение с базой данных
    if not db.check_connection():
        logger.critical("Не удалось подключиться к БД")
        sys.exit(1)

    # Инициализация базы данных (создание таблиц, если их нет)
    db.init_db()
    logger.info("Соединение с базой данных установлено")

    # # Создаем сессию
    # session = db.get_session()

    # Здесь можно добавить логику для работы с приложением
    logger.info("Приложение запущено")

    # Создаём сервис опроса
    polling_service = PollingService(db)

    # Запуск опроса
    await polling_service.start_polling()


# Запуск асинхронного основного метода
if __name__ == "__main__":
    # Настройка логирования
    setup_logging()
    asyncio.run(main())
