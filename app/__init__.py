from flask import Flask
import app.database.db as db
from app.routes.products import products_bp
from app.routes.orders import orders_bp
from urllib import request
import json


def create_app():
    app = Flask(__name__)
    db.setup_db()

    @app.cli.command("init-db")
    def init_db_command():
        db.init_db() # Crée les tables
        products = GetProductList()
        db.save_products(products)
        print("Base de données initialisée !")

    app.register_blueprint(products_bp)
    app.register_blueprint(orders_bp)
    return app

def GetProductList():
        with request.urlopen("https://dimensweb.uqac.ca/~jgnault/shops/products/") as response:
            data = json.loads(response.read().decode())
        
        products_data = data["products"]
        return products_data