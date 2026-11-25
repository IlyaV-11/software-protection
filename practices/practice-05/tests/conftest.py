import pytest
from fastapi.testclient import TestClient

from src.main import app, items_db


@pytest.fixture
def client():
    # Каждый тест начинает работу с пустым справочником.
    items_db.clear()
    with TestClient(app) as api:
        yield api
    items_db.clear()
