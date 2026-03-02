from flask import Flask
import app.database.db as db
from app.database.db import Product
from app.routes.products import products_bp
from app.routes.orders import orders_bp
from flasgger import Swagger
import requests
import json



def create_app():
    app = Flask(__name__)
    db.setup_db()

    # AJOUTE CECI ICI :
    @app.cli.command("init-db")
    def init_db_command():
        db.init_db() # Crée les tables
        products = GetProductList()
        db.save_products(products)
        print("Base de données initialisée !")

    app.register_blueprint(products_bp)
    app.register_blueprint(orders_bp)
    Swagger(app)
    return app

def GetProductList():
        response = requests.get("https://dimensweb.uqac.ca/~jgnault/shops/products/")
        data = response.json()
        
        products_data = data["products"]
        return products_data