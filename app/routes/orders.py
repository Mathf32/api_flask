from flask import Blueprint, jsonify, request
from app.database.db import (
    Product, Order, OrderProduct, ShippingInformation, CreditCard, Transaction,
    TAX_RATES, create_order, update_order_info, db
)
from app.database.db_redis import cache_order,get_cache_order
from app.routes.shops import pay_order
from peewee import DoesNotExist
from rq import Queue
from redis import Redis
import os

orders_bp = Blueprint("orders", __name__)


def _build_order_response(order) -> dict:
    """Construit le dict complet d'une commande (Order ou dict)."""

    # 🔹 Normaliser accès aux champs
    if isinstance(order, dict):
        order_id = order["id"]
        shipping_information_id = order.get("shipping_information")
        credit_card_id = order.get("credit_card")
        transaction_id = order.get("transaction")

        total_price = order["total_price"]
        total_price_tax = order.get("total_price_tax")
        email = order.get("email")
        paid = order.get("paid")
        shipping_price = order["shipping_price"]

    else:
        order_id = order.id
        shipping_information_id = order.shipping_information_id
        credit_card_id = order.credit_card_id
        transaction_id = order.transaction_id

        total_price = order.total_price
        total_price_tax = order.total_price_tax
        email = order.email
        paid = order.paid
        shipping_price = order.shipping_price

    # 🔹 Produits
    order_products = OrderProduct.select().where(OrderProduct.order == order_id)
    products_list = [
        {"id": op.product_id, "quantity": op.quantity}
        for op in order_products
    ]

    # 🔹 Relations
    shipping_info = None
    if shipping_information_id:
        try:
            shipping_info = ShippingInformation.get_by_id(shipping_information_id)
        except DoesNotExist:
            pass

    credit_card = None
    if credit_card_id:
        try:
            credit_card = CreditCard.get_by_id(credit_card_id)
        except DoesNotExist:
            pass

    transaction = None
    if transaction_id:
        try:
            transaction = Transaction.get_by_id(transaction_id)
        except DoesNotExist:
            pass

    def safe(obj, fields):
        if obj is None:
            return {}
        return {f: getattr(obj, f) for f in fields}

    return {
        "order": {
            "id": order_id,
            "total_price": float(total_price),
            "total_price_tax": float(total_price_tax) if total_price_tax is not None else None,
            "email": email,
            "credit_card": safe(credit_card, ["name", "first_digits", "last_digits", "expiration_year", "expiration_month"]),
            "shipping_information": safe(shipping_info, ["country", "address", "postal_code", "city", "province"]),
            "paid": bool(paid),
            "transaction": safe(transaction, ["id", "success", "amount_charged"]),
            "products": products_list,
            "shipping_price": float(shipping_price),
        }
    }



def create_order(products, email=None, credit_card=None, shipping_information=None, paid=False):
    shipping_info_obj = None
    if shipping_information:
        shipping_info_obj = ShippingInformation.create(
            country=shipping_information.get("country"),
            address=shipping_information.get("address"),
            postal_code=shipping_information.get("postal_code"),
            city=shipping_information.get("city"),
            province=shipping_information.get("province"),
        )

    credit_card_obj = None
    if credit_card:
        credit_card_obj = CreditCard.create(
            name=credit_card.get("name"),
            first_digits=credit_card.get("first_digits"),
            last_digits=credit_card.get("last_digits"),
            expiration_year=credit_card.get("expiration_year"),
            expiration_month=credit_card.get("expiration_month"),
        )

    total_price = 0
    for item in products:
        product = Product.get_by_id(item["id"])
        total_price += float(product.price) * int(item["quantity"])

    shipping_price = 5.0

    order = Order.create(
        email=email,
        paid=False,
        total_price=total_price,
        total_price_tax=None,
        shipping_price=shipping_price,
        shipping_information=shipping_info_obj,
        credit_card=credit_card_obj,
        transaction=None
    )

    for item in products:
        OrderProduct.create(
            order=order,
            product=item["id"],
            quantity=item["quantity"]
        )

    return order





@orders_bp.post("/order")
def create_order_route():
    data = request.get_json(silent=True)

    if data:
        products_data = data.get("products")
        if not products_data:
            product_data = data.get("product")
            if product_data:
                products_data = [product_data]

        email = data.get("email")
        paid = bool(data.get("paid", False))

        credit_card = data.get("credit_card") or {}
        shipping_information = data.get("shipping_information") or {}

    else:
        product_ids = request.form.getlist("product_id[]")
        quantities = request.form.getlist("quantity[]")

        products_data = []
        for product_id, quantity in zip(product_ids, quantities):
            products_data.append({
                "id": product_id,
                "quantity": quantity
            })

        email = request.form.get("email")
        paid = request.form.get("paid") == "on"

        credit_card = {
            "name": request.form.get("credit_card_name"),
            "first_digits": request.form.get("credit_card_first_digits"),
            "last_digits": request.form.get("credit_card_last_digits"),
            "expiration_year": request.form.get("expiration_year"),
            "expiration_month": request.form.get("expiration_month"),
        }

        shipping_information = {
            "country": request.form.get("country"),
            "address": request.form.get("address"),
            "postal_code": request.form.get("postal_code"),
            "city": request.form.get("city"),
            "province": request.form.get("province"),
        }

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
                        "name": f"Chaque produit doit avoir un id et une quantité | Produit {product_id}"
                    }
                }
            }), 422

        try:
            product_id = int(product_id)
            quantity = int(quantity)
        except (ValueError, TypeError):
            return jsonify({
                "errors": {
                    "product": {
                        "code": "missing-fields",
                        "name": "Le produit et la quantité doivent être des entiers"
                    }
                }
            }), 422

        if quantity < 1:
            return jsonify({
                "errors": {
                    "product": {
                        "code": "missing-fields",
                        "name": "La quantité doit être >= 1"
                    }
                }
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
                        "name": f"Le produit demandé n'est pas en inventaire | Produit {product_id}"
                    }
                }
            }), 422

        validated.append({
            "id": product_id,
            "quantity": quantity
        })

    order = create_order(
        validated,
        email=email,
        credit_card=credit_card,
        shipping_information=shipping_information,
        paid=paid
    )

    cache_order(order)

    response = jsonify({})
    response.status_code = 302
    response.headers["Location"] = f"/order/{order.id}"
    return response






@orders_bp.get("/order/<int:order_id>")
def get_order(order_id: int):
    
    order = get_cache_order(order_id)
    print(order["payment_pending"])
    if order is None:
        print("Pas trouver")
        try:
            order = Order.get_by_id(order_id)
            cache_order(order)
            if(order.payment_pending == True):
                return {
                    "errors": {"order": {"code": "Conflict"}}
                }, 409
        except DoesNotExist:
            return jsonify({
                "errors": {"order": {"code": "not-found", "name": "La commande demandée n'existe pas"}}
            }), 404

    if(order["payment_pending"] == True):
            return {
                "errors": {"order": {"code": "Conflict"}}
            }, 409
    
    return jsonify(_build_order_response(order)), 200


@orders_bp.put("/order/<int:order_id>")
def put_order(order_id: int):
    data = request.get_json(silent=True) or {}

    # Cas paiement
    credit_card_data = data.get("credit_card")
    if credit_card_data:
        order = Order.get_or_none(Order.id == order_id)
        if not order:
            return {"errors": {"order": {"code": "not-found", "name": "Commande introuvable"}}}, 404

        if order.paid:
            return {"errors": {"order": {"code": "already-paid", "name": "La commande a déjà été payée."}}}, 422

        if not order.email or not order.shipping_information_id:
            return {
                "errors": {"order": {"code": "missing-fields", "name": "Les informations du client sont nécessaires"}}
            }, 422
        
        if(order.payment_pending == True):
            return {
                "errors": {"order": {"code": "Conflict"}}
            }, 409
        
        
        redis_conn = Redis.from_url(os.getenv("REDIS_URL", "redis://localhost"))
        q = Queue(connection=redis_conn)
        job = q.enqueue(pay_order, order_id, credit_card_data)
        print("JOB ID:", job.id)
        order.payment_pending = 1
        order.save()
        cache_order(order)
        
        #if status != 200:
         #   return jsonify(result), status

        # Construire la réponse complète après paiement
        #try:
         #   order = Order.get_by_id(order_id)
        #except DoesNotExist:
         #   return jsonify({"errors": {"order": {"code": "not-found", "name": "Commande introuvable"}}}), 404

        #return jsonify(_build_order_response(order)), 200
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