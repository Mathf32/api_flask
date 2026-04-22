import os
from peewee import (
    Proxy,
    SqliteDatabase, PostgresqlDatabase, Model,
    IntegerField, TextField, FloatField, BooleanField,
    AutoField, ForeignKeyField
)


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
    transaction_id = TextField(null=True)   # ID retourné par le service de paiement (null si échec)
    success = BooleanField()
    amount_charged = IntegerField()
    error_code = TextField(null=True)
    error_name = TextField(null=True)


class Order(BaseModel):
    id = AutoField(primary_key=True)
    total_price = FloatField(default=0)
    total_price_tax = FloatField(default=None, null=True)
    email = TextField(null=True)
    credit_card = ForeignKeyField(CreditCard, backref="orders", null=True)
    shipping_information = ForeignKeyField(ShippingInformation, backref="orders", null=True)
    paid = BooleanField(default=False)
    transaction = ForeignKeyField(Transaction, backref="orders", null=True)
    shipping_price = FloatField(default=0)
    payment_pending = BooleanField(default=False)

    class Meta:
        table_name = 'orders'


class OrderProduct(BaseModel):
    """Table de liaison Order ↔ Product (supporte les commandes multi-produits)."""
    order = ForeignKeyField(Order, backref='order_products')
    product = ForeignKeyField(Product, backref='order_products')
    quantity = IntegerField()

    class Meta:
        table_name = 'order_products'


def setup_db():
    db_host = os.getenv("DB_HOST")
    if db_host:
        # Mode production : PostgreSQL
        real_db = PostgresqlDatabase(
            os.getenv("DB_NAME", "api8inf349"),
            user=os.getenv("DB_USER", "user"),
            password=os.getenv("DB_PASSWORD", "pass"),
            host=db_host,
            port=int(os.getenv("DB_PORT", 5432)),
        )
    else:
        # Mode développement/tests : SQLite
        path = os.getenv("db_path", "products.db")
        real_db = SqliteDatabase(path)
    db.initialize(real_db)


def init_db():
    db.connect(reuse_if_open=True)
    db.create_tables([Product, ShippingInformation, CreditCard, Transaction, Order, OrderProduct])
    db.close()


def _clean_product(p: dict) -> dict:
    """Supprime les caractères NUL (\\x00) incompatibles avec PostgreSQL."""
    return {k: v.replace('\x00', '') if isinstance(v, str) else v for k, v in p.items()}


def save_products(products: list):
    db.connect(reuse_if_open=True)
    with db.atomic():
        for p in products:
            p = _clean_product(p)
            Product.insert(p).on_conflict(
                conflict_target=[Product.id],
                update=p
            ).execute()
    db.close()


def _calc_shipping(weight_g: int) -> float:
    """Frais d'expédition en dollars selon le poids total."""
    if weight_g <= 500:
        return 5.0
    elif weight_g < 2000:
        return 10.0
    else:
        return 25.0


def create_order(products: list) -> Order:
    """
    Crée une commande avec un ou plusieurs produits.
    products = [{"id": int, "quantity": int}, ...]
    """
    db.connect(reuse_if_open=True)
    try:
        total_price = 0.0
        total_weight = 0
        product_objects = []

        for item in products:
            p = Product.get_by_id(item["id"])
            total_price += p.price * item["quantity"]
            total_weight += p.weight * item["quantity"]
            product_objects.append((p, item["quantity"]))

        total_price = round(total_price, 2)
        shipping = _calc_shipping(total_weight)

        with db.atomic():
            order = Order.create(
                total_price=total_price,
                total_price_tax=None,
                email=None,
                credit_card=None,
                shipping_information=None,
                paid=False,
                transaction=None,
                shipping_price=shipping,
            )
            for p, qty in product_objects:
                OrderProduct.create(order=order, product=p, quantity=qty)

        return order
    finally:
        db.close()


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