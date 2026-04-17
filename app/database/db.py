import os
from dotenv import load_dotenv
from peewee import (
    Proxy,
    SqliteDatabase, Model,
    IntegerField, TextField, FloatField, BooleanField,
    AutoField, ForeignKeyField
)

load_dotenv()

db = Proxy()

TAX_RATES = {
    "QC": 0.15,
    "ON": 0.13,
    "AB": 0.05,
    "BC": 0.12,
    "NS": 0.14,
}


class BaseModel(Model):
    class Meta:
        database = db


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
    total_price_tax = FloatField(default=None, null=True)
    email = TextField(null=True)
    credit_card = ForeignKeyField(CreditCard, backref="orders", null=True)
    shipping_information = ForeignKeyField(ShippingInformation, backref="orders", null=True)
    paid = BooleanField(default=False)
    transaction = ForeignKeyField(Transaction, backref="orders", null=True)
    product = ForeignKeyField(Product, backref="orders")
    product_quantity = IntegerField()
    shipping_price = FloatField(default=0)

    class Meta:
        table_name = 'orders'


def setup_db():
    load_dotenv()
    path = os.getenv("db_path", "products.db")
    real_db = SqliteDatabase(path)
    db.initialize(real_db)


def init_db():
    db.connect(reuse_if_open=True)
    db.create_tables([Product, Order, Transaction, CreditCard, ShippingInformation])
    db.close()


def save_products(products: list):
    db.connect(reuse_if_open=True)
    with db.atomic():
        for p in products:
            Product.insert(p).on_conflict_replace().execute()
    db.close()


def _calc_shipping(weight_g: int) -> float:
    """Frais d'expédition en dollars selon le poids total."""
    if weight_g <= 500:
        return 5.0
    elif weight_g < 2000:
        return 10.0
    else:
        return 25.0


def create_order(product_id: int, quantity: int):
    product = Product.get_by_id(product_id)
    total = round(product.price * quantity, 2)
    shipping = _calc_shipping(product.weight * quantity)

    db.connect(reuse_if_open=True)
    with db.atomic():
        order = Order.create(
            total_price=total,
            total_price_tax=None,
            product_quantity=quantity,
            product=product_id,
            email=None,
            credit_card=None,
            shipping_information=None,
            paid=False,
            transaction=None,
            shipping_price=shipping,
        )
    db.close()
    return order


def update_order_info(order_id: int, email: str, shipping_data: dict):
    """Met à jour email + shipping_information + calcule les taxes."""
    db.connect(reuse_if_open=True)
    try:
        with db.atomic():
            order = Order.get_or_none(Order.id == order_id)
            if order is None:
                return None

            order.email = email

            shipping = ShippingInformation.create(
                country=shipping_data["country"],
                address=shipping_data["address"],
                postal_code=shipping_data["postal_code"],
                city=shipping_data["city"],
                province=shipping_data["province"],
            )
            order.shipping_information = shipping

            province = shipping_data.get("province", "").strip().upper()
            tax_rate = TAX_RATES.get(province, 0.0)
            order.total_price_tax = round(order.total_price * (1 + tax_rate), 2)

            order.save()
            return order
    finally:
        db.close()