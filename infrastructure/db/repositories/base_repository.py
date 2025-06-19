from sqlalchemy.orm import Session


class BaseRepository:
    def __init__(self, session: Session, model):
        self.session = session
        self.model = model

    def get_by_id(self, id: int):
        """Получение записи по ID"""
        return self.session.query(self.model).filter(self.model.id == id).first()

    def get_all(self):
        """Получение всех записей"""
        return self.session.query(self.model).all()

    def add(self, instance):
        """Добавить новую запись"""
        self.session.add(instance)
        self.session.commit()
        return instance

    def delete(self, instance):
        """Удалить запись"""
        self.session.delete(instance)
        self.session.commit()

    def update(self, instance):
        """Обновить запись"""
        self.session.commit()
        return instance
