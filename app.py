from flask import Flask,jsonify, request
from flasgger import Swagger
from model import Product
from factory import Factory 

app = Flask(__name__)

#Pour utiliser swagger utilisez le path /apidocs
swagger = Swagger(app)

@app.get("/")
def get():
    return {"products":products}

@app.post("/order")
def order():
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

if __name__ == "__main__":

    products = Product.GetProductList()
    Factory.init_db()
    Factory.save_products(products)
    app.run(debug=True)

