import asyncio
import logging
import sys
from threading import Thread

from PySide6.QtWidgets import QApplication

from core.service.polling_service import PollingService
from ui.main_window import MeteoMonitor
from infrastructure.config.config import settings
from infrastructure.db.postgres import PostgresDB


def setup_logging():
    """Настройка системы логирования"""
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(settings.LOG_FILE, encoding="utf-8")
        ],
    )


class Application:
    def __init__(self):
        """Инициализация приложения"""
        self.logger = logging.getLogger("App")
        self.db = None
        self.polling_service = None
        self.gui = None
        self.polling_thread = None

    def initialize_db(self):
        """Инициализация подключения к базе данных"""
        try:
            self.db = PostgresDB(settings.DATABASE_URL)
            if not self.db.check_connection():
                raise ConnectionError("Не удалось подключиться к БД")

            self.db.init_db()
            self.logger.info("База данных инициализирована")
            return True
        except Exception as e:
            self.logger.critical(f"Ошибка инициализации БД: {e}")
            return False

    def initialize_polling_service(self):
        """Инициализация сервиса опроса"""
        try:
            self.polling_service = PollingService(self.db)
            self.logger.info("Сервис опроса инициализирован")
            return True
        except Exception as e:
            self.logger.error(f"Ошибка инициализации сервиса опроса: {e}")
            return False

    def run_polling_service(self):
        """Запуск сервиса опроса в отдельном потоке"""
        try:
            self.polling_thread = Thread(
                target=self._run_async_polling,
                daemon=True
            )
            self.polling_thread.start()
            self.logger.info("Сервис опроса запущен")
        except Exception as e:
            self.logger.error(f"Ошибка запуска сервиса опроса: {e}")

    def _run_async_polling(self):
        """Запуск асинхронного опроса в отдельном потоке"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.polling_service.start_polling())
        except Exception as e:
            self.logger.error(f"Ошибка в сервисе опроса: {e}")
        finally:
            loop.close()

    def initialize_gui(self):
        """Инициализация графического интерфейса"""
        try:
            app = QApplication(sys.argv)
            self.gui = MeteoMonitor(self)  # Передаем ссылку на приложение
            self.gui.show()
            self.logger.info("Графический интерфейс инициализирован")
            sys.exit(app.exec())
        except Exception as e:
            self.logger.critical(f"Ошибка инициализации GUI: {e}")

    def run(self):
        """Основной метод запуска приложения"""
        setup_logging()
        self.logger.info("Запуск приложения")

        if not self.initialize_db():
            return

        if not self.initialize_polling_service():
            return

        # Запускаем GUI в основном потоке
        self.initialize_gui()


if __name__ == "__main__":
    app = Application()
    app.run()