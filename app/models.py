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
    profile_name = Column(String(64), nullable=True, index=True)
    menu_name = Column(String(128), nullable=False)
    items_json = Column(Text, nullable=False)  # [{ingredient_id, name, portion, unit, calories}, ...]
    total_calories = Column(Float, nullable=False)
    is_fallback = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class MessageTemplate(Base):
    """LINE配信のテンプレート。kind ごとに is_active=True のものが1つずつ使われる。"""

    __tablename__ = "message_templates"

    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False)
    body = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=False)
    # "breakfast" or "cleaning". 既存 DB 互換のため nullable(None は "breakfast" 扱い)
    kind = Column(String(32), nullable=True, default="breakfast", index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "body": self.body,
            "is_active": self.is_active,
            "kind": self.kind or "breakfast",
        }


class Cleaner(Base):
    """掃除担当者。名前のみ登録、累積ポイントを持つ。"""

    __tablename__ = "cleaners"

    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False, unique=True)
    total_points = Column(Integer, nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "total_points": self.total_points,
            "active": self.active,
        }


class CleaningLocation(Base):
    """掃除する場所。名前・点数・実施内容(備考)を持つ。"""

    __tablename__ = "cleaning_locations"

    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False, unique=True)
    points = Column(Integer, nullable=False)
    notes = Column(Text, nullable=False, default="")
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "points": self.points,
            "notes": self.notes,
            "active": self.active,
        }


class CleaningHistory(Base):
    """掃除担当履歴。毎週の割り当て結果を記録する。"""

    __tablename__ = "cleaning_history"

    id = Column(Integer, primary_key=True)
    assigned_on = Column(Date, nullable=False, index=True)
    cleaner_id = Column(Integer, nullable=True)
    cleaner_name = Column(String(64), nullable=False)
    location_id = Column(Integer, nullable=True)
    location_name = Column(String(128), nullable=False)
    points = Column(Integer, nullable=False, default=0)
    notes = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
