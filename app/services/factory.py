import sqlite3
from app.models.model import Product
import os
from dotenv import load_dotenv

load_dotenv()
db_path = os.getenv("db_path")

class Factory:

    
    

    def init_db():

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Table products
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                description TEXT NOT NULL,
                image TEXT NOT NULL,
                height INTEGER NOT NULL,
                weight INTEGER NOT NULL,
                price REAL NOT NULL,
                in_stock INTEGER NOT NULL
            );
        """)

        # Table commands (commandes)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                total_price INTEGER NOT NULL,
                total_price_tax REAL,
                email TEXT,
                credit_card TEXT,
                shipping_information TEXT,
                paid INTEGER NOT NULL DEFAULT 0,
                transac TEXT,
                product_id INTEGER NOT NULL,
                product_quantity INTEGER NOT NULL,
                shipping_price INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(id)
            );
        """)

        conn.commit()
        conn.close()

    def save_products(products, db_path: str = db_path) -> None:
        with sqlite3.connect(db_path) as conn:
            conn.executemany("""
                INSERT OR REPLACE INTO products
                (id, name, type, description, image, height, weight, price, in_stock)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (
                    p.id,
                    p.name,
                    p.type,
                    p.description,
                    p.image,
                    int(p.height),
                    int(p.weight),
                    float(p.price),
                    1 if p.in_stock else 0
                )
                for p in products
            ])
            conn.commit()
    
    def create_command(product_id: int, quantity: int, product: Product) -> bool:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        total_price = product.price * quantity
        total_price_tax = None
        email = None
        credit_card = None
        shipping_information = None
        paid = False
        transaction = None
        if product.weight <= 500:
            shipping_price = total_price + 5
        elif product.weight < 2000:
            shipping_price = total_price +  10
        else:
            shipping_price = total_price +  25

        

        try:
            conn.execute("BEGIN")
            # Ajouter la commande
            cursor.execute(
                """
                INSERT INTO orders
                    (
                    total_price,
                    total_price_tax,
                    email,
                    credit_card,
                    shipping_information,
                    paid,
                    transac,
                    product_id,
                    product_quantity,
                    shipping_price
                    )
                    VALUES
                    (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    );
                """,
                (total_price,total_price_tax,email,credit_card,shipping_information,paid,transaction,product_id,quantity,shipping_price)
            )

            conn.commit()
            return True

        except Exception as e:
            conn.rollback()
            print("Erreur :", e)
            return False

        finally:
            conn.close()

    
