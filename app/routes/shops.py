from urllib import request
import json
from app.database.db import Order, Transaction, CreditCard, db
from playhouse.shortcuts import model_to_dict

PAYMENT_URL = "https://dimensweb.uqac.ca/~jgnault/shops/pay/"


def pay_order(order, credit_card_data):

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

    card_number = credit_card_data.get("number")


    #Ajout de la vérification des champs
    required_fields = ["name", "number", "expiration_year", "expiration_month", "cvv"]

    missing_fields = [
        field for field in required_fields
        if not credit_card_data.get(field)
    ]

    if missing_fields:
        return {
            "errors": {
                "credit_card": {
                    "code": "missing-fields",
                    "name": f"Champs manquants ou vides: {', '.join(missing_fields)}"
                }
            }
        }, 422

    payload = {
        "credit_card": {
            "name": str(credit_card_data.get("name")),
            "number": card_number,
            "expiration_year": int(credit_card_data.get("expiration_year")),
            "expiration_month": int(credit_card_data.get("expiration_month")),
            "cvv": str(credit_card_data.get("cvv"))
        },
        "amount_charged": amount_cents
    }

    try:
        data_encoded = json.dumps(payload).encode()

        req = request.Request(
            PAYMENT_URL,
            data=data_encoded,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode())

        res_data = response.json()
        
        print(card_number)
        if response.status_code != 200:
            return res_data, response.status_code

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
            "order": order_dict
        }, 200

    except Exception as e:
        return {"errors": {"server": {"code": "connection-error", "name": str(e)}}}, 500