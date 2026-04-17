import os
import pytest
from dotenv import load_dotenv

load_dotenv()

# Forcer la DB de test AVANT d'importer l'app
os.environ["db_path"] = os.getenv("test_db_path", "test.db")

from app import create_app
from app.database.db import db, Product, Order, Transaction, CreditCard, ShippingInformation


@pytest.fixture(scope="session")
def app():
    flask_app = create_app()
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture(scope="session")
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def setup_test_db():
    """Recrée les tables et insère un produit de test avant chaque test."""
    db.connect(reuse_if_open=True)
    db.drop_tables([Order, Transaction, CreditCard, ShippingInformation, Product], safe=True)
    db.create_tables([Product, Order, Transaction, CreditCard, ShippingInformation])

    Product.create(
        id=1,
        name="Produit Test",
        type="test",
        description="Description de test",
        image="img.png",
        height=10,
        weight=400,
        price=28.10,
        in_stock=True,
    )
    Product.create(
        id=2,
        name="Produit Hors Stock",
        type="test",
        description="Rupture",
        image="img2.png",
        height=5,
        weight=200,
        price=10.00,
        in_stock=False,
    )

    yield

    db.close()