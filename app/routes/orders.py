from flask import Blueprint,jsonify, request
from app.services.factory import Factory
from app.models.model import Product,Order

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

    products = Product.GetProductList()
    data = request.get_json()

    product_id = data["product"]["id"]
    quantity = data["product"]["quantity"]

    if not any(p.id == product_id for p in products):
        return jsonify({
            "errors": {
                "product": {
                    "code": "invalid-ID",
                    "name": "La création d'une commande nécessite un produit valide"
                }
            }
        }), 400
    
    if product_id is None:
        return jsonify({
            "errors": {
                "product": {
                    "code": "missing-fields",
                    "name": "La création d'une commande nécessite un produit"
                }
            }
        }), 400
    
    product = next((p for p in products if p.id == product_id), None)
    
    if not product.in_stock:
        return {
            "errors": {
                "product": {
                    "code": "insufficient-stock",
                    "name": "Quantité insuffisante en stock"
                }
            }
        }, 400


    Factory.create_command(product_id,quantity,product)

    return {"products":data}