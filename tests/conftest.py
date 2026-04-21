import json
import random

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Ingredient, MenuHistory


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    s = Session()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def populated_session(session):
    items = [
        Ingredient(name="食パン", category="main", unit="枚", calories_per_unit=160,
                   default_portion=1, min_portion=1, max_portion=2, active=True),
        Ingredient(name="ごはん", category="main", unit="g", calories_per_unit=1.68,
                   default_portion=150, min_portion=100, max_portion=200, active=True),
        Ingredient(name="ゆで卵", category="protein", unit="個", calories_per_unit=90,
                   default_portion=1, min_portion=1, max_portion=2, active=True),
        Ingredient(name="ヨーグルト", category="protein", unit="g", calories_per_unit=0.62,
                   default_portion=100, min_portion=80, max_portion=150, active=True),
        Ingredient(name="バナナ", category="side", unit="本", calories_per_unit=90,
                   default_portion=1, min_portion=1, max_portion=1, active=True),
        Ingredient(name="サラダ", category="side", unit="g", calories_per_unit=0.2,
                   default_portion=80, min_portion=50, max_portion=120, active=True),
        Ingredient(name="牛乳", category="drink", unit="ml", calories_per_unit=0.67,
                   default_portion=200, min_portion=150, max_portion=250, active=True),
        Ingredient(name="コーヒー", category="drink", unit="ml", calories_per_unit=0.04,
                   default_portion=200, min_portion=150, max_portion=250, active=True),
    ]
    for i in items:
        session.add(i)
    session.commit()
    return session


@pytest.fixture(autouse=True)
def _seed_random():
    random.seed(42)
