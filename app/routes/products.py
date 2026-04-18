from flask import Blueprint, jsonify
from app.database.db import Product

products_bp = Blueprint("products", __name__)


@products_bp.get("/")
def get_products():
    return jsonify({"products": [p.__data__ for p in Product.select()]})