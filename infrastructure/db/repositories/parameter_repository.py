from core.model import Parameter
from infrastructure.db.repositories.base_repository import BaseRepository


class ParameterRepository(BaseRepository):
    def __init__(self, session):
        super().__init__(session, Parameter)

    def get_parameter_by_id(self, parameter_id: int) -> Parameter:
        """Получение параметра по ID"""
        return self.get_by_id(parameter_id)

    def get_parameters_by_device_type(self, device_type_id: int) -> list[Parameter]:
        """Получение параметров по типу устройства"""
        return self.session.query(Parameter).filter(
            Parameter.device_type_id == device_type_id
        ).all()
