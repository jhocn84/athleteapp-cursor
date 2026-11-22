"""Extensiones compartidas: CSRF y límite de intentos (anti fuerza bruta)."""
from flask import request
from flask_limiter import Limiter
from flask_wtf.csrf import CSRFProtect


def ip_cliente():
    # Detrás de Cloudflare Tunnel la IP real llega en CF-Connecting-IP. Es confiable
    # porque el servidor solo escucha en 127.0.0.1 (solo cloudflared puede conectarse).
    return request.headers.get("CF-Connecting-IP") or request.remote_addr or "desconocida"


csrf = CSRFProtect()
limiter = Limiter(key_func=ip_cliente, storage_uri="memory://", default_limits=[])
