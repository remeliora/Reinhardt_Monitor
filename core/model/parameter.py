from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from core.model.base import Base


class Parameter(Base):
    __tablename__ = 'parameter'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    command = Column(String(50), nullable=False)
    metric = Column(String(20))
    description = Column(String(255))
    device_type_id = Column(Integer, ForeignKey('device_type.id'), nullable=False)

    device_type = relationship(
        "DeviceType",
        back_populates="parameters",
        lazy="joined"
    )
    thresholds = relationship(
        "Threshold",
        back_populates="parameter",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
