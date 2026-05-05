"""Rate limiting via slowapi.

Stratégie :
- Utilisateurs authentifiés  → clé user:{id}     → 60 requêtes/minute
- Utilisateurs anonymes      → clé ip:{adresse}   → 10 requêtes/minute

En production multi-workers, remplacer le stockage mémoire par Redis :
    from slowapi import Limiter
    limiter = Limiter(key_func=..., storage_uri="redis://redis:6379")
"""
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _auth_key(request: Request) -> str:
    """Clé de rate-limit : user:{id} si JWT valide, sinon ip:{adresse}."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            from jose import jwt
            from backend.config import settings
            payload = jwt.decode(
                auth[7:], settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
            )
            if sub := payload.get("sub"):
                return f"user:{sub}"
        except Exception:
            pass
    return f"ip:{get_remote_address(request)}"


def _translate_limit(key: str) -> str:
    """Limite dynamique basée sur la clé retournée par _auth_key.

    slowapi (>=0.1.9) appelle cette fonction avec le résultat de key_func
    quand le paramètre s'appelle 'key'.
    """
    if key.startswith("user:"):
        return "60/minute"
    return "10/minute"


# Instance partagée — importée dans main.py et dans les routers
limiter = Limiter(key_func=get_remote_address, default_limits=[])
