from app import create_app
from app.services.factory import Factory
from app.models.model import Product
from dotenv import load_dotenv
import os


app = create_app()

if __name__ == "__main__":
    load_dotenv()
    products = Product.GetProductList()
    Factory.init_db()
    Factory.save_products(products)
    app.run(debug=True)