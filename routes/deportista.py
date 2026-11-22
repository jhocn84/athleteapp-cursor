"""Panel del deportista: tarjeta, asistencia, pagos y registro por QR/código."""
from datetime import date, datetime, timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from db import execute, query
from extensions import limiter
from helpers import ESTADO_PAGO_SQL, avisos_visibles, porcentaje
from security import roles_required

bp = Blueprint("deportista", __name__, url_prefix="/deportista")

MINUTOS_TOLERANCIA = 10  # después de esto el QR marca "tarde"


def ficha_actual():
    ficha = query("""
        SELECT d.*, e.nombre AS equipo, e.categoria, dp.nombre AS deporte,
               CONCAT(en.nombre, ' ', en.apellido) AS entrenador
        FROM deportistas d
        LEFT JOIN equipos e ON e.id = d.equipo_id
        LEFT JOIN deportes dp ON dp.id = e.deporte_id
        LEFT JOIN usuarios en ON en.id = e.entrenador_id
        WHERE d.usuario_id = %s""", (g.user["id"],), one=True)
    if not ficha:  # usuario con rol deportista sin ficha (p. ej. cambio de rol)
        execute("INSERT INTO deportistas (usuario_id) VALUES (%s)", (g.user["id"],))
        return ficha_actual()
    return ficha


def historial(ficha, limite=None, desde=None):
    """Entrenamientos ya realizados del equipo con el estado del deportista."""
    if not ficha["equipo_id"]:
        return []
    sql = """
        SELECT t.id, t.fecha, t.hora_inicio, t.lugar, a.estado, a.metodo
        FROM entrenamientos t
        LEFT JOIN asistencias a ON a.entrenamiento_id = t.id AND a.deportista_id = %s
        WHERE t.equipo_id = %s AND t.fecha <= CURDATE()"""
    args = [ficha["id"], ficha["equipo_id"]]
    if desde:
        sql += " AND t.fecha >= %s"
        args.append(desde)
    sql += " ORDER BY t.fecha DESC, t.hora_inicio DESC"
    if limite:
        sql += " LIMIT %s"
        args.append(limite)
    return query(sql, args)


def estadisticas(registros):
    total = len(registros)
    asistio = sum(1 for r in registros if r["estado"] in ("presente", "tarde"))
    conteo = {e: sum(1 for r in registros if r["estado"] == e)
              for e in ("presente", "tarde", "justificado", "ausente")}
    conteo["sin registro"] = sum(1 for r in registros if not r["estado"])
    return {"total": total, "asistio": asistio, "porcentaje": porcentaje(asistio, total), "conteo": conteo}


@bp.route("/")
@roles_required("deportista")
def panel():
    ficha = ficha_actual()
    hoy = date.today()
    mes = historial(ficha, desde=hoy.replace(day=1))
    ultimos = historial(ficha, limite=10)
    racha = 0
    for r in ultimos:
        if r["estado"] not in ("presente", "tarde"):
            break
        racha += 1
    proximo = None
    if ficha["equipo_id"]:
        proximo = query("""SELECT * FROM entrenamientos WHERE equipo_id = %s AND fecha >= CURDATE()
                           ORDER BY fecha, hora_inicio LIMIT 1""", (ficha["equipo_id"],), one=True)
    pagos = query(f"""SELECT p.*, {ESTADO_PAGO_SQL} AS estado_real FROM pagos p
                      WHERE p.deportista_id = %s ORDER BY p.periodo DESC LIMIT 4""", (ficha["id"],))
    pendiente = query(f"""SELECT p.*, {ESTADO_PAGO_SQL} AS estado_real FROM pagos p
                          WHERE p.deportista_id = %s AND p.estado = 'pendiente'
                          ORDER BY p.fecha_vencimiento LIMIT 1""", (ficha["id"],), one=True)
    return render_template("deportista/panel.html", ficha=ficha, mes=estadisticas(mes),
                           total=estadisticas(historial(ficha)), ultimos=list(reversed(ultimos)),
                           racha=racha, proximo=proximo, pagos=pagos, pendiente=pendiente,
                           avisos=avisos_visibles(g.user, limite=3))


@bp.route("/asistencia")
@roles_required("deportista")
def asistencia():
    ficha = ficha_actual()
    registros = historial(ficha, desde=date.today() - timedelta(days=180))
    # Serie mensual para la gráfica
    meses = {}
    for r in registros:
        clave = r["fecha"].strftime("%Y-%m")
        m = meses.setdefault(clave, {"total": 0, "asistio": 0})
        m["total"] += 1
        m["asistio"] += r["estado"] in ("presente", "tarde")
    serie = [{"mes": k, "porcentaje": porcentaje(v["asistio"], v["total"])} for k, v in sorted(meses.items())]
    return render_template("deportista/asistencia.html", ficha=ficha, registros=registros,
                           stats=estadisticas(registros), serie=serie)


@bp.route("/pagos")
@roles_required("deportista")
def pagos():
    ficha = ficha_actual()
    lista = query(f"""SELECT p.*, {ESTADO_PAGO_SQL} AS estado_real FROM pagos p
                      WHERE p.deportista_id = %s ORDER BY p.periodo DESC, p.id DESC""", (ficha["id"],))
    deuda = sum(float(p["monto"]) for p in lista if p["estado"] == "pendiente")
    pagado = sum(float(p["monto"]) for p in lista if p["estado"] == "pagado")
    return render_template("deportista/pagos.html", ficha=ficha, pagos=lista, deuda=deuda, pagado=pagado)


def registrar_por_qr(entrenamiento):
    """Marca la asistencia del deportista actual en un entrenamiento con QR vigente."""
    ficha = ficha_actual()
    if ficha["equipo_id"] != entrenamiento["equipo_id"]:
        flash("Este entrenamiento no corresponde a tu equipo.", "error")
        return redirect(url_for("deportista.panel"))
    if not entrenamiento["qr_expira"] or entrenamiento["qr_expira"] < datetime.now():
        flash("El código de este entrenamiento ya expiró. Pídele al entrenador uno nuevo.", "error")
        return redirect(url_for("deportista.codigo"))
    existente = query("SELECT estado FROM asistencias WHERE entrenamiento_id = %s AND deportista_id = %s",
                      (entrenamiento["id"], ficha["id"]), one=True)
    if existente and existente["estado"] in ("presente", "tarde"):
        flash("Tu asistencia ya estaba registrada.", "info")
        return redirect(url_for("deportista.panel"))
    inicio = datetime.combine(entrenamiento["fecha"], datetime.min.time()) + entrenamiento["hora_inicio"]
    estado = "tarde" if datetime.now() > inicio + timedelta(minutes=MINUTOS_TOLERANCIA) else "presente"
    execute("""INSERT INTO asistencias (entrenamiento_id, deportista_id, estado, metodo)
               VALUES (%s,%s,%s,'qr')
               ON DUPLICATE KEY UPDATE estado = VALUES(estado), metodo = 'qr'""",
            (entrenamiento["id"], ficha["id"], estado))
    flash("Asistencia registrada como " + ("presente." if estado == "presente" else "tarde."), "ok")
    return redirect(url_for("deportista.panel"))


@bp.route("/qr/<token>", methods=["GET", "POST"])
@roles_required("deportista")
def qr_checkin(token):
    if len(token) > 64:
        abort(404)
    ent = query("""SELECT t.*, e.nombre AS equipo FROM entrenamientos t JOIN equipos e ON e.id = t.equipo_id
                   WHERE t.qr_token = %s""", (token,), one=True)
    if not ent:
        flash("El código QR no es válido o ya fue reemplazado.", "error")
        return redirect(url_for("deportista.codigo"))
    if request.method == "POST":
        return registrar_por_qr(ent)
    # GET: confirmación explícita (evita registros por enlaces abiertos sin querer)
    return render_template("deportista/qr_confirmar.html", ent=ent, token=token)


@bp.route("/codigo", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
@roles_required("deportista")
def codigo():
    if request.method == "POST":
        cod = request.form.get("codigo", "").strip().upper()[:6]
        ficha = ficha_actual()
        ent = None
        if len(cod) == 6 and ficha["equipo_id"]:
            ent = query("""SELECT * FROM entrenamientos WHERE qr_codigo = %s AND equipo_id = %s
                           AND qr_expira >= NOW() ORDER BY qr_expira DESC LIMIT 1""",
                        (cod, ficha["equipo_id"]), one=True)
        if ent:
            return registrar_por_qr(ent)
        flash("Código incorrecto o vencido.", "error")
    return render_template("deportista/codigo.html")
