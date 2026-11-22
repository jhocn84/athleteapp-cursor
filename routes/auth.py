"""Login, registro y cierre de sesión."""
from datetime import date, datetime

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from pymysql.err import IntegrityError

from db import execute, get_db, query
from extensions import limiter
from security import (DUMMY_HASH, EMAIL_RE, check_password, es_url_segura, hash_password,
                      password_errors)

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute;40 per hour", methods=["POST"])
def login():
    if g.user:
        return redirect(url_for("inicio"))
    email = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()[:120]
        password = request.form.get("password", "")
        user = query("SELECT id, password_hash, rol, activo FROM usuarios WHERE email = %s", (email,), one=True)

        # Siempre se verifica un hash (real o ficticio) para no revelar si el correo existe.
        valido = check_password(password, user["password_hash"] if user else DUMMY_HASH)
        if user and valido and user["activo"]:
            session.clear()  # nueva sesión: evita fijación de sesión
            session.permanent = True
            session["user_id"] = user["id"]
            session["rol"] = user["rol"]
            execute("UPDATE usuarios SET ultimo_acceso = %s WHERE id = %s", (datetime.now(), user["id"]))
            destino = request.args.get("next")
            return redirect(destino if es_url_segura(destino) else url_for("inicio"))

        if user and valido and not user["activo"]:
            flash("Tu cuenta está desactivada. Comunícate con la administración del club.", "error")
        else:
            flash("Correo o contraseña incorrectos.", "error")
    return render_template("auth/login.html", email=email)


@bp.route("/registro", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def registro():
    if g.user:
        return redirect(url_for("inicio"))
    datos = {}
    if request.method == "POST":
        f = request.form
        datos = {
            "nombre": f.get("nombre", "").strip()[:60],
            "apellido": f.get("apellido", "").strip()[:60],
            "email": f.get("email", "").strip().lower()[:120],
            "documento": f.get("documento", "").strip()[:20],
            "telefono": f.get("telefono", "").strip()[:20],
            "fecha_nacimiento": f.get("fecha_nacimiento", "").strip(),
        }
        password = f.get("password", "")
        errores = []
        if len(datos["nombre"]) < 2 or len(datos["apellido"]) < 2:
            errores.append("Escribe tu nombre y apellido.")
        if not EMAIL_RE.match(datos["email"]):
            errores.append("Escribe un correo válido.")
        if datos["documento"] and not datos["documento"].replace("-", "").isalnum():
            errores.append("El documento solo puede tener letras, números y guiones.")
        if datos["telefono"] and not datos["telefono"].replace("+", "").replace(" ", "").isdigit():
            errores.append("El teléfono solo puede tener números.")
        nacimiento = None
        if datos["fecha_nacimiento"]:
            try:
                nacimiento = date.fromisoformat(datos["fecha_nacimiento"])
                if not (date(1930, 1, 1) <= nacimiento <= date.today()):
                    raise ValueError
            except ValueError:
                errores.append("La fecha de nacimiento no es válida.")
        errores += password_errors(password, datos["email"])
        if password != f.get("password2", ""):
            errores.append("Las contraseñas no coinciden.")
        if not f.get("acepto"):
            errores.append("Debes aceptar el tratamiento de datos personales.")

        if not errores:
            conn = get_db()
            try:
                with conn.cursor() as cur:
                    # El registro público SIEMPRE crea deportistas; los roles los asigna un admin.
                    cur.execute(
                        "INSERT INTO usuarios (nombre, apellido, email, password_hash, rol) "
                        "VALUES (%s,%s,%s,%s,'deportista')",
                        (datos["nombre"], datos["apellido"], datos["email"], hash_password(password)),
                    )
                    cur.execute(
                        "INSERT INTO deportistas (usuario_id, documento, telefono, fecha_nacimiento) "
                        "VALUES (%s,%s,%s,%s)",
                        (cur.lastrowid, datos["documento"] or None, datos["telefono"] or None, nacimiento),
                    )
                conn.commit()
                flash("Cuenta creada. Ya puedes iniciar sesión; la administración te asignará un equipo.", "ok")
                return redirect(url_for("auth.login"))
            except IntegrityError:
                conn.rollback()
                # Mensaje neutro para no confirmar qué correos existen.
                errores.append("No se pudo crear la cuenta con esos datos. Si ya estás registrado, inicia sesión.")
        for e in errores:
            flash(e, "error")
    return render_template("auth/registro.html", datos=datos)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Sesión cerrada.", "ok")
    return redirect(url_for("auth.login"))
