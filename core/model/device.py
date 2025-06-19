from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship

from core.model.base import Base


class Device(Base):
    __tablename__ = "device"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    ip_address = Column(String(100), nullable=False)
    port = Column(Integer, nullable=False)
    description = Column(String(255))
    is_enable = Column(Boolean, default=True)
    device_type_id = Column(Integer, ForeignKey('device_type.id'), nullable=False)

    device_type = relationship(
        "DeviceType",
        back_populates="devices",
        lazy="joined"
    )
    thresholds = relationship(
        "Threshold",
        back_populates="device",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
