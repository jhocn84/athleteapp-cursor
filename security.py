"""Utilidades de seguridad: hash de contraseñas, política de contraseñas y control de acceso por rol."""
import re
from functools import wraps

import bcrypt
from flask import abort, flash, g, redirect, request, url_for

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
PASSWORD_MIN, PASSWORD_MAX = 8, 64  # bcrypt solo usa los primeros 72 bytes


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def check_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


# Hash ficticio: se verifica cuando el correo no existe, para que el tiempo de
# respuesta no revele qué correos están registrados.
DUMMY_HASH = hash_password("athletehub-dummy-password")


def password_errors(password: str, email: str = "") -> list[str]:
    errores = []
    if len(password) < PASSWORD_MIN:
        errores.append(f"Debe tener al menos {PASSWORD_MIN} caracteres.")
    if len(password) > PASSWORD_MAX:
        errores.append(f"Debe tener máximo {PASSWORD_MAX} caracteres.")
    if not re.search(r"[A-Z]", password):
        errores.append("Debe incluir una letra mayúscula.")
    if not re.search(r"[a-z]", password):
        errores.append("Debe incluir una letra minúscula.")
    if not re.search(r"\d", password):
        errores.append("Debe incluir un número.")
    if not re.search(r"[^A-Za-z0-9]", password):
        errores.append("Debe incluir un símbolo (por ejemplo * # ! @).")
    usuario = email.split("@")[0].lower() if email else ""
    if usuario and len(usuario) >= 4 and usuario in password.lower():
        errores.append("No debe contener tu correo.")
    return errores


def es_url_segura(destino: str | None) -> bool:
    """Evita redirecciones abiertas: solo rutas internas."""
    return bool(destino) and destino.startswith("/") and not destino.startswith("//") and "\\" not in destino


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if g.get("user") is None:
            flash("Inicia sesión para continuar.", "info")
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?") if request.method == "GET" else None))
        return view(*args, **kwargs)
    return wrapper


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(*args, **kwargs):
            if g.user["rol"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapper
    return decorator
