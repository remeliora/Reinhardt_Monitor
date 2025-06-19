from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from core.model.base import Base


class DeviceType(Base):
    __tablename__ = "device_type"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(String(255))

    parameters = relationship(
        "Parameter",
        back_populates="device_type",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    devices = relationship(
        "Device",
        back_populates="device_type",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

