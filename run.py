import asyncio
import logging
import sys
from threading import Thread
from typing import Optional

from PySide6.QtWidgets import QApplication

from core.service.polling_service import PollingService
from ui.main_window import MeteoMonitor, GUILogHandler
from infrastructure.config.config import settings
from infrastructure.db.postgres import PostgresDB


class Application:
    def __init__(self):
        """Инициализация приложения"""
        self.logger = logging.getLogger("App")
        self.db: Optional[PostgresDB] = None
        self.polling_service: Optional[PollingService] = None
        self.gui: Optional[MeteoMonitor] = None
        self.polling_thread: Optional[Thread] = None
        self._polling_loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event = asyncio.Event()
        self._is_polling_active = False

        # Инициализируем QApplication
        self.app = QApplication(sys.argv)

        # Настраиваем логирование (пока без GUI обработчика)
        self.setup_logging(include_gui_handler=False)

        self.logger.info("Приложение инициализировано")

    def setup_logging(self, include_gui_handler=True):
        """Настройка системы логирования"""
        level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

        # Очищаем существующие обработчики
        logging.getLogger().handlers = []

        # Создаем форматтер
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # Консольный обработчик
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        # Файловый обработчик
        file_handler = logging.FileHandler(settings.LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(formatter)

        # Настраиваем корневой логгер
        root_logger = logging.getLogger()
        root_logger.setLevel(level)
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)

        # GUI обработчик добавляем только после инициализации GUI
        if include_gui_handler and self.gui:
            gui_handler = GUILogHandler(self.gui.log_updated)
            gui_handler.setFormatter(formatter)
            root_logger.addHandler(gui_handler)

    def initialize_db(self) -> bool:
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

    def initialize_polling_service(self) -> bool:
        """Инициализация сервиса опроса"""
        try:
            if self.db is None:
                raise ValueError("База данных не инициализирована")

            self.polling_service = PollingService(self.db)
            self.logger.info("Сервис опроса инициализирован")
            return True
        except Exception as e:
            self.logger.error(f"Ошибка инициализации сервиса опроса: {e}")
            return False

    def run_polling_service(self):
        """Запуск сервиса опроса в отдельном потоке"""
        if self.polling_service is None:
            self.logger.error("Сервис опроса не инициализирован")
            return

        if self._is_polling_active:
            self.logger.warning("Сервис опроса уже запущен")
            return

        try:
            self._stop_event.clear()
            self.polling_thread = Thread(
                target=self._run_async_polling,
                daemon=True,
                name="PollingServiceThread"
            )
            self.polling_thread.start()
            self._is_polling_active = True
            self.logger.info("Сервис опроса запущен в отдельном потоке")
        except Exception as e:
            self.logger.error(f"Ошибка запуска сервиса опроса: {e}")

    def _run_async_polling(self):
        """Запуск асинхронного опроса в отдельном потоке"""
        try:
            self._polling_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._polling_loop)
            self._polling_loop.run_until_complete(self.polling_service.run())
        except Exception as e:
            self.logger.error(f"Ошибка в сервисе опроса: {e}")
        finally:
            self._is_polling_active = False
            if self._polling_loop is not None:
                if self._polling_loop.is_running():
                    self._polling_loop.stop()
                self._polling_loop.close()
            self._polling_loop = None

    async def stop_polling_service(self):
        """Корректная остановка сервиса опроса"""
        if self.polling_service is None or not self._is_polling_active:
            return

        self.logger.info("Остановка сервиса опроса...")
        try:
            if self._polling_loop is not None and not self._polling_loop.is_closed():
                future = asyncio.run_coroutine_threadsafe(
                    self.polling_service.stop_polling(),
                    self._polling_loop
                )
                future.result(timeout=5.0)
            self.logger.info("Сервис опроса остановлен")
        except asyncio.TimeoutError:
            self.logger.warning("Таймаут при остановке сервиса опроса")
        except Exception as e:
            self.logger.error(f"Ошибка при остановке сервиса опроса: {e}")
        finally:
            self._is_polling_active = False

    def initialize_gui(self):
        """Инициализация графического интерфейса"""
        try:
            self.gui = MeteoMonitor(self)
            self.gui.closeEvent = self.on_gui_close

            # Теперь добавляем GUI обработчик в логирование
            self.setup_logging(include_gui_handler=True)

            # self.logger.info("Графический интерфейс инициализирован")
        except Exception as e:
            self.logger.critical(f"Ошибка инициализации GUI: {e}")
            raise

    def on_gui_close(self, event):
        """Обработчик закрытия главного окна"""
        self.logger.info("Завершение работы приложения...")
        self.shutdown()
        event.accept()

    def shutdown(self):
        """Корректное завершение работы приложения"""
        self.logger.info("Запуск процедуры завершения работы...")

        if self._is_polling_active:
            if self._polling_loop is not None and self._polling_loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self.stop_polling_service(),
                    self._polling_loop
                )

        if self.db is not None:
            self.db.close_connection()
            self.logger.info("Соединение с БД закрыто")

    def run(self):
        """Основной метод запуска приложения"""
        self.logger.info("Запуск приложения")

        if not self.initialize_db():
            return

        if not self.initialize_polling_service():
            return

        # Инициализируем GUI
        self.initialize_gui()

        # Показываем главное окно
        self.gui.show()

        # Запускаем цикл событий
        sys.exit(self.app.exec())

    def is_polling_active(self) -> bool:
        """Проверка активности опроса"""
        return self._is_polling_active


if __name__ == "__main__":
    app = Application()
    app.run()
