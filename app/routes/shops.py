import requests
from app.database.db import Order, Transaction, CreditCard, db

PAYMENT_URL = "http://dimensweb.uqac.ca/~jgnault/shops/pay/"


def pay_order(order_id, credit_card_data):
    order = Order.get_or_none(Order.id == order_id)
    if not order:
        return {"errors": {"order": {"code": "not-found", "name": "Commande introuvable"}}}, 404

    if order.paid:
        return {"errors": {"order": {"code": "already-paid", "name": "La commande a déjà été payée."}}}, 422

    if not order.email or not order.shipping_information_id:
        return {
            "errors": {"order": {"code": "missing-fields", "name": "Les informations du client sont nécessaires"}}
        }, 422

    total_dollars = float(order.total_price_tax or order.total_price) + float(order.shipping_price)
    amount_cents = int(round(total_dollars * 100))

    card_number = str(credit_card_data.get("number", "")).replace(" ", "").strip()

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

    try:
        response = requests.post(PAYMENT_URL, json=payload, timeout=10)

        if response.status_code != 200:
            return response.json(), 422

        res_data = response.json()

        # Persistance — PAS de return avant cette partie (bug corrigé)
        db.connect(reuse_if_open=True)
        with db.atomic():
            t_info = res_data["transaction"]
            transaction = Transaction.create(
                success=t_info["success"],
                amount_charged=float(t_info["amount_charged"]) / 100.0,
            )

            c_info = res_data["credit_card"]
            cc = CreditCard.create(
                name=c_info["name"],
                first_digits=c_info["first_digits"],
                last_digits=c_info["last_digits"],
                expiration_year=c_info["expiration_year"],
                expiration_month=c_info["expiration_month"],
            )

            order.paid = True
            order.transaction = transaction
            order.credit_card = cc
            order.save()
        db.close()

        return None, 200  # Le caller construit la réponse complète

    except Exception as e:
        return {"errors": {"server": {"code": "connection-error", "name": str(e)}}}, 500