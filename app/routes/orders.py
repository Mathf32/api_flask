from flask import Blueprint,jsonify, request
from app.database.db import Product,Order
import app.database.db as db
from playhouse.shortcuts import model_to_dict

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
    data = request.get_json()
    order_transformed = data["order"]

    db.update_order(order_transformed,order_id)

    order = Order.get_or_none(Order.id == order_id)

    return {"Commande modifié": model_to_dict(order,backrefs=False, recurse=True)}


