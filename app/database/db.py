# app.py (tout-en-un) — Peewee + SQLite
import os
from dotenv import load_dotenv
from peewee import (
    Proxy,
    SqliteDatabase, Model,
    IntegerField, TextField, FloatField, BooleanField,
    AutoField, ForeignKeyField
)
from playhouse.shortcuts import model_to_dict


load_dotenv()

# Chemin DB depuis .env (ex: DB_PATH=app/database/products.db)
DB_PATH = os.getenv("db_path")
db = Proxy()


class BaseModel(Model):
    class Meta:
        database = db


def setup_db():
    load_dotenv()
    path = os.getenv("db_path", "products.db")
    real_db = SqliteDatabase(path)
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


def init_db():
    db.connect(reuse_if_open=True)
    db.create_tables([Product, Order, Transaction, CreditCard, ShippingInformation])
    db.close()


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
                tax_rate = 1.15 if shipping_info.province == "QC" else 1.13
                order.total_price_tax = float(int((order.total_price * tax_rate) * 100 + 0.5)) / 100.0

            order.save()
            return order
    finally:
        db.close()


def create_shippinginfo(shippinginfo: dict):
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