from sqlalchemy.orm import joinedload

from core.model import Device, Threshold
from infrastructure.db.repositories.base_repository import BaseRepository


class DeviceRepository(BaseRepository):
    def __init__(self, session):
        super().__init__(session, Device)

    def get_device_by_id(self, device_id: int) -> Device:
        """Получение устройства по ID с предзагрузкой связанных данных"""
        return self.session.query(Device).options(
            joinedload(Device.device_type),
            joinedload(Device.thresholds).joinedload(Threshold.parameter)
        ).filter(Device.id == device_id).first()

    def get_devices_by_is_enable_true(self) -> list[Device]:
        """Получение всех активных устройств"""
        return self.session.query(Device).options(
            joinedload(Device.device_type)
        ).filter(Device.is_enable == True).all()

    def get_device_by_ip_and_port(self, ip: str, port: int) -> Device:
        """Поиск устройства по IP и порту"""
        return self.session.query(Device).filter(
            Device.ip_address == ip,
            Device.port == port
        ).first()

    def get_all_devices(self) -> list[Device]:
        """Получение всех устройств с предзагрузкой связанных данных"""
        return self.session.query(Device).options(
            joinedload(Device.device_type),
            joinedload(Device.thresholds).joinedload(Threshold.parameter)
        ).all()
