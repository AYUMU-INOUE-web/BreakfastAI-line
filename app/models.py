from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Text, Boolean
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Ingredient(Base):
    """登録食材。カロリーは1単位あたりの値。"""

    __tablename__ = "ingredients"

    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False, unique=True)
    category = Column(String(32), nullable=False)  # main / protein / side / drink
    unit = Column(String(16), nullable=False)  # g / 個 / 枚 / ml など
    calories_per_unit = Column(Float, nullable=False)
    default_portion = Column(Float, nullable=False)
    min_portion = Column(Float, nullable=False)
    max_portion = Column(Float, nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "unit": self.unit,
            "calories_per_unit": self.calories_per_unit,
            "default_portion": self.default_portion,
            "min_portion": self.min_portion,
            "max_portion": self.max_portion,
            "active": self.active,
        }


class MenuHistory(Base):
    """生成・配信した献立の履歴。"""

    __tablename__ = "menu_history"

    id = Column(Integer, primary_key=True)
    served_on = Column(Date, nullable=False, index=True)
    menu_name = Column(String(128), nullable=False)
    items_json = Column(Text, nullable=False)  # [{ingredient_id, name, portion, unit, calories}, ...]
    total_calories = Column(Float, nullable=False)
    is_fallback = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class MessageTemplate(Base):
    """LINE配信のテンプレート。is_active=True のものが1つだけ使われる想定。"""

    __tablename__ = "message_templates"

    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False)
    body = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "body": self.body,
            "is_active": self.is_active,
        }
