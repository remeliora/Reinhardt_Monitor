from sqlalchemy.orm import joinedload

from core.model import DeviceType
from infrastructure.db.repositories.base_repository import BaseRepository


class DeviceTypeRepository(BaseRepository):
    def __init__(self, session):
        super().__init__(session, DeviceType)

    def get_device_type_by_id(self, device_type_id: int) -> DeviceType:
        """Получение типа устройства по ID с предзагрузкой связанных данных"""
        return (
            self.session
            .query(DeviceType)
            .options(
                joinedload(DeviceType.parameters),
                joinedload(DeviceType.devices)
            )
            .filter(DeviceType.id == device_type_id)
            .first()
        )

    def get_all_device_types(self) -> list[DeviceType]:
        """Получение всех типов устройств"""
        return self.get_all()
