from app.database.db import Product, Order
import json 
import redis

r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)

def cache_order(order):
    r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
    order_dict = {
    "id": order.id,
    "total_price": order.total_price,
    "total_price_tax": order.total_price_tax,
    "email": order.email,
    "credit_card": order.credit_card_id,
    "shipping_information": order.shipping_information_id,
    "paid": order.paid,
    "transaction": order.transaction_id,
    "shipping_price": order.shipping_price
    }
    order_json = json.dumps(order_dict)
    print(order_json)

    r.set(f"order:{order.id}", order_json,ex=60)

def get_cache_order(id):
    r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
    print(id)
    order = r.get(f"order:{id}")
    if order == None:
        return None
    else:
        return json.loads(order)


