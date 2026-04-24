"""
Tests d'intégration — à lancer quand l'app tourne (docker-compose up).

Usage :
    pytest tests/integration/test_integration.py -v

URL de base configurable via la variable d'environnement BASE_URL :
    BASE_URL=http://localhost:5000 pytest tests/integration/test_integration.py
"""
import http.client
import json
import os
import time

import pytest

BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")
_host = BASE_URL.replace("http://", "").split(":")[0]
_port = int(BASE_URL.split(":")[-1]) if ":" in BASE_URL.replace("http://", "") else 80

# Données de test standard
SHIPPING = {
    "country": "Canada",
    "address": "555 Boulevard de l'Université",
    "postal_code": "G7H 2B1",
    "city": "Saguenay",
    "province": "QC",
}
CARD_VALID    = {"name": "John Doe", "number": "4242 4242 4242 4242", "expiration_year": 2027, "expiration_month": 9, "cvv": "123"}
CARD_DECLINED = {"name": "John Doe", "number": "4000 0000 0000 0002", "expiration_year": 2027, "expiration_month": 9, "cvv": "123"}


# ---------------------------------------------------------------------------
# Helpers HTTP — http.client ne suit pas les redirections automatiquement
# ---------------------------------------------------------------------------

def _request(method: str, path: str, payload: dict | None = None) -> tuple[int, dict | str, dict]:
    """Retourne (status_code, body_parsed, headers). body_parsed est un dict si JSON, sinon str."""
    conn = http.client.HTTPConnection(_host, _port, timeout=20)
    headers = {}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=body, headers=headers)
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8")
    conn.close()
    try:
        parsed = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        parsed = raw  # HTML d'erreur, etc.
    return resp.status, parsed, dict(resp.getheaders())


def get(path):
    status, body, _ = _request("GET", path)
    return status, body

def post(path, data):
    status, body, _ = _request("POST", path, data)
    return status, body

def put(path, data):
    status, body, _ = _request("PUT", path, data)
    return status, body


def _get_valid_product_id() -> int:
    """Récupère le premier produit en stock depuis l'app."""
    status, body = get("/")
    assert status == 200, f"GET / a retourné {status}"
    products = body.get("products", [])
    in_stock = [p for p in products if p.get("in_stock")]
    assert in_stock, "Aucun produit en stock disponible"
    return in_stock[0]["id"]


def create_order(product_id: int | None = None, quantity: int = 1) -> int:
    """Crée une commande et retourne son id via le header Location."""
    if product_id is None:
        product_id = _get_valid_product_id()
    status, body, headers = _request("POST", "/order", {"products": [{"id": product_id, "quantity": quantity}]})
    assert status == 302, f"POST /order attendu 302, reçu {status} — body: {body}"
    location = headers.get("Location", "")
    assert location, "Pas de header Location dans la réponse 302"
    return int(location.split("/")[-1])


def fill_order(order_id: int, email: str = "integration@test.com", province: str = "QC"):
    return put(f"/order/{order_id}", {
        "order": {
            "email": email,
            "shipping_information": {**SHIPPING, "province": province},
        }
    })


def wait_for_payment(order_id: int, timeout: int = 15) -> dict:
    """Poll GET /order/<id> jusqu'à ce que le paiement soit traité (max timeout secondes)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        status, body = get(f"/order/{order_id}")
        if status == 200:
            return body
        if status == 202:
            time.sleep(1)
            continue
        pytest.fail(f"GET /order/{order_id} a retourné {status}: {body}")
    pytest.fail(f"Paiement non traité après {timeout}s (toujours 202)")


# ---------------------------------------------------------------------------
# Vérification que l'app tourne
# ---------------------------------------------------------------------------

def test_app_is_running():
    status, body = get("/")
    assert status == 200, f"L'app ne répond pas sur {BASE_URL} (status {status})"
    assert "products" in body, "La route GET / ne retourne pas de produits"


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------

def test_products_list_not_empty():
    status, body = get("/")
    assert status == 200
    products = body.get("products", [])
    assert len(products) > 0
    first = products[0]
    assert "id" in first
    assert "name" in first
    assert "price" in first


# ---------------------------------------------------------------------------
# POST /order
# ---------------------------------------------------------------------------

def test_create_order_redirects():
    product_id = _get_valid_product_id()
    status, body, headers = _request("POST", "/order", {"products": [{"id": product_id, "quantity": 1}]})
    assert status == 302, f"Attendu 302, reçu {status}"
    assert "Location" in headers
    assert "/order/" in headers["Location"]


def test_create_order_invalid_product():
    status, body = post("/order", {"products": [{"id": 99999, "quantity": 1}]})
    assert status == 422
    assert body["errors"]["product"]["code"] == "invalid-product"


def test_create_order_missing_fields():
    status, body = post("/order", {})
    assert status == 422
    assert body["errors"]["product"]["code"] == "missing-fields"


def test_create_order_out_of_stock():
    _, body = get("/")
    out_of_stock = next((p for p in body["products"] if not p.get("in_stock")), None)
    if out_of_stock is None:
        pytest.skip("Aucun produit hors-stock disponible")
    status, body = post("/order", {"products": [{"id": out_of_stock["id"], "quantity": 1}]})
    assert status == 422
    assert body["errors"]["product"]["code"] == "out-of-inventory"


# ---------------------------------------------------------------------------
# GET /order/<id>
# ---------------------------------------------------------------------------

def test_get_order_structure():
    order_id = create_order()
    status, body = get(f"/order/{order_id}")
    assert status == 200
    order = body["order"]
    assert order["id"] == order_id
    assert order["paid"] is False
    assert isinstance(order["products"], list)
    assert len(order["products"]) == 1
    assert isinstance(order["shipping_information"], dict)
    assert isinstance(order["credit_card"], dict)
    assert isinstance(order["transaction"], dict)


def test_get_order_not_found():
    status, body = get("/order/99999999")
    assert status == 404
    assert body["errors"]["order"]["code"] == "not-found"


# ---------------------------------------------------------------------------
# PUT /order/<id> — infos client
# ---------------------------------------------------------------------------

def test_put_client_info():
    order_id = create_order()
    status, body = fill_order(order_id)
    assert status == 200
    order = body["order"]
    assert order["email"] == "integration@test.com"
    assert order["shipping_information"]["province"] == "QC"
    assert order["total_price_tax"] is not None


def test_put_client_info_taxes_qc():
    order_id = create_order()
    status, body = fill_order(order_id, province="QC")
    assert status == 200
    order = body["order"]
    expected = round(order["total_price"] * 1.15, 2)
    assert abs(order["total_price_tax"] - expected) < 0.01


def test_put_missing_email():
    order_id = create_order()
    status, body = put(f"/order/{order_id}", {
        "order": {"shipping_information": SHIPPING}
    })
    assert status == 422


# ---------------------------------------------------------------------------
# PUT /order/<id> — paiement (requiert le worker)
# ---------------------------------------------------------------------------

def test_pay_order_valid_card():
    order_id = create_order()
    fill_order(order_id)
    status, _ = put(f"/order/{order_id}", {"credit_card": CARD_VALID})
    assert status == 202, f"PUT paiement attendu 202, reçu {status}"
    body = wait_for_payment(order_id)
    order = body["order"]
    assert order["paid"] is True
    assert order["transaction"]["success"] is True
    assert order["transaction"]["error"] == {}
    assert isinstance(order["transaction"]["amount_charged"], int)


def test_pay_order_declined_card():
    order_id = create_order()
    fill_order(order_id)
    status, _ = put(f"/order/{order_id}", {"credit_card": CARD_DECLINED})
    assert status == 202
    body = wait_for_payment(order_id)
    order = body["order"]
    assert order["paid"] is False
    assert order["transaction"]["success"] is False
    assert order["transaction"]["error"]["code"] == "card-declined"


def test_pay_already_paid():
    order_id = create_order()
    fill_order(order_id)
    put(f"/order/{order_id}", {"credit_card": CARD_VALID})
    wait_for_payment(order_id)
    status, body = put(f"/order/{order_id}", {"credit_card": CARD_VALID})
    assert status == 422
    assert body["errors"]["order"]["code"] == "already-paid"


def test_pay_missing_client_info():
    order_id = create_order()
    status, body = put(f"/order/{order_id}", {"credit_card": CARD_VALID})
    assert status == 422
    assert body["errors"]["order"]["code"] == "missing-fields"
