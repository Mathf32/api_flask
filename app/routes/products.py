
from app.database.db import Product
from flask import Blueprint,jsonify, request

products_bp = Blueprint("products", __name__)

@products_bp.get("/")
def get():
    """
    Liste des produits
    ---
    tags:
      - Products
    produces:
      - application/json
    responses:
      200:
        description: Liste des produits
        schema:
          type: object
          properties:
            products:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                    example: 1
                  name:
                    type: string
                    example: "Brown eggs"
                  type:
                    type: string
                    example: "dairy"
                  description:
                    type: string
                  image:
                    type: string
                  height:
                    type: integer
                  weight:
                    type: integer
                  price:
                    type: number
                  in_stock:
                    type: boolean
    """
    return {"products":[p.__data__ for p in Product.select()]}