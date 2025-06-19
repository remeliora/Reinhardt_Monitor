from sqlalchemy.orm import joinedload

from core.model import Threshold
from infrastructure.db.repositories.base_repository import BaseRepository


class ThresholdRepository(BaseRepository):
    def __init__(self, session):
        super().__init__(session, Threshold)

    def get_threshold_by_id(self, threshold_id: int) -> Threshold:
        """Получение порога по ID"""
        return self.get_by_id(threshold_id)

    def get_thresholds_by_parameter_id_and_is_enable_true(self, parameter_id: int) -> list[Threshold]:
        """Получение активных порогов для параметра"""
        return self.session.query(Threshold).filter(
            Threshold.parameter_id == parameter_id,
            Threshold.is_enable == True
        ).all()

    def get_thresholds_by_device_id(self, device_id: int) -> list[Threshold]:
        """Получение всех порогов для устройства"""
        return self.session.query(Threshold).options(
            joinedload(Threshold.parameter)
        ).filter(Threshold.device_id == device_id).all()
