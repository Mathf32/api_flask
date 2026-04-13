import pytest
from run import app as flask_app
from app.database.db import db
import os

@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as client:
        yield client

@pytest.fixture(autouse=True)
def setup_test_db():
    if not db.is_closed():
        db.close()

    # Supprimer la DB si elle existe
    if os.path.exists(os.environ["test_db_path"]):
        os.remove(os.environ["test_db_path"])
