from flask import Blueprint,jsonify, request
from app.database.db import Product,Order
import app.database.db as db
from playhouse.shortcuts import model_to_dict
from peewee import DoesNotExist

from app.routes.shops import pay_order

orders_bp = Blueprint("orders", __name__)

TAX_RATES = {
    "QC": 0.15,
    "ON": 0.13,
    "AB": 0.05,
    "BC": 0.12,
    "NS": 0.14,
}

def _shipping_price_cents(total_weight_g: int) -> int:
    if total_weight_g <= 500:
        return 500
    if total_weight_g < 2000:
        return 1000
    return 2500

def _safe_dict(model_obj) -> dict:
    # Retourne {} si None (comme les exemples du devis)
    return model_obj.__data__.copy() if model_obj is not None else {}


@orders_bp.post("/order")
def order():
    """
    Création d'une commande
    ---
    tags:
      - Orders
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required:
            - product
          properties:
            product:
              type: object
              required:
                - id
                - quantity
              properties:
                id:
                  type: integer
                  example: 123
                quantity:
                  type: integer
                  example: 2
    responses:
      201:
        description: Commande créée
      400:
        description: Erreur de validation
    """

    data = request.get_json()
    data_transform = data["product"]

    product_id = data["product"]["id"]
    quantity = data["product"]["quantity"]

    verif_produit = Product.get_or_none(Product.id == product_id)

    if verif_produit == None:
        return jsonify({
            "errors": {
                "product": {
                    "code": "invalid-ID",
                    "name": "La création d'une commande nécessite un produit valide"
                }
            }
        }), 400
    
    if product_id is None or quantity is None:
        return jsonify({
            "errors": {
                "product": {
                    "code": "missing-fields",
                    "name": "La création d'une commande nécessite un produit et une quantité"
                }
            }
        }), 400
    
    
    
    if not verif_produit.in_stock:
        return {
            "errors": {
                "product": {
                    "code": "insufficient-stock",
                    "name": "Quantité insuffisante en stock"
                }
            }
        }, 400


    new_order = db.create_order(data_transform)

    return {"Nouvelle Commande ": model_to_dict(new_order)}


@orders_bp.put("/order/<int:order_id>")
def put_order(order_id):
    """
        Mise à jour ou Paiement d'une commande
        ---
        tags: [Orders]
        parameters:
          - in: body
            name: body
            schema:
              type: object
              properties:
                order:
                  type: object
                  properties:
                    email: {type: string}
                    shipping_information: {type: object}
                credit_card:
                  type: object
                  properties:
                    name: {type: string}
                    number: {type: string}
                    expiration_year: {type: integer}
                    expiration_month: {type: integer}
                    cvv: {type: string}
        """
    data = request.get_json()

    # 1. CAS PAIEMENT : Si 'credit_card' est présent
    if "credit_card" in data:
        result, status = pay_order(order_id, data["credit_card"])
        return jsonify(result), status

    # 2. CAS MISE À JOUR : Si 'order' est présent
    order_transformed = data.get("order")
    if order_transformed:
        # On met à jour les infos (adresse, email, taxes)
        db.update_order(order_transformed, order_id)

        # On DOIT récupérer l'objet mis à jour pour le retourner au client
        order = Order.get_or_none(Order.id == order_id)

        if order:
            return jsonify({"order": model_to_dict(order)}), 200
        else:
            return jsonify({"error": "Order not found"}), 404

    return jsonify({"error": "Invalid request"}), 400







@orders_bp.get("/order/<int:order_id>")
def get_order(order_id: int):
    """
    Get order by id
    ---
    tags:
      - Orders
    parameters:
      - name: order_id
        in: path
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Order found
      404:
        description: Order not found
    """
    try:
        order = Order.get_by_id(order_id)
    except DoesNotExist:
        # Le devis spécifie 404 pour une commande inexistante (au moins pour PUT),
        # mais c'est cohérent de faire pareil pour GET.
        return jsonify({"errors": {"order": {"code": "not-found", "name": "Commande inexistante"}}}), 404

    # Produit
    try:
        product = Product.get_by_id(order.product_id)
    except DoesNotExist:
        # Si DB corrompue / produit supprimé
        return jsonify({"errors": {"order": {"code": "invalid-product", "name": "Produit introuvable"}}}), 422

    qty = int(order.product_quantity or 0)
    if qty < 1:
        qty = 1  # sécurité

    total_price = int(product.price) * qty  # cents

    # Shipping info (si présente) pour calcul taxe
    shipping_info = None
    province = None
    if getattr(order, "shipping_information_id", None):
        shipping_info = ShippingInformation.get_by_id(order.shipping_information_id)
        province = (shipping_info.province or "").strip().upper()

    # Shipping calc (poids total)
    total_weight_g = int(product.weight) * qty
    shipping_price = _shipping_price_cents(total_weight_g)

    # Tax calc (si province connue, sinon 0)
    tax_rate = TAX_RATES.get(province, 0.0)
    total_price_tax = total_price * (1.0 + tax_rate)

    credit_card = None
    if getattr(order, "credit_card_id", None):
        credit_card = CreditCard.get_by_id(order.credit_card_id)

    transaction = None
    if getattr(order, "transaction_id", None):
        transaction = Transaction.get_by_id(order.transaction_id)

    payload = {
        "order": {
            "id": order.id,
            "total_price": total_price,
            "total_price_tax": total_price_tax,
            "email": getattr(order, "email", None),
            "credit_card": _safe_dict(credit_card),
            "shipping_information": _safe_dict(shipping_info),
            "paid": bool(getattr(order, "paid", False)),
            "transaction": _safe_dict(transaction),
            "product": {
                "id": product.id,
                "quantity": qty,
            },
            "shipping_price": shipping_price,
        }
    }
    return jsonify(payload), 200