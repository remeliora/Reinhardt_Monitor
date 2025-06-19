from sqlalchemy import Column, Integer, Float, Boolean, ForeignKey
from sqlalchemy.orm import relationship

from core.model.base import Base


class Threshold(Base):
    __tablename__ = 'threshold'

    id = Column(Integer, primary_key=True, autoincrement=True)
    low_value = Column(Float)
    high_value = Column(Float)
    is_enable = Column(Boolean, default=True)
    parameter_id = Column(Integer, ForeignKey('parameter.id'), nullable=False)
    device_id = Column(Integer, ForeignKey('device.id'), nullable=False)

    parameter = relationship(
        "Parameter",
        back_populates="thresholds",
        lazy="joined"
    )
    device = relationship(
        "Device",
        back_populates="thresholds",
        lazy="joined"
    )
