from flask import Flask, render_template
import app.database.db as db
from app.routes.products import products_bp
from app.routes.orders import orders_bp
import requests
from app.database.db import Product
from rq import SimpleWorker
from redis import Redis
import os


def create_app():
    app = Flask(__name__)
    db.setup_db()

    @app.route("/ui")
    def home():
        products = Product.select()
        return render_template("index.html", products=products)


    @app.cli.command("init-db")
    def init_db_command():
        db.init_db()
        products = _get_product_list()
        db.save_products(products)
        print("Base de données initialisée !")

    @app.cli.command("worker")
    def worker():
        redis_conn = Redis.from_url(os.getenv("REDIS_URL", "redis://localhost"))
        worker = SimpleWorker(["default"], connection=redis_conn)
        worker.work()

    app.register_blueprint(products_bp)
    app.register_blueprint(orders_bp)
    return app




def _get_product_list():
    response = requests.get("https://dimensweb.uqac.ca/~jgnault/shops/products/")
    return response.json()["products"]