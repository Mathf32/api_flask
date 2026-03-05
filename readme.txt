payload pour le paiement

{
"credit_card" : {
"name" : "John Doe",
"number" : "4242 4242 4242 4242",
"expiration_year" : 2024,
"cvv" : "123",
"expiration_month" : 9
}
}



payload pour le shipping info

{
  "order": {
    "email": "pierluc@test.com",
    "shipping_information": {
      "address": "555 Boulevard de l'Université",
      "city": "Saguenay",
      "country": "Canada",
      "id": 5,
      "postal_code": "G7H 2B1",
      "province": "QC"
    }
  },
}