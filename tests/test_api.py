"""
Tests conformes au devis TP1.
POST /order  → 302 + Location header
GET /order/<id> → 200 + {order: {...}}
PUT /order/<id> avec {order: ...} → 200 + {order: {...}}
PUT /order/<id> avec {credit_card: ...} → 200 + {order: {...}} ou 422
"""
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_order(client, product_id=1, quantity=1):
    """Crée une commande et retourne l'order_id extrait du header Location."""
    res = client.post("/order", json={"product": {"id": product_id, "quantity": quantity}})
    assert res.status_code == 302, f"Attendu 302, reçu {res.status_code}: {res.data}"
    location = res.headers.get("Location", "")
    order_id = int(location.split("/")[-1])
    return order_id


def fill_order(client, order_id, email="test@test.com", province="QC"):
    payload = {
        "order": {
            "email": email,
            "shipping_information": {
                "country": "Canada",
                "address": "555 Boulevard de l'Université",
                "postal_code": "G7H 2B1",
                "city": "Saguenay",
                "province": province,
            },
        }
    }
    return client.put(f"/order/{order_id}", json=payload)


# ---------------------------------------------------------------------------
# POST /order
# ---------------------------------------------------------------------------

def test_create_order_returns_302(client):
    res = client.post("/order", json={"product": {"id": 1, "quantity": 1}})
    assert res.status_code == 302
    assert "Location" in res.headers
    assert "/order/" in res.headers["Location"]


def test_create_order_missing_product_field(client):
    res = client.post("/order", json={})
    assert res.status_code == 422
    assert res.get_json()["errors"]["product"]["code"] == "missing-fields"


def test_create_order_missing_quantity(client):
    res = client.post("/order", json={"product": {"id": 1}})
    assert res.status_code == 422


def test_create_order_invalid_product_id(client):
    res = client.post("/order", json={"product": {"id": 9999, "quantity": 1}})
    assert res.status_code == 422
    assert res.get_json()["errors"]["product"]["code"] == "invalid-product"


def test_create_order_out_of_stock(client):
    res = client.post("/order", json={"product": {"id": 2, "quantity": 1}})
    assert res.status_code == 422
    assert res.get_json()["errors"]["product"]["code"] == "out-of-inventory"


def test_create_order_quantity_zero(client):
    res = client.post("/order", json={"product": {"id": 1, "quantity": 0}})
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# GET /order/<id>
# ---------------------------------------------------------------------------

def test_get_order(client):
    order_id = create_order(client)
    res = client.get(f"/order/{order_id}")
    assert res.status_code == 200
    body = res.get_json()
    assert "order" in body
    order = body["order"]
    assert order["id"] == order_id
    assert order["paid"] is False
    assert order["email"] is None
    assert isinstance(order["shipping_information"], dict)
    assert isinstance(order["credit_card"], dict)
    assert isinstance(order["transaction"], dict)


def test_get_order_not_found(client):
    res = client.get("/order/99999")
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# PUT /order/<id> — mise à jour infos client
# ---------------------------------------------------------------------------

def test_put_order_client_info(client):
    order_id = create_order(client)
    res = fill_order(client, order_id)
    assert res.status_code == 200
    body = res.get_json()
    assert "order" in body
    order = body["order"]
    assert order["email"] == "test@test.com"
    assert order["shipping_information"]["province"] == "QC"
    # Les taxes QC = 15%
    assert order["total_price_tax"] is not None
    expected_tax = round(order["total_price"] * 1.15, 2)
    assert abs(order["total_price_tax"] - expected_tax) < 0.01


def test_put_order_missing_email(client):
    order_id = create_order(client)
    res = client.put(f"/order/{order_id}", json={
        "order": {
            "shipping_information": {
                "country": "Canada", "address": "123 Rue", "postal_code": "G1A 1A1",
                "city": "Québec", "province": "QC"
            }
        }
    })
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# PUT /order/<id> — paiement
# ---------------------------------------------------------------------------

def test_pay_already_paid(client):
    order_id = create_order(client)
    fill_order(client, order_id)

    from app.database.db import Order, db
    db.connect(reuse_if_open=True)
    order = Order.get_by_id(order_id)
    order.paid = True
    order.save()
    db.close()

    res = client.put(f"/order/{order_id}", json={
        "credit_card": {
            "name": "John Doe", "number": "4242424242424242",
            "expiration_year": 2028, "expiration_month": 12, "cvv": "123"
        }
    })
    assert res.status_code == 422
    assert res.get_json()["errors"]["order"]["code"] == "already-paid"


def test_pay_missing_client_info(client):
    order_id = create_order(client)
    # Pas de PUT infos client → paiement doit échouer
    res = client.put(f"/order/{order_id}", json={
        "credit_card": {
            "name": "John Doe", "number": "4242424242424242",
            "expiration_year": 2028, "expiration_month": 12, "cvv": "123"
        }
    })
    assert res.status_code == 422
    assert res.get_json()["errors"]["order"]["code"] == "missing-fields"


def test_pay_order_not_found(client):
    res = client.put("/order/99999", json={
        "credit_card": {
            "name": "John Doe", "number": "4242424242424242",
            "expiration_year": 2028, "expiration_month": 12, "cvv": "123"
        }
    })
    assert res.status_code == 404