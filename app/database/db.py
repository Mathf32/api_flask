# app.py (tout-en-un) — Peewee + SQLite
import os
from peewee import (
    Proxy,
    SqliteDatabase, Model,
    IntegerField, TextField, FloatField, BooleanField,
    AutoField, ForeignKeyField
)

import os

def load_dotenv(path=".env"):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.abspath(os.path.join(base_dir, "..", "..", path))

    print(env_path)

    with open(env_path) as f:
        for line in f:
            line = line.strip()
            
            if not line or line.startswith("#"):
                continue
            
            key, value = line.split("=", 1)
            os.environ[key] = value


load_dotenv()

db = Proxy()


class BaseModel(Model):
    class Meta:
        database = db


def setup_db(is_test = False):

    db_path = "products.db" 
    if(is_test == True):
        db_path = "test.db"

    if not db_path:
        raise Exception("La variable d'environnement 'db_path' est requise")

    real_db = SqliteDatabase(db_path)
    db.initialize(real_db)

def init_db():
    db.connect(reuse_if_open=True)
    db.create_tables([Product, Order, Transaction, CreditCard, ShippingInformation])
    db.close()

class Product(BaseModel):
    id = AutoField(primary_key=True)
    name = TextField()
    type = TextField()
    description = TextField()
    image = TextField()
    height = IntegerField()
    weight = IntegerField()
    price = FloatField()
    in_stock = BooleanField()
    class Meta:
        table_name = 'products'

class ShippingInformation(BaseModel):
    id = AutoField(primary_key=True)
    country = TextField()
    address = TextField()
    postal_code = TextField()
    city = TextField()
    province = TextField()

class CreditCard(BaseModel):
    id = AutoField(primary_key=True)
    name = TextField()
    first_digits = TextField()
    last_digits = TextField()
    expiration_year = IntegerField()
    expiration_month = IntegerField()

class Transaction(BaseModel):
    id = AutoField(primary_key=True)
    success = BooleanField()
    amount_charged = FloatField()


class Order(BaseModel):
    id = AutoField(primary_key=True)
    total_price = FloatField(default=0)
    total_price_tax = FloatField(default=0,null=True)
    email = TextField(null=True)
    credit_card = ForeignKeyField(CreditCard, backref="orders", null=True)             # JSON string
    shipping_information = ForeignKeyField(ShippingInformation, backref="orders", null=True)    # JSON string
    paid = BooleanField(default=False)
    transaction = ForeignKeyField(Transaction, backref="orders", null=True)              # JSON string
    product = ForeignKeyField(Product, backref="orders")
    product_quantity = IntegerField()
    shipping_price = FloatField(default=0)


def save_products(products: list[dict]):
    """
    products = [{"id":1, "name":"...", "type":"...", ...}, ...]
    """
    db.connect(reuse_if_open=True)
    with db.atomic():
        for p in products:
            Product.insert(p).on_conflict_replace().execute()
    db.close()

def create_order(requete: dict):
    """
    products = [{"id":1, "name":"...", "type":"...", ...}, ...]
    """

    product_id = int(requete["id"])
    quantity = int(requete["quantity"])
    product = Product.get_by_id(product_id)

    total = product.price * quantity
    shipping = 0

    if product.weight <= 500:
        shipping = 5
    elif product.weight < 2000:
        shipping = 10
    else:
        shipping = 25

    db.connect(reuse_if_open=True)
    with db.atomic():
        order = Order.create(
            total_price = total,
            total_price_tax = 0,
            product_quantity = quantity,
            product = product_id,
            email = None,
            credit_card = None,
            shipping_information = None,
            paid = False,
            transaction = None,
            shipping_price = shipping
        )
    db.close()

    return order


def update_order(request: dict, order_id):
    # On vérifie si shipping_information est présent avant de tenter de le créer
    shipping_data = request.get("shipping_information")

    if shipping_data:
        shipping_info = create_shippinginfo(shipping_data)
        if shipping_info == None:
            return {
            "errors": {
                "shipping": {
                    "code": "missing-fields", 
                    "name": "Il manque un ou plusieurs champs qui sont obligatoires",
                }
            }
        }, 422
    else:
        shipping_info = None

    db.connect(reuse_if_open=True)
    try:
        with db.atomic():
            order = Order.get_or_none(Order.id == order_id)
            if order is None:
                return None

            # On ne met à jour que ce qui est fourni
            if request.get("email"):
                order.email = request["email"]

            if shipping_info:
                order.shipping_information = shipping_info
                # Recalcul des taxes (QC = 15%, etc.)
                tax_rates = {
                    "QC": 1.15,
                    "ON": 1.13,
                    "AB": 1.05,
                    "BC": 1.12,
                    "NS": 1.14
                }
                tax_rate = tax_rates.get(shipping_info.province, 0)

                order.total_price_tax = float(int((order.total_price * tax_rate) * 100 + 0.5)) / 100.0

            order.save()
            return order
    finally:
        db.close()


def create_shippinginfo(shippinginfo: dict):
    required_fields = ["country", "address", "postal_code", "city", "province"]

    # Vérifier les champs manquants ou vides
    missing_fields = [
        field for field in required_fields
        if field not in shippinginfo or not shippinginfo.get(field)
    ]

    if missing_fields:
        return None

    db.connect(reuse_if_open=True)
    with db.atomic():
        shipping = ShippingInformation.create(
            country=shippinginfo["country"],
            address=shippinginfo["address"],
            postal_code=shippinginfo["postal_code"],
            city=shippinginfo["city"],
            province=shippinginfo["province"]
        )
    db.close()

    return shipping



if __name__ == "__main__":
    init_db()