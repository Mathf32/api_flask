from dataclasses import dataclass
import requests
import json
from typing import Optional, Dict
from dataclasses import dataclass, asdict

@dataclass
class Product:
    id: int
    name: str
    type: str
    description: str
    image: str
    height: int
    weight: int
    price: float
    in_stock: bool

    def GetProductList():
        response = requests.get("https://dimensweb.uqac.ca/~jgnault/shops/products/")
        data = response.json()

        products_data = data["products"]
        products = [Product(**p) for p in products_data]
        return products
    
@dataclass
class Order:
    id: int
    total_price: float
    total_price_tax: float
    email: Optional[str]
    credit_card: Dict
    shipping_information: Dict
    paid: bool
    transaction: Dict
    product: Product
    shipping_price: float

    def to_dict(self):
        data = asdict(self)
        return {"order": data}