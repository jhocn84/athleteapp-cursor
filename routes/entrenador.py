"""Panel del entrenador: equipos, entrenamientos, lista de asistencia y QR."""
import secrets
import string
from datetime import date, datetime, time, timedelta

import segno
from flask import (Blueprint, Response, abort, current_app, flash, g, redirect, render_template,
                   request, url_for)

from db import execute, execute_many, query
from helpers import ESTADOS_ASISTENCIA, porcentaje, puede_gestionar_equipo, resumen_asistencia_equipo
from security import roles_required

bp = Blueprint("entrenador", __name__, url_prefix="/entrenador")

ALFABETO_CODIGO = "".join(c for c in string.ascii_uppercase + string.digits if c not in "O0I1")


def mis_equipos():
    if g.user["rol"] == "admin":
        filtro, args = "", ()
    else:
        filtro, args = "WHERE e.entrenador_id = %s", (g.user["id"],)
    return query(f"""
        SELECT e.*, dp.nombre AS deporte,
               (SELECT COUNT(*) FROM deportistas d JOIN usuarios u ON u.id = d.usuario_id
                WHERE d.equipo_id = e.id AND u.activo = 1 AND u.rol = 'deportista') AS jugadores
        FROM equipos e JOIN deportes dp ON dp.id = e.deporte_id {filtro}
        ORDER BY dp.nombre, e.nombre""", args)


def obtener_entrenamiento(ent_id):
    ent = query("""SELECT t.*, e.nombre AS equipo, e.categoria, dp.nombre AS deporte
                   FROM entrenamientos t JOIN equipos e ON e.id = t.equipo_id
                   JOIN deportes dp ON dp.id = e.deporte_id WHERE t.id = %s""", (ent_id,), one=True)
    if not ent:
        abort(404)
    if not puede_gestionar_equipo(g.user, ent["equipo_id"]):
        abort(403)
    return ent


def plantilla_equipo(equipo_id):
    return query("""SELECT d.id, d.posicion, d.dorsal, u.nombre, u.apellido
                    FROM deportistas d JOIN usuarios u ON u.id = d.usuario_id
                    WHERE d.equipo_id = %s AND u.activo = 1 AND u.rol = 'deportista'
                    ORDER BY d.dorsal IS NULL, d.dorsal, u.apellido""", (equipo_id,))


@bp.route("/")
@roles_required("entrenador", "admin")
def panel():
    equipos = mis_equipos()
    for e in equipos:
        e["asistencia"] = resumen_asistencia_equipo(e["id"])
    ids = [e["id"] for e in equipos] or [0]
    marcadores = ",".join(["%s"] * len(ids))
    proximos = query(f"""SELECT t.*, e.nombre AS equipo FROM entrenamientos t JOIN equipos e ON e.id = t.equipo_id
                         WHERE t.equipo_id IN ({marcadores}) AND t.fecha >= CURDATE()
                         ORDER BY t.fecha, t.hora_inicio LIMIT 8""", ids)
    recientes = query(f"""SELECT t.*, e.nombre AS equipo,
                                 (SELECT COUNT(*) FROM asistencias a WHERE a.entrenamiento_id = t.id) AS marcados,
                                 (SELECT COUNT(*) FROM asistencias a WHERE a.entrenamiento_id = t.id
                                    AND a.estado IN ('presente','tarde')) AS asistieron
                          FROM entrenamientos t JOIN equipos e ON e.id = t.equipo_id
                          WHERE t.equipo_id IN ({marcadores}) AND t.fecha < CURDATE()
                          ORDER BY t.fecha DESC, t.hora_inicio DESC LIMIT 8""", ids)
    return render_template("entrenador/panel.html", equipos=equipos, proximos=proximos,
                           recientes=recientes, manana=date.today())


@bp.route("/entrenamientos/nuevo", methods=["POST"])
@roles_required("entrenador", "admin")
def nuevo_entrenamiento():
    f = request.form
    try:
        equipo_id = int(f.get("equipo_id", 0))
        fecha = date.fromisoformat(f.get("fecha", ""))
        inicio = time.fromisoformat(f.get("hora_inicio", ""))
        fin = time.fromisoformat(f["hora_fin"]) if f.get("hora_fin") else None
    except (ValueError, KeyError):
        flash("Revisa el equipo, la fecha y las horas del entrenamiento.", "error")
        return redirect(url_for("entrenador.panel"))
    if not puede_gestionar_equipo(g.user, equipo_id):
        abort(403)
    if fin and fin <= inicio:
        flash("La hora de fin debe ser posterior a la de inicio.", "error")
        return redirect(url_for("entrenador.panel"))
    ent_id = execute("""INSERT INTO entrenamientos (equipo_id, fecha, hora_inicio, hora_fin, lugar, creado_por)
                        VALUES (%s,%s,%s,%s,%s,%s)""",
                     (equipo_id, fecha, inicio, fin, f.get("lugar", "").strip()[:100] or None, g.user["id"]))
    flash("Entrenamiento programado.", "ok")
    return redirect(url_for("entrenador.entrenamiento", ent_id=ent_id))


@bp.route("/entrenamiento/<int:ent_id>", methods=["GET", "POST"])
@roles_required("entrenador", "admin")
def entrenamiento(ent_id):
    ent = obtener_entrenamiento(ent_id)
    jugadores = plantilla_equipo(ent["equipo_id"])
    if request.method == "POST":
        ids_validos = {j["id"] for j in jugadores}
        filas = []
        for did in ids_validos:
            estado = request.form.get(f"estado_{did}")
            if estado in ESTADOS_ASISTENCIA:
                filas.append((ent_id, did, estado))
        if filas:
            execute_many("""INSERT INTO asistencias (entrenamiento_id, deportista_id, estado, metodo)
                            VALUES (%s,%s,%s,'manual')
                            ON DUPLICATE KEY UPDATE metodo = IF(estado = VALUES(estado), metodo, 'manual'),
                                                    estado = VALUES(estado)""", filas)
        flash(f"Asistencia guardada ({len(filas)} de {len(jugadores)} deportistas).", "ok")
        return redirect(url_for("entrenador.entrenamiento", ent_id=ent_id))

    marcas = {a["deportista_id"]: a for a in query(
        "SELECT deportista_id, estado, metodo FROM asistencias WHERE entrenamiento_id = %s", (ent_id,))}
    for j in jugadores:
        j["estado"] = marcas.get(j["id"], {}).get("estado")
        j["metodo"] = marcas.get(j["id"], {}).get("metodo")
    asistieron = sum(1 for j in jugadores if j["estado"] in ("presente", "tarde"))
    qr_activo = bool(ent["qr_expira"] and ent["qr_expira"] > datetime.now())
    return render_template("entrenador/entrenamiento.html", ent=ent, jugadores=jugadores,
                           asistieron=asistieron, porcentaje=porcentaje(asistieron, len(jugadores)),
                           qr_activo=qr_activo, estados=ESTADOS_ASISTENCIA)


@bp.route("/entrenamiento/<int:ent_id>/qr", methods=["POST"])
@roles_required("entrenador", "admin")
def generar_qr(ent_id):
    obtener_entrenamiento(ent_id)
    if request.form.get("accion") == "cerrar":
        execute("UPDATE entrenamientos SET qr_token = NULL, qr_codigo = NULL, qr_expira = NULL WHERE id = %s",
                (ent_id,))
        flash("Registro por QR cerrado.", "ok")
    else:
        minutos = current_app.config["QR_MINUTOS"]
        token = secrets.token_urlsafe(24)
        codigo = "".join(secrets.choice(ALFABETO_CODIGO) for _ in range(6))
        execute("UPDATE entrenamientos SET qr_token = %s, qr_codigo = %s, qr_expira = %s WHERE id = %s",
                (token, codigo, datetime.now() + timedelta(minutes=minutos), ent_id))
        flash(f"QR activo durante {minutos} minutos.", "ok")
    return redirect(url_for("entrenador.entrenamiento", ent_id=ent_id))


@bp.route("/entrenamiento/<int:ent_id>/qr.svg")
@roles_required("entrenador", "admin")
def qr_svg(ent_id):
    ent = obtener_entrenamiento(ent_id)
    if not ent["qr_token"] or not ent["qr_expira"] or ent["qr_expira"] < datetime.now():
        abort(404)
    url = url_for("deportista.qr_checkin", token=ent["qr_token"], _external=True)
    svg = segno.make(url, error="m").svg_inline(scale=8, border=2, dark="#0A1830", light="#FFFFFF")
    return Response(svg, mimetype="image/svg+xml", headers={"Cache-Control": "no-store"})


@bp.route("/entrenamiento/<int:ent_id>/eliminar", methods=["POST"])
@roles_required("entrenador", "admin")
def eliminar_entrenamiento(ent_id):
    obtener_entrenamiento(ent_id)
    execute("DELETE FROM entrenamientos WHERE id = %s", (ent_id,))
    flash("Entrenamiento eliminado.", "ok")
    return redirect(url_for("entrenador.panel"))


@bp.route("/equipo/<int:equipo_id>")
@roles_required("entrenador", "admin")
def equipo(equipo_id):
    if not puede_gestionar_equipo(g.user, equipo_id):
        abort(403)
    eq = query("""SELECT e.*, dp.nombre AS deporte, CONCAT(u.nombre, ' ', u.apellido) AS entrenador
                  FROM equipos e JOIN deportes dp ON dp.id = e.deporte_id
                  LEFT JOIN usuarios u ON u.id = e.entrenador_id WHERE e.id = %s""", (equipo_id,), one=True)
    if not eq:
        abort(404)
    desde = date.today() - timedelta(days=30)
    jugadores = query("""
        SELECT d.id, d.posicion, d.dorsal, d.telefono, d.contacto_emergencia, u.nombre, u.apellido, u.email,
               COUNT(a.id) AS registros,
               SUM(a.estado IN ('presente','tarde')) AS asistio,
               SUM(a.estado = 'ausente') AS ausencias
        FROM deportistas d
        JOIN usuarios u ON u.id = d.usuario_id
        LEFT JOIN entrenamientos t ON t.equipo_id = d.equipo_id AND t.fecha BETWEEN %s AND CURDATE()
        LEFT JOIN asistencias a ON a.entrenamiento_id = t.id AND a.deportista_id = d.id
        WHERE d.equipo_id = %s AND u.activo = 1 AND u.rol = 'deportista'
        GROUP BY d.id ORDER BY d.dorsal IS NULL, d.dorsal, u.apellido""", (desde, equipo_id))
    for j in jugadores:
        j["porcentaje"] = porcentaje(int(j["asistio"] or 0), int(j["registros"] or 0))
    return render_template("entrenador/equipo.html", eq=eq, jugadores=jugadores,
                           promedio=resumen_asistencia_equipo(equipo_id))
