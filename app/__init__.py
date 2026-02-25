from flask import Flask
from app.services.factory import Factory
from app.routes.products import products_bp
from app.routes.orders import orders_bp
from flasgger import Swagger
from dotenv import load_dotenv
import os


def create_app():
    app = Flask(__name__)

    #Pour utiliser swagger utilisez le path /apidocs
    

    Factory.init_db()

    app.register_blueprint(products_bp)
    app.register_blueprint(orders_bp)
   

    load_dotenv()

    Swagger(app)

    return app