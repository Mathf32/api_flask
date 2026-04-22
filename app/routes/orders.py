from flask import Blueprint, jsonify, request
from app.database.db import (
    Product, Order, OrderProduct, ShippingInformation, CreditCard, Transaction,
    TAX_RATES, create_order, update_order_info, db
)
from app.database.db_redis import cache_order, get_cached_order
from app.routes.shops import pay_order, _build_transaction_dict
from peewee import DoesNotExist
from rq import Queue
from redis import Redis
import os

orders_bp = Blueprint("orders", __name__)


def _build_order_response(order: Order) -> dict:
    """Construit le dict complet d'une commande depuis Postgres."""

    order_products = OrderProduct.select().where(OrderProduct.order == order)
    products_list = [
        {"id": op.product_id, "quantity": op.quantity}
        for op in order_products
    ]

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

    return {
        "order": {
            "id": order.id,
            "total_price": float(order.total_price),
            "total_price_tax": float(order.total_price_tax) if order.total_price_tax is not None else None,
            "email": order.email,
            "credit_card": safe(credit_card, ["name", "first_digits", "last_digits", "expiration_year", "expiration_month"]),
            "shipping_information": safe(shipping_info, ["country", "address", "postal_code", "city", "province"]),
            "paid": bool(order.paid),
            "transaction": _build_transaction_dict(transaction),
            "products": products_list,
            "shipping_price": float(order.shipping_price),
        }
    }


@orders_bp.post("/order")
def create_order_route():
    data = request.get_json(silent=True) or {}

    # Nouveau format: {"products": [...]}
    # Ancien format (rétrocompat): {"product": {...}} → converti en liste
    products_data = data.get("products")
    if not products_data:
        product_data = data.get("product")
        if product_data:
            products_data = [product_data]

    if not products_data:
        return jsonify({
            "errors": {
                "product": {
                    "code": "missing-fields",
                    "name": "La création d'une commande nécessite au moins un produit"
                }
            }
        }), 422

    validated = []
    for item in products_data:
        product_id = item.get("id")
        quantity = item.get("quantity")

        if product_id is None or quantity is None:
            return jsonify({
                "errors": {
                    "product": {
                        "code": "missing-fields",
                        "name": "Chaque produit doit avoir un id et une quantité"
                    }
                }
            }), 422

        try:
            product_id = int(product_id)
            quantity = int(quantity)
        except (ValueError, TypeError):
            return jsonify({
                "errors": {"product": {"code": "missing-fields", "name": "Le produit et la quantité doivent être des entiers"}}
            }), 422

        if quantity < 1:
            return jsonify({
                "errors": {"product": {"code": "missing-fields", "name": "La quantité doit être >= 1"}}
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

        validated.append({"id": product_id, "quantity": quantity})

    order = create_order(validated)

    response = jsonify({})
    response.status_code = 302
    response.headers["Location"] = f"/order/{order.id}"
    return response


@orders_bp.get("/order/<int:order_id>")
def get_order(order_id: int):
    # 1. Vérifier Redis en premier (seulement les commandes payées sont en cache)
    #    Si trouvé → retourner directement sans toucher Postgres
    cached = get_cached_order(order_id)
    if cached is not None:
        return jsonify(cached), 200
        

    # 2. Chercher dans Postgres
    try:
        order = Order.get_by_id(order_id)
    except DoesNotExist:
        return jsonify({
            "errors": {"order": {"code": "not-found", "name": "La commande demandée n'existe pas"}}
        }), 404

    # 3. Si le paiement est en cours → 202 Accepted sans corps
    if order.payment_pending:
        return "", 202

    # 4. Retourner la commande normalement
    return jsonify(_build_order_response(order)), 200


@orders_bp.put("/order/<int:order_id>")
def put_order(order_id: int):
    data = request.get_json(silent=True) or {}

    # Cas paiement
    credit_card_data = data.get("credit_card")
    if credit_card_data:
        order = Order.get_or_none(Order.id == order_id)
        if not order:
            return jsonify({"errors": {"order": {"code": "not-found", "name": "Commande introuvable"}}}), 404

        if order.paid:
            return jsonify({"errors": {"order": {"code": "already-paid", "name": "La commande a déjà été payée."}}}), 422

        if not order.email or not order.shipping_information_id:
            return jsonify({
                "errors": {"order": {"code": "missing-fields", "name": "Les informations du client sont nécessaires"}}
            }), 422

        if order.payment_pending:
            return jsonify({"errors": {"order": {"code": "conflict", "name": "Un paiement est déjà en cours"}}}), 409

        # Enqueue le paiement en arrière-plan via RQ
        redis_conn = Redis.from_url(os.getenv("REDIS_URL", "redis://localhost"))
        q = Queue(connection=redis_conn)
        q.enqueue(pay_order, order_id, credit_card_data)

        order.payment_pending = True
        order.save()

        return "", 202

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

    order = Order.get_or_none(Order.id == order_id)
    if not order:
        return jsonify({
            "errors": {"order": {"code": "not-found", "name": "La commande demandée n'existe pas"}}
        }), 404

    # Vérifier que la commande n'est pas déjà payée ou en cours de paiement
    if order.paid:
        return jsonify({"errors": {"order": {"code": "conflict", "name": "Impossible de modifier cette commande : elle est déjà payée"}}}), 409

    if order.payment_pending:
        return jsonify({"errors": {"order": {"code": "conflict", "name": "Impossible de modifier cette commande : un paiement est en cours"}}}), 409

    updated = update_order_info(order_id, email, shipping_data)
    if updated is None:
        return jsonify({
            "errors": {"order": {"code": "not-found", "name": "La commande demandée n'existe pas"}}
        }), 404

    order = Order.get_by_id(order_id)
    return jsonify(_build_order_response(order)), 200
