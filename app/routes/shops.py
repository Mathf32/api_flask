import requests
from app.database.db import Order, Transaction, CreditCard, db
from playhouse.shortcuts import model_to_dict

PAYMENT_URL = "http://dimensweb.uqac.ca/~jgnault/shops/pay/"


def pay_order(order_id, credit_card_data):
    # 1. Commande
    order = Order.get_or_none(Order.id == order_id)
    if not order:
        return {"errors": {"order": {"code": "not-found", "name": "Commande introuvable"}}}, 404

    # 2. Validations
    if order.paid:
        return {"errors": {"order": {"code": "already-paid", "name": "La commande a déjà été payée."}}}, 422

    if not order.email or not order.shipping_information:
        return {
            "errors": {
                "order": {
                    "code": "missing-fields",
                    "name": "Les informations du client sont nécessaire avant d'appliquer une carte de crédit"
                }
            }
        }, 422

    # 3. Calcul du montant (CENT)
    amount_to_charge = int(round(order.total_price_tax * 100)) + order.shipping_price

    # 4. Payload
    card_number = str(credit_card_data.get("number")).replace(" ", "").replace("-", "")

    payload = {
        "credit_card": {
            "name": credit_card_data.get("name"),
            "number": card_number,
            "expiration_year": int(credit_card_data.get("expiration_year")),
            "expiration_month": int(credit_card_data.get("expiration_month")),
            "cvv": str(credit_card_data.get("cvv"))
        },
        "amount_charged": amount_to_charge
    }

    try:
        response = requests.post(
            PAYMENT_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15
        )

        try:
            res_data = response.json()
        except ValueError:
            # Retry UNE fois (serveur UQAC instable)
            response = requests.post(
                PAYMENT_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=15
            )
            res_data = response.json()

        if response.status_code != 200:
            return res_data, 422

        # 5. DB
        with db.atomic():
            t = res_data["transaction"]
            transaction = Transaction.create(
                id=t["id"],
                success=t["success"],
                amount_charged=t["amount_charged"]
            )

            c = res_data["credit_card"]
            credit_card = CreditCard.create(
                name=c["name"],
                first_digits=c["first_digits"],
                last_digits=c["last_digits"],
                expiration_year=c["expiration_year"],
                expiration_month=c["expiration_month"]
            )

            order.paid = True
            order.transaction = transaction
            order.credit_card = credit_card
            order.save()

        return {
            "transaction": {
                "id": transaction.id,
                "success": transaction.success,
                "amount_charged": transaction.amount_charged
            },
            "order": model_to_dict(order)
        }, 200

    except requests.exceptions.RequestException as e:
        return {"errors": {"server": {"code": "connection-error", "name": str(e)}}}, 500

    except Exception as e:
        return {"errors": {"server": {"code": "internal-error", "name": str(e)}}}, 500