import pytest
from run import app as flask_app
from app.database.db import db, Product

@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as client:
        yield client

@pytest.fixture(autouse=True)
def setup_test_db():
    # S'assure que la DB est connectée pour les tests
    if db.is_closed():
        db.connect()
    yield