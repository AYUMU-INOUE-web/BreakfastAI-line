"""初期投入用の食材セット。"""
from __future__ import annotations

from app.database import session_scope
from app.models import Ingredient

DEFAULT_INGREDIENTS = [
    # main 主食
    {"name": "食パン(6枚切)", "category": "main", "unit": "枚", "calories_per_unit": 160, "default_portion": 1, "min_portion": 1, "max_portion": 2},
    {"name": "ごはん", "category": "main", "unit": "g", "calories_per_unit": 1.68, "default_portion": 150, "min_portion": 100, "max_portion": 200},
    {"name": "オートミール", "category": "main", "unit": "g", "calories_per_unit": 3.8, "default_portion": 40, "min_portion": 30, "max_portion": 60},
    {"name": "コーンフレーク", "category": "main", "unit": "g", "calories_per_unit": 3.8, "default_portion": 40, "min_portion": 30, "max_portion": 60},
    # protein たんぱく
    {"name": "ゆで卵", "category": "protein", "unit": "個", "calories_per_unit": 90, "default_portion": 1, "min_portion": 1, "max_portion": 2},
    {"name": "目玉焼き", "category": "protein", "unit": "個", "calories_per_unit": 110, "default_portion": 1, "min_portion": 1, "max_portion": 2},
    {"name": "ハム", "category": "protein", "unit": "枚", "calories_per_unit": 18, "default_portion": 2, "min_portion": 1, "max_portion": 3},
    {"name": "ヨーグルト(無糖)", "category": "protein", "unit": "g", "calories_per_unit": 0.62, "default_portion": 100, "min_portion": 80, "max_portion": 150},
    {"name": "納豆", "category": "protein", "unit": "パック", "calories_per_unit": 100, "default_portion": 1, "min_portion": 1, "max_portion": 1},
    # side 副菜
    {"name": "バナナ", "category": "side", "unit": "本", "calories_per_unit": 90, "default_portion": 1, "min_portion": 1, "max_portion": 1},
    {"name": "りんご", "category": "side", "unit": "個", "calories_per_unit": 120, "default_portion": 1, "min_portion": 1, "max_portion": 1},
    {"name": "ミニトマト", "category": "side", "unit": "個", "calories_per_unit": 5, "default_portion": 5, "min_portion": 3, "max_portion": 8},
    {"name": "サラダ(ミックス)", "category": "side", "unit": "g", "calories_per_unit": 0.2, "default_portion": 80, "min_portion": 50, "max_portion": 120},
    {"name": "アボカド", "category": "side", "unit": "個", "calories_per_unit": 230, "default_portion": 0.5, "min_portion": 0.5, "max_portion": 1},
    # drink 飲み物
    {"name": "牛乳", "category": "drink", "unit": "ml", "calories_per_unit": 0.67, "default_portion": 200, "min_portion": 150, "max_portion": 250},
    {"name": "豆乳(無調整)", "category": "drink", "unit": "ml", "calories_per_unit": 0.46, "default_portion": 200, "min_portion": 150, "max_portion": 250},
    {"name": "オレンジジュース", "category": "drink", "unit": "ml", "calories_per_unit": 0.45, "default_portion": 200, "min_portion": 150, "max_portion": 250},
    {"name": "コーヒー(ブラック)", "category": "drink", "unit": "ml", "calories_per_unit": 0.04, "default_portion": 200, "min_portion": 150, "max_portion": 250},
    {"name": "カフェオレ", "category": "drink", "unit": "ml", "calories_per_unit": 0.4, "default_portion": 200, "min_portion": 150, "max_portion": 250},
]


def seed_default_ingredients() -> int:
    """既存名と重複しないものだけ投入し、追加件数を返す。"""
    inserted = 0
    with session_scope() as s:
        existing = {n for (n,) in s.query(Ingredient.name).all()}
        for spec in DEFAULT_INGREDIENTS:
            if spec["name"] in existing:
                continue
            s.add(Ingredient(**spec))
            inserted += 1
    return inserted
