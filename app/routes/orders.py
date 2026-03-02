from flask import Blueprint,jsonify, request
from app.database.db import Product,Order
import app.database.db as db
from playhouse.shortcuts import model_to_dict

from app.routes.shops import pay_order

orders_bp = Blueprint("orders", __name__)

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

