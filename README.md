# 8INF349 — API de paiement de commandes en ligne

**Cours :** 8INF349 - Technologies Web avancées  
**Présenté à :** Jimmy Girard-Nault  
**Université :** UQAC — Session hiver 2026

**Équipe :**

| Nom | Code permanent |
| --- |----------------|
| Pier-Luc Larouche | LARP03108406   |
| Mathieu Dionne | DIOM30120200   |
| Alexandre Perron | PERA25010108   |

---

## Prérequis

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installé et **démarré**
- Aucune autre installation requise (Python, Redis, PostgreSQL sont gérés par Docker)

---

## Démarrage rapide (Docker)

```bash
docker-compose up --build
```

Cette commande unique lance automatiquement :
1. **PostgreSQL** — base de données principale (port 5432)
2. **Redis** — cache et file de travaux (port 6379)
3. **Web** — initialise la BD (`flask init-db`) puis démarre Flask sur le port 5000
4. **Worker** — traite les paiements en arrière-plan via RQ

Une fois tout démarré, accédez à :
- **Interface web (UI de test) :** http://localhost:5000/ui
- **API REST :** http://localhost:5000/ (voir section "Endpoints de l'API" ci-dessous)

Pour arrêter :
```bash
docker-compose down
```

Pour repartir de zéro (effacer la BD) :
```bash
docker-compose down -v
docker-compose up --build
```

---

## Développement local (sans Docker)

Utile pour lancer les tests ou travailler sans conteneurs.

### Installation des dépendances

```bash
pip install -r requirements.txt
```

### Configuration

Créez un fichier `.env` à la racine (ou exportez les variables) :

```env
FLASK_APP=inf349.py
DB_HOST=localhost
DB_USER=user
DB_PASSWORD=pass
DB_NAME=api8inf349
DB_PORT=5432
REDIS_URL=redis://localhost:6379
```

> En développement sans PostgreSQL, l'app utilise automatiquement SQLite (`products.db`).

### Lancement

Terminal 1 — serveur Flask :
```bash
flask --app inf349.py init-db
flask --app inf349.py run
```

Terminal 2 — worker RQ :
```bash
flask --app inf349.py worker
```

### Tests

```bash
pytest tests/
```

---

## Endpoints de l'API

| Méthode | Route | Description |
|---------|-------|-------------|
| `GET` | `/` | Liste de tous les produits |
| `POST` | `/order` | Créer une commande |
| `GET` | `/order/<id>` | Consulter une commande |
| `PUT` | `/order/<id>` | Mettre à jour les infos client ou payer |

### Créer une commande

```bash
curl -X POST http://localhost:5000/order \
  -H "Content-Type: application/json" \
  -d '{"products": [{"id": 1, "quantity": 2}]}'
```

La réponse est une redirection 302 vers `/order/<id>`.

### Consulter une commande

```bash
curl http://localhost:5000/order/1
```

### Ajouter les infos client

```bash
curl -X PUT http://localhost:5000/order/1 \
  -H "Content-Type: application/json" \
  -d '{
    "order": {
      "email": "client@example.com",
      "shipping_information": {
        "address": "555 Boulevard de l'\''Université",
        "city": "Saguenay",
        "country": "Canada",
        "postal_code": "G7H 2B1",
        "province": "QC"
      }
    }
  }'
```

### Payer une commande

```bash
curl -X PUT http://localhost:5000/order/1 \
  -H "Content-Type: application/json" \
  -d '{
    "credit_card": {
      "name": "John Doe",
      "number": "4242 4242 4242 4242",
      "expiration_year": 2027,
      "expiration_month": 9,
      "cvv": "123"
    }
  }'
```

Le paiement est traité de façon asynchrone. La réponse immédiate est un `202 Accepted`.  
Consultez ensuite `GET /order/<id>` pour vérifier le résultat.

---

## Cartes de test

| Numéro | Résultat |
|--------|----------|
| `4242 4242 4242 4242` | ✅ Paiement accepté (`paid: true`) |
| `4000 0000 0000 0002` | ❌ Carte refusée (`card-declined`) |

> **Important :** Le numéro de carte doit être envoyé **avec les espaces**.

---

## Structure du projet

```
.
├── app/
│   ├── database/
│   │   ├── db.py           # Modèles Peewee (Product, Order, Transaction, ...)
│   │   └── db_redis.py     # Cache Redis pour commandes payées
│   ├── routes/
│   │   ├── orders.py       # POST /order, GET /order/<id>, PUT /order/<id>
│   │   ├── products.py     # GET /
│   │   └── shops.py        # Logique de paiement (RQ worker)
│   ├── static/
│   │   └── style.css       # Interface web
│   └── templates/
│       └── index.html      # SPA de test (3 onglets)
├── tests/                  # Tests pytest
├── CODES-PERMANENTS        # Codes permanents de l'équipe
├── docker-compose.yml      # Orchestration des 4 services
├── Dockerfile              # Image Python pour web + worker
├── inf349.py               # Point d'entrée Flask
└── requirements.txt        # Dépendances Python
```

---

## Architecture

```
Navigateur / curl
       │
       ▼
   Flask (web:5000)
       │
       ├─── PostgreSQL ──── Données persistantes (commandes, produits)
       │
       ├─── Redis ─────────┬── Cache des commandes payées (GET rapide)
       │                   └── File de jobs RQ
       │
       └─── Worker (RQ) ── Traitement asynchrone des paiements
```

Le paiement est délégué au worker pour éviter de bloquer le serveur web. Une fois le paiement traité (accepté ou refusé), le résultat est persisté en PostgreSQL **et** mis en cache dans Redis.
