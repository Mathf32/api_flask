from flask import Blueprint, jsonify, request, url_for
from app.database.db import (
    Product, Order, ShippingInformation, CreditCard, Transaction,
    TAX_RATES, create_order, update_order_info, db
)
from app.routes.shops import pay_order
from peewee import DoesNotExist

orders_bp = Blueprint("orders", __name__)


def _build_order_response(order: Order) -> dict:
    """Construit le dict complet d'une commande selon le format du devis."""
    try:
        product = Product.get_by_id(order.product_id)
    except DoesNotExist:
        product = None

    shipping_info = None
    if order.shipping_information_id:
        try:
            shipping_info = ShippingInformation.get_by_id(order.shipping_information_id)
        except DoesNotExist:
            pass

    credit_card = None
    if order.credit_card_id:
        try:
            credit_card = CreditCard.get_by_id(order.credit_card_id)
        except DoesNotExist:
            pass

    transaction = None
    if order.transaction_id:
        try:
            transaction = Transaction.get_by_id(order.transaction_id)
        except DoesNotExist:
            pass

    def safe(obj, fields):
        if obj is None:
            return {}
        return {f: getattr(obj, f) for f in fields}

    # Calcul prix et shipping en temps réel depuis le produit
    qty = int(order.product_quantity or 1)
    total_price = round(float(product.price) * qty, 2) if product else float(order.total_price)

    # Shipping selon poids total
    total_weight = (product.weight * qty) if product else 0
    if total_weight <= 500:
        shipping_price = 5.0
    elif total_weight < 2000:
        shipping_price = 10.0
    else:
        shipping_price = 25.0

    # Taxes
    total_price_tax = None
    if shipping_info:
        province = (shipping_info.province or "").strip().upper()
        tax_rate = TAX_RATES.get(province, 0.0)
        total_price_tax = round(total_price * (1 + tax_rate), 2)

    return {
        "order": {
            "id": order.id,
            "total_price": total_price,
            "total_price_tax": total_price_tax,
            "email": order.email,
            "credit_card": safe(credit_card, ["name", "first_digits", "last_digits", "expiration_year", "expiration_month"]),
            "shipping_information": safe(shipping_info, ["country", "address", "postal_code", "city", "province"]),
            "paid": bool(order.paid),
            "transaction": safe(transaction, ["id", "success", "amount_charged"]),
            "product": {
                "id": product.id if product else order.product_id,
                "quantity": qty,
            },
            "shipping_price": shipping_price,
        }
    }


@orders_bp.post("/order")
def create_order_route():
    data = request.get_json(silent=True) or {}

    product_data = data.get("product")
    if not product_data:
        return jsonify({
            "errors": {
                "product": {
                    "code": "missing-fields",
                    "name": "La création d'une commande nécessite un produit et une quantité"
                }
            }
        }), 422

    product_id = product_data.get("id")
    quantity = product_data.get("quantity")

    if product_id is None or quantity is None:
        return jsonify({
            "errors": {
                "product": {
                    "code": "missing-fields",
                    "name": "La création d'une commande nécessite un produit et une quantité"
                }
            }
        }), 422

    try:
        quantity = int(quantity)
    except (ValueError, TypeError):
        return jsonify({
            "errors": {"product": {"code": "missing-fields", "name": "La quantité doit être un entier"}}
        }), 422

    if quantity < 1:
        return jsonify({
            "errors": {"product": {"code": "missing-fields", "name": "La quantité doit être supérieure à 0"}}
        }), 422

    product = Product.get_or_none(Product.id == product_id)
    if product is None:
        return jsonify({
            "errors": {
                "product": {
                    "code": "invalid-product",
                    "name": "Le produit demandé n'existe pas"
                }
            }
        }), 422

    if not product.in_stock:
        return jsonify({
            "errors": {
                "product": {
                    "code": "out-of-inventory",
                    "name": "Le produit demandé n'est pas en inventaire"
                }
            }
        }), 422

    order = create_order(int(product_id), quantity)

    # 302 avec header Location selon le devis
    response = jsonify({})
    response.status_code = 302
    response.headers["Location"] = f"/order/{order.id}"
    return response


@orders_bp.get("/order/<int:order_id>")
def get_order(order_id: int):
    try:
        order = Order.get_by_id(order_id)
    except DoesNotExist:
        return jsonify({
            "errors": {"order": {"code": "not-found", "name": "La commande demandée n'existe pas"}}
        }), 404

    return jsonify(_build_order_response(order)), 200


@orders_bp.put("/order/<int:order_id>")
def put_order(order_id: int):
    data = request.get_json(silent=True) or {}

    # Cas paiement
    credit_card_data = data.get("credit_card")
    if credit_card_data:
        result, status = pay_order(order_id, credit_card_data)
        if status != 200:
            return jsonify(result), status

        # Construire la réponse complète après paiement
        try:
            order = Order.get_by_id(order_id)
        except DoesNotExist:
            return jsonify({"errors": {"order": {"code": "not-found", "name": "Commande introuvable"}}}), 404

        return jsonify(_build_order_response(order)), 200

    # Cas mise à jour infos client
    order_payload = data.get("order")
    if not order_payload:
        return jsonify({"errors": {"order": {"code": "missing-fields", "name": "Payload invalide"}}}), 422

    email = order_payload.get("email")
    shipping_data = order_payload.get("shipping_information")

    if not email or not shipping_data:
        return jsonify({
            "errors": {"order": {"code": "missing-fields", "name": "L'email et l'adresse sont requis"}}
        }), 422

    # Vérifier que la commande existe
    order = Order.get_or_none(Order.id == order_id)
    if not order:
        return jsonify({
            "errors": {"order": {"code": "not-found", "name": "La commande demandée n'existe pas"}}
        }), 404

    updated = update_order_info(order_id, email, shipping_data)
    if updated is None:
        return jsonify({
            "errors": {"order": {"code": "not-found", "name": "La commande demandée n'existe pas"}}
        }), 404

    # Recharger depuis DB pour avoir shipping_information_id à jour
    order = Order.get_by_id(order_id)
    return jsonify(_build_order_response(order)), 200