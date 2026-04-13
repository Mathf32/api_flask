import pytest
from app.database.db import Order, Product, db

from app.database.db import setup_db, CreditCard, ShippingInformation, Transaction

# 1. On force l'initialisation de la DB pour l'environnement de test
setup_db(True)


@pytest.fixture(autouse=True)
def prepare_db():
    # Crée les tables si elles n'existent pas dans le fichier .db pointé par setup_db()
    db.connect(reuse_if_open=True)
    db.create_tables([Product, Order, Transaction, CreditCard, ShippingInformation])

    # On s'assure que le produit ID=1 existe, sinon tes tests planteront dès la création de commande
    Product.get_or_create(
        id=1,
        defaults={
            "name": "Produit Test",
            "type": "test",
            "description": "Description",
            "image": "img.png",
            "height": 10,
            "weight": 100,
            "price": 28.10,
            "in_stock": True
        }
    )
    yield

def test_error_already_paid(client):
    """Vérifie qu'on ne peut pas payer une commande déjà payée (Exigence technique)"""

    # On crée une commande manuellement marquée comme payée
    with db.atomic():
        prod = Product.get(Product.id == 1)
        order = Order.create(
            product=prod,
            product_quantity=1,
            email="test@test.com",
            paid=True,  # Déjà payé
            total_price=10.0,
            total_price_tax=11.5
        )

    pay_payload = {
        "credit_card": {
            "name": "Pier-Luc Larouche",
            "number": "4540 0000 0000 0001",  # Doit être un String
            "expiration_year": 2028,  # Doit être un Int
            "expiration_month": 12,  # Doit être un Int
            "cvv": "123"  # Doit être un String
        }
    }
    response = client.put(f'/order/{order.id}', json=pay_payload)

    # Doit retourner 422 Unprocessable Entity
    assert response.status_code == 422
    assert response.get_json()["errors"]["order"]["code"] == "already-paid"


def test_error_payment_missing_info(client):
    """Vérifie qu'on ne peut pas payer si l'adresse est manquante"""

    # Création d'une commande sans passer par l'étape PUT (donc pas d'email/adresse)
    client.post('/orders', json={"product": {"id": 1, "quantity": 1}})

    pay_payload = {
        "credit_card": {"name": "Test", "number": "4540..", "expiration_year": 2028, "expiration_month": 1,
                        "cvv": "111"}
    }
    response = client.put(f'/order/1', json=pay_payload)

    # Doit retourner 422 car email/adresse manquants
    assert response.status_code == 422
    assert response.get_json()["errors"]["order"]["code"] == "missing-fields"



def test_full_order_flow_real(client):
    """Test du flux complet : Création -> Taxes -> Paiement RÉEL"""

    # 1. CRÉATION
    order_res = client.post('/orders', json={"product": {"id": 1, "quantity": 1}})
    order_id = order_res.get_json().get("Nouvelle Commande", {}).get("id")

    # 2. MISE À JOUR (Taxes + Adresse)
    update_payload = {
        "order": {
            "email": "pierluc@test.com",
            "shipping_information": {
                "country": "Canada",
                "address": "555 Boulevard de l'Université",
                "postal_code": "G7H 2B1",
                "city": "Saguenay",
                "province": "QC"
            }
        }
    }
    client.put(f'/order/1', json=update_payload)

    # 3. PAIEMENT RÉEL
    pay_payload = {
        "credit_card": {
            "name": "Pier-Luc Larouche",
            "number": "4242 4242 4242 4242",
            "expiration_year": 2028,
            "expiration_month": 12,
            "cvv": "123"
        }
    }

    response = client.put(f'/order/1', json=pay_payload)

    # Si ça échoue, le -s dans pytest nous montrera ce print
    if response.status_code != 200:
        print(f"\nLOG ERREUR UQAC: {response.get_json()}")

    assert response.status_code == 200
    assert response.get_json()["order"]["transaction"]["success"] == "true"