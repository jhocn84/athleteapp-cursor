"""Perfil del usuario: datos de contacto y cambio de contraseña."""
from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from db import execute, query
from extensions import limiter
from security import check_password, hash_password, login_required, password_errors

bp = Blueprint("perfil", __name__, url_prefix="/perfil")


@bp.route("/", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
@login_required
def ver():
    ficha = None
    if g.user["rol"] == "deportista":
        ficha = query("""SELECT d.*, e.nombre AS equipo FROM deportistas d
                         LEFT JOIN equipos e ON e.id = d.equipo_id WHERE d.usuario_id = %s""",
                      (g.user["id"],), one=True)
    if request.method == "POST" and request.form.get("accion") == "contacto" and ficha:
        telefono = request.form.get("telefono", "").strip()[:20]
        contacto = request.form.get("contacto_emergencia", "").strip()[:120]
        if telefono and not telefono.replace("+", "").replace(" ", "").isdigit():
            flash("El teléfono solo puede tener números.", "error")
        else:
            execute("UPDATE deportistas SET telefono = %s, contacto_emergencia = %s WHERE usuario_id = %s",
                    (telefono or None, contacto or None, g.user["id"]))
            flash("Datos de contacto actualizados.", "ok")
        return redirect(url_for("perfil.ver"))

    if request.method == "POST" and request.form.get("accion") == "password":
        actual = request.form.get("actual", "")
        nueva = request.form.get("nueva", "")
        fila = query("SELECT password_hash FROM usuarios WHERE id = %s", (g.user["id"],), one=True)
        errores = []
        if not check_password(actual, fila["password_hash"]):
            errores.append("La contraseña actual no es correcta.")
        errores += password_errors(nueva, g.user["email"])
        if nueva != request.form.get("nueva2", ""):
            errores.append("Las contraseñas nuevas no coinciden.")
        if actual and actual == nueva:
            errores.append("La nueva contraseña debe ser distinta a la actual.")
        if errores:
            for e in errores:
                flash(e, "error")
        else:
            execute("UPDATE usuarios SET password_hash = %s WHERE id = %s", (hash_password(nueva), g.user["id"]))
            rol, uid = session["rol"], session["user_id"]
            session.clear()  # rota la sesión tras cambiar la contraseña
            session.permanent = True
            session.update(user_id=uid, rol=rol)
            flash("Contraseña actualizada.", "ok")
        return redirect(url_for("perfil.ver"))
    return render_template("perfil.html", ficha=ficha)
