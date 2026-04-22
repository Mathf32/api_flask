from app.database.db import (
    Order, Transaction, CreditCard, OrderProduct, ShippingInformation, db
)
from app.database.db_redis import cache_order
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

PAYMENT_URL = "https://dimensweb.uqac.ca/~jgnault/shops/pay/"


def _post_json(url: str, payload: dict, timeout: int = 10) -> tuple[int, dict]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        body = error.read().decode("utf-8")
        return error.code, json.loads(body) if body else {}


def _build_transaction_dict(transaction) -> dict:
    """Construit le dict transaction selon le format attendu par le devis."""
    if transaction is None:
        return {}
    if transaction.success:
        return {
            "id": transaction.transaction_id,
            "success": True,
            "error": {},
            "amount_charged": transaction.amount_charged,
        }
    else:
        return {
            "success": False,
            "error": {
                "code": transaction.error_code,
                "name": transaction.error_name,
            },
            "amount_charged": transaction.amount_charged,
        }


def _build_cached_response(order, cc, transaction) -> dict:
    """
    Construit le dict complet d'une commande pour mise en cache Redis.
    Toutes les données sont expandées pour fonctionner sans Postgres.
    """
    order_products = list(OrderProduct.select().where(OrderProduct.order == order))
    products_list = [{"id": op.product_id, "quantity": op.quantity} for op in order_products]

    shipping_info = None
    if order.shipping_information_id:
        try:
            shipping_info = ShippingInformation.get_by_id(order.shipping_information_id)
        except Exception:
            pass

    credit_card_dict = {}
    if cc:
        credit_card_dict = {
            "name": cc.name,
            "first_digits": cc.first_digits,
            "last_digits": cc.last_digits,
            "expiration_year": cc.expiration_year,
            "expiration_month": cc.expiration_month,
        }

    return {
        "order": {
            "id": order.id,
            "total_price": float(order.total_price),
            "total_price_tax": float(order.total_price_tax) if order.total_price_tax is not None else None,
            "email": order.email,
            "credit_card": credit_card_dict,
            "shipping_information": {
                "country": shipping_info.country,
                "address": shipping_info.address,
                "postal_code": shipping_info.postal_code,
                "city": shipping_info.city,
                "province": shipping_info.province,
            } if shipping_info else {},
            "paid": bool(order.paid),
            "transaction": _build_transaction_dict(transaction),
            "products": products_list,
            "shipping_price": float(order.shipping_price),
        }
    }


def pay_order(order_id, credit_card_data):
    db.connect(reuse_if_open=True)
    try:
        order = Order.get_or_none(Order.id == order_id)
        if not order:
            raise Exception(f"Commande {order_id} introuvable")

        if order.paid:
            raise Exception(f"Commande {order_id} déjà payée")

        if not order.email or not order.shipping_information_id:
            raise Exception(f"Commande {order_id} : informations client manquantes")

        total_dollars = float(order.total_price_tax or order.total_price) + float(order.shipping_price)
        amount_cents = int(round(total_dollars * 100))

        card_number = str(credit_card_data.get("number", "")).strip()

        payload = {
            "credit_card": {
                "name": str(credit_card_data.get("name")),
                "number": card_number,
                "expiration_year": int(credit_card_data.get("expiration_year")),
                "expiration_month": int(credit_card_data.get("expiration_month")),
                "cvv": str(credit_card_data.get("cvv")),
            },
            "amount_charged": amount_cents,
        }

        status_code, res_data = _post_json(PAYMENT_URL, payload, timeout=10)

        if status_code != 200:
            # Erreur retournée par le service distant → persister la transaction en échec
            error_info = {}
            errors = res_data.get("errors", {})
            if "credit_card" in errors:
                error_info = errors["credit_card"]

            with db.atomic():
                transaction = Transaction.create(
                    transaction_id=None,
                    success=False,
                    amount_charged=amount_cents,
                    error_code=error_info.get("code", "unknown"),
                    error_name=error_info.get("name", "Erreur de paiement"),
                )
                order.payment_pending = False
                order.transaction = transaction
                order.save()

            # Mettre en cache la commande avec la transaction en échec
            response_data = _build_cached_response(order, None, transaction)
            cache_order(order.id, response_data)
            return

        # Paiement réussi
        with db.atomic():
            t_info = res_data["transaction"]
            transaction = Transaction.create(
                transaction_id=t_info["id"],
                success=bool(t_info["success"]),
                amount_charged=int(t_info["amount_charged"]),
                error_code=None,
                error_name=None,
            )

            c_info = res_data["credit_card"]
            cc = CreditCard.create(
                name=c_info["name"],
                first_digits=str(c_info["first_digits"]),
                last_digits=str(c_info["last_digits"]),
                expiration_year=c_info["expiration_year"],
                expiration_month=c_info["expiration_month"],
            )

            order.paid = True
            order.payment_pending = False
            order.transaction = transaction
            order.credit_card = cc
            order.save()

        # Mise en cache Redis avec toutes les données expandées
        response_data = _build_cached_response(order, cc, transaction)
        cache_order(order.id, response_data)

    except Exception:
        # S'assurer que payment_pending est remis à False en cas d'erreur inattendue
        try:
            order.payment_pending = False
            order.save()
        except Exception:
            pass
        raise
    finally:
        db.close()
