from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from core.model.base import Base  # Импортируем базовый класс и все модели


class PostgresDB:
    def __init__(self, database_url: str):
        """
        Инициализация подключения к базе данных.
        :param database_url: Строка подключения к базе данных.
        """
        self.engine = create_engine(database_url, echo=False)  # echo=True для вывода SQL-запросов
        self.Session = sessionmaker(bind=self.engine)

    def init_db(self):
        """
        Инициализация базы данных: создание всех таблиц, если они ещё не созданы.
        """
        Base.metadata.create_all(self.engine)

    def get_session(self):
        """
        Получение новой сессии для работы с базой данных.
        :return: Сессия SQLAlchemy.
        """
        return self.Session()

    def check_connection(self):
        """
        Проверка соединения с базой данных.
        :return: True если соединение успешно, иначе False.
        """
        try:
            # Создаём сессию и выполняем запрос с использованием text()
            session = self.get_session()
            session.execute(text('SELECT 1'))  # Используем text() для SQL-запроса
            session.commit()  # Подтверждаем транзакцию
            return True
        except Exception as e:
            # print(f"Ошибка подключения к базе данных: {e}")
            return False

    def close_connection(self):
        """
                Корректное закрытие соединения с базой данных.
                Закрывает пул соединений и освобождает ресурсы.
                """
        try:
            if hasattr(self, 'engine') and self.engine is not None:
                self.engine.dispose()
                # self.logger.info("Соединение с базой данных успешно закрыто")
        except Exception as e:
            print(f"Ошибка при закрытии соединения с БД: {e}")
