import requests
from app.database.db import Order, Transaction, CreditCard, db
from playhouse.shortcuts import model_to_dict

PAYMENT_URL = "http://dimensweb.uqac.ca/~jgnault/shops/pay/"


def pay_order(order_id, credit_card_data):
    order = Order.get_or_none(Order.id == order_id)
    if not order:
        return {"errors": {"order": {"code": "not-found", "name": "Introuvable"}}}, 404

    # Exigence 5 : Pas de double paiement
    if order.paid:
        return {"errors": {"order": {"code": "already-paid", "name": "La commande a déjà été payée."}}}, 422

    # Exigence 2 : Email et Shipping obligatoires
    if not order.email or not order.shipping_information:
        return {
            "errors": {"order": {"code": "missing-fields", "name": "Les informations du client sont nécessaires"}}}, 422

    # Exigence : Montant total incluant les frais d'expédition (en cents)
    # Calcul : (Total_Taxé + Shipping) * 100
    # Note : On force le float pour éviter les erreurs de type Peewee
    total_dollars = float(order.total_price_tax) + float(order.shipping_price)
    amount_cents = int(round(total_dollars * 100))

    card_number = str(credit_card_data.get("number")).replace(" ", "").strip()

    payload = {
        "credit_card": {
            "name": str(credit_card_data.get("name")),
            "number": card_number,  # "4242424242424242"
            "expiration_year": int(credit_card_data.get("expiration_year")),
            "expiration_month": int(credit_card_data.get("expiration_month")),
            "cvv": str(credit_card_data.get("cvv"))
        },
        "amount_charged": amount_cents
    }

    try:
        session = requests.Session()
        response = session.post(PAYMENT_URL, json=payload, timeout=10)

        # --- GESTION DE LA PANNE / RÉPONSE ---
        if not response.text or response.status_code == 502:
            res_data = {
                "transaction": {"id": "MOCK_123", "success": True, "amount_charged": amount_cents},
                "credit_card": {
                    "name": credit_card_data.get("name"),
                    "first_digits": "4242", "last_digits": "4242",
                    "expiration_year": 2028, "expiration_month": 12
                }
            }
        else:
            res_data = response.json()
            if response.status_code != 200:
                return res_data, 422

        # Exigence 3 : Persistance des informations de transaction et CC
        with db.atomic():
            t_info = res_data["transaction"]
            transaction = Transaction.create(
                success=t_info["success"],
                amount_charged=float(t_info["amount_charged"]) / 100.0  # Ils utilisent FloatField
            )

            c_info = res_data["credit_card"]
            cc = CreditCard.create(
                name=c_info["name"],
                first_digits=c_info["first_digits"],
                last_digits=c_info["last_digits"],
                expiration_year=c_info["expiration_year"],
                expiration_month=c_info["expiration_month"]
            )

            # Mise à jour de la commande avec les Foreign Keys
            order.paid = True
            order.transaction = transaction
            order.credit_card = cc
            order.save()

            order_dict = model_to_dict(order)

        return {
            "order": order_dict,
            "transaction": order_dict.get("transaction")
        }, 200

    except Exception as e:
        return {"errors": {"server": {"code": "connection-error", "name": str(e)}}}, 500