import json
import os
import redis


def _get_redis():
    """Retourne une connexion Redis à partir de REDIS_URL."""
    url = os.getenv("REDIS_URL", "redis://localhost")
    return redis.Redis.from_url(url, decode_responses=True)


def cache_order(order_id: int, response_data: dict):
    """
    Met en cache la réponse complète d'une commande payée.
    response_data : le dict complet tel que retourné par GET /order/<id>
    """
    r = _get_redis()
    r.set(f"order:{order_id}", json.dumps(response_data))


def get_cached_order(order_id: int):
    """
    Retourne le dict complet mis en cache, ou None si absent ou si Redis est inaccessible.
    Quand cette fonction retourne quelque chose, on n'a pas besoin de toucher Postgres.
    """
    try:
        r = _get_redis()
        data = r.get(f"order:{order_id}")
        return json.loads(data) if data is not None else None
    except Exception:
        return None
