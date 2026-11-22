r"""Servidor de producción (Waitress) para publicar AthleteHub con Cloudflare Tunnel.

Uso:  .venv\Scripts\python servidor.py
Escucha solo en 127.0.0.1: nadie de fuera puede entrar directo, solo a través del túnel.
"""
import os

from waitress import serve

from app import app

if __name__ == "__main__":
    puerto = int(os.getenv("PORT", "5000"))
    print(f"AthleteHub en http://127.0.0.1:{puerto} (Ctrl+C para detener)")
    serve(app, host="127.0.0.1", port=puerto, threads=8)
