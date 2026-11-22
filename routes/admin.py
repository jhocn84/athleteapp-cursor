"""Panel de administración: resumen, usuarios, deportes/equipos y pagos."""
import json
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from pymysql.err import IntegrityError

from db import execute, query, scalar
from helpers import ESTADO_PAGO_SQL, porcentaje
from security import es_url_segura, roles_required

bp = Blueprint("admin", __name__, url_prefix="/admin")

METODOS_PAGO = ["efectivo", "transferencia", "tarjeta", "otro"]
ROLES = ["deportista", "entrenador", "admin"]


def a_entero(valor, defecto=None):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return defecto


def a_monto(valor):
    try:
        monto = Decimal(str(valor).strip().replace(",", "."))
        return monto if Decimal("0") < monto < Decimal("100000000") else None
    except InvalidOperation:
        return None


# ------------------------------------------------------------------ Resumen
@bp.route("/")
@roles_required("admin")
def panel():
    hoy = date.today()
    periodo = hoy.strftime("%Y-%m")
    tot = query("""SELECT
        (SELECT COUNT(*) FROM usuarios WHERE rol = 'deportista' AND activo = 1) AS deportistas,
        (SELECT COUNT(*) FROM usuarios WHERE rol = 'entrenador' AND activo = 1) AS entrenadores,
        (SELECT COUNT(*) FROM equipos) AS equipos,
        (SELECT COUNT(*) FROM deportistas d JOIN usuarios u ON u.id = d.usuario_id
          WHERE d.equipo_id IS NULL AND u.rol = 'deportista' AND u.activo = 1) AS sin_equipo""", one=True)
    pagos = query(f"""SELECT
        SUM({ESTADO_PAGO_SQL} = 'pendiente') AS pendientes, SUM(IF({ESTADO_PAGO_SQL} = 'pendiente', p.monto, 0)) AS monto_pendiente,
        SUM({ESTADO_PAGO_SQL} = 'vencido') AS vencidos, SUM(IF({ESTADO_PAGO_SQL} = 'vencido', p.monto, 0)) AS monto_vencido,
        SUM(IF(p.estado = 'pagado' AND DATE_FORMAT(p.fecha_pago, '%%Y-%%m') = %s, p.monto, 0)) AS recaudado_mes
        FROM pagos p""", (periodo,), one=True)
    equipos = query("""
        SELECT e.id, e.nombre, COUNT(a.id) AS registros, SUM(a.estado IN ('presente','tarde')) AS asistio
        FROM equipos e
        LEFT JOIN entrenamientos t ON t.equipo_id = e.id AND t.fecha BETWEEN %s AND CURDATE()
        LEFT JOIN asistencias a ON a.entrenamiento_id = t.id
        GROUP BY e.id ORDER BY e.nombre""", (hoy - timedelta(days=30),))
    for e in equipos:
        e["porcentaje"] = porcentaje(int(e["asistio"] or 0), int(e["registros"] or 0))
    total_reg = sum(int(e["registros"] or 0) for e in equipos)
    total_asis = sum(int(e["asistio"] or 0) for e in equipos)
    vencidos = query(f"""SELECT p.*, u.nombre, u.apellido, e.nombre AS equipo
                         FROM pagos p JOIN deportistas d ON d.id = p.deportista_id
                         JOIN usuarios u ON u.id = d.usuario_id LEFT JOIN equipos e ON e.id = d.equipo_id
                         WHERE {ESTADO_PAGO_SQL} = 'vencido' ORDER BY p.fecha_vencimiento LIMIT 6""")
    grafica = json.dumps({"labels": [e["nombre"] for e in equipos],
                          "valores": [e["porcentaje"] for e in equipos]})
    return render_template("admin/panel.html", tot=tot, pagos=pagos, equipos=equipos,
                           asistencia_global=porcentaje(total_asis, total_reg), vencidos=vencidos,
                           grafica=grafica)


# ------------------------------------------------------------------ Usuarios
@bp.route("/usuarios")
@roles_required("admin")
def usuarios():
    rol = request.args.get("rol", "")
    buscar = request.args.get("q", "").strip()[:60]
    sql = """SELECT u.*, d.dorsal, d.posicion, e.nombre AS equipo
             FROM usuarios u LEFT JOIN deportistas d ON d.usuario_id = u.id
             LEFT JOIN equipos e ON e.id = d.equipo_id WHERE 1=1"""
    args = []
    if rol in ROLES:
        sql += " AND u.rol = %s"
        args.append(rol)
    if buscar:
        sql += " AND (u.nombre LIKE %s OR u.apellido LIKE %s OR u.email LIKE %s)"
        args += [f"%{buscar}%"] * 3
    sql += " ORDER BY u.activo DESC, FIELD(u.rol, 'admin','entrenador','deportista'), u.apellido"
    return render_template("admin/usuarios.html", usuarios=query(sql, args), rol=rol, buscar=buscar, roles=ROLES)


@bp.route("/usuarios/<int:uid>", methods=["GET", "POST"])
@roles_required("admin")
def usuario_editar(uid):
    usuario = query("SELECT * FROM usuarios WHERE id = %s", (uid,), one=True)
    if not usuario:
        abort(404)
    ficha = query("SELECT * FROM deportistas WHERE usuario_id = %s", (uid,), one=True)
    if request.method == "POST":
        f = request.form
        rol = f.get("rol", usuario["rol"])
        activo = 1 if f.get("activo") else 0
        if rol not in ROLES:
            abort(400)
        if uid == g.user["id"] and (rol != "admin" or not activo):
            flash("No puedes quitarte el rol de administrador ni desactivar tu propia cuenta.", "error")
            return redirect(url_for("admin.usuario_editar", uid=uid))
        execute("UPDATE usuarios SET rol = %s, activo = %s WHERE id = %s", (rol, activo, uid))
        if rol == "deportista":
            equipo_id = a_entero(f.get("equipo_id")) or None
            dorsal = a_entero(f.get("dorsal"))
            if dorsal is not None and not 0 <= dorsal <= 99:
                dorsal = None
            valores = (equipo_id, f.get("posicion", "").strip()[:40] or None, dorsal,
                       f.get("telefono", "").strip()[:20] or None,
                       f.get("contacto_emergencia", "").strip()[:120] or None)
            if ficha:
                execute("""UPDATE deportistas SET equipo_id = %s, posicion = %s, dorsal = %s, telefono = %s,
                           contacto_emergencia = %s WHERE usuario_id = %s""", (*valores, uid))
            else:
                execute("""INSERT INTO deportistas (equipo_id, posicion, dorsal, telefono, contacto_emergencia,
                           usuario_id) VALUES (%s,%s,%s,%s,%s,%s)""", (*valores, uid))
        if rol != "entrenador":
            execute("UPDATE equipos SET entrenador_id = NULL WHERE entrenador_id = %s", (uid,))
        flash("Usuario actualizado.", "ok")
        return redirect(url_for("admin.usuarios"))
    equipos = query("""SELECT e.id, e.nombre, dp.nombre AS deporte FROM equipos e
                       JOIN deportes dp ON dp.id = e.deporte_id ORDER BY dp.nombre, e.nombre""")
    return render_template("admin/usuario_editar.html", usuario=usuario, ficha=ficha or {},
                           equipos=equipos, roles=ROLES)


# ------------------------------------------------------------------ Deportes y equipos
@bp.route("/deportes", methods=["GET", "POST"])
@roles_required("admin")
def deportes():
    if request.method == "POST":
        accion = request.form.get("accion")
        try:
            if accion == "deporte":
                nombre = request.form.get("nombre", "").strip()[:60]
                if len(nombre) < 3:
                    flash("Escribe el nombre del deporte.", "error")
                else:
                    execute("INSERT INTO deportes (nombre, descripcion) VALUES (%s,%s)",
                            (nombre, request.form.get("descripcion", "").strip()[:255] or None))
                    flash("Deporte creado.", "ok")
            elif accion == "equipo":
                deporte_id = a_entero(request.form.get("deporte_id"))
                nombre = request.form.get("nombre", "").strip()[:80]
                if not deporte_id or len(nombre) < 3:
                    flash("Elige el deporte y escribe el nombre del equipo.", "error")
                else:
                    execute("INSERT INTO equipos (deporte_id, nombre, categoria, entrenador_id) VALUES (%s,%s,%s,%s)",
                            (deporte_id, nombre, request.form.get("categoria", "").strip()[:40] or None,
                             entrenador_valido(request.form.get("entrenador_id"))))
                    flash("Equipo creado.", "ok")
            elif accion == "asignar":
                equipo_id = a_entero(request.form.get("equipo_id"))
                execute("UPDATE equipos SET entrenador_id = %s WHERE id = %s",
                        (entrenador_valido(request.form.get("entrenador_id")), equipo_id))
                flash("Entrenador asignado.", "ok")
            elif accion == "eliminar_equipo":
                execute("DELETE FROM equipos WHERE id = %s", (a_entero(request.form.get("equipo_id")),))
                flash("Equipo eliminado. Sus deportistas quedaron sin equipo.", "ok")
            elif accion == "eliminar_deporte":
                execute("DELETE FROM deportes WHERE id = %s", (a_entero(request.form.get("deporte_id")),))
                flash("Deporte eliminado.", "ok")
        except IntegrityError:
            flash("No se pudo guardar: el nombre ya existe o el deporte todavía tiene equipos.", "error")
        return redirect(url_for("admin.deportes"))

    lista = query("SELECT * FROM deportes ORDER BY nombre")
    equipos = query("""SELECT e.*, CONCAT(u.nombre, ' ', u.apellido) AS entrenador,
                              (SELECT COUNT(*) FROM deportistas d JOIN usuarios du ON du.id = d.usuario_id
                               WHERE d.equipo_id = e.id AND du.activo = 1 AND du.rol = 'deportista') AS jugadores
                       FROM equipos e LEFT JOIN usuarios u ON u.id = e.entrenador_id ORDER BY e.nombre""")
    for d in lista:
        d["equipos"] = [e for e in equipos if e["deporte_id"] == d["id"]]
    entrenadores = query("""SELECT id, nombre, apellido FROM usuarios
                            WHERE rol = 'entrenador' AND activo = 1 ORDER BY nombre""")
    return render_template("admin/deportes.html", deportes=lista, entrenadores=entrenadores)


def entrenador_valido(valor):
    uid = a_entero(valor)
    if uid and scalar("SELECT COUNT(*) FROM usuarios WHERE id = %s AND rol = 'entrenador'", (uid,)):
        return uid
    return None


# ------------------------------------------------------------------ Pagos
@bp.route("/pagos")
@roles_required("admin")
def pagos():
    estado = request.args.get("estado", "")
    equipo_id = a_entero(request.args.get("equipo"))
    periodo = request.args.get("periodo", "")
    sql = f"""SELECT p.*, {ESTADO_PAGO_SQL} AS estado_real, u.nombre, u.apellido, e.nombre AS equipo
              FROM pagos p JOIN deportistas d ON d.id = p.deportista_id
              JOIN usuarios u ON u.id = d.usuario_id LEFT JOIN equipos e ON e.id = d.equipo_id WHERE 1=1"""
    args = []
    if estado in ("pendiente", "pagado", "vencido"):
        sql += f" AND {ESTADO_PAGO_SQL} = %s"
        args.append(estado)
    if equipo_id:
        sql += " AND d.equipo_id = %s"
        args.append(equipo_id)
    if len(periodo) == 7:
        sql += " AND p.periodo = %s"
        args.append(periodo)
    sql += " ORDER BY p.periodo DESC, FIELD(p.estado, 'pendiente', 'pagado'), u.apellido LIMIT 500"
    lista = query(sql, args)
    resumen = {
        "pendiente": sum(float(p["monto"]) for p in lista if p["estado_real"] == "pendiente"),
        "vencido": sum(float(p["monto"]) for p in lista if p["estado_real"] == "vencido"),
        "pagado": sum(float(p["monto"]) for p in lista if p["estado_real"] == "pagado"),
    }
    equipos = query("SELECT id, nombre FROM equipos ORDER BY nombre")
    deportistas = query("""SELECT d.id, u.nombre, u.apellido, e.nombre AS equipo FROM deportistas d
                           JOIN usuarios u ON u.id = d.usuario_id LEFT JOIN equipos e ON e.id = d.equipo_id
                           WHERE u.activo = 1 AND u.rol = 'deportista' ORDER BY u.apellido""")
    return render_template("admin/pagos.html", pagos=lista, resumen=resumen, equipos=equipos,
                           deportistas=deportistas, metodos=METODOS_PAGO,
                           filtros={"estado": estado, "equipo": equipo_id, "periodo": periodo},
                           periodo_actual=date.today().strftime("%Y-%m"))


@bp.route("/pagos/generar", methods=["POST"])
@roles_required("admin")
def pagos_generar():
    f = request.form
    periodo = f.get("periodo", "")
    monto = a_monto(f.get("monto"))
    try:
        anio, mes = map(int, periodo.split("-"))
        vence = date(anio, mes, min(max(a_entero(f.get("dia"), 5), 1), 28))
    except ValueError:
        vence = None
    if not vence or not monto:
        flash("Revisa el periodo, el monto y el día de vencimiento.", "error")
        return redirect(url_for("admin.pagos"))
    filas = query("""SELECT d.id FROM deportistas d JOIN usuarios u ON u.id = d.usuario_id
                     WHERE u.activo = 1 AND u.rol = 'deportista' AND d.equipo_id IS NOT NULL""")
    creados = 0
    for d in filas:
        try:
            execute("""INSERT INTO pagos (deportista_id, concepto, periodo, monto, fecha_vencimiento, registrado_por)
                       VALUES (%s,'Mensualidad',%s,%s,%s,%s)""", (d["id"], periodo, monto, vence, g.user["id"]))
            creados += 1
        except IntegrityError:
            pass  # ya existía la mensualidad de ese periodo
    flash(f"Se generaron {creados} mensualidades para {periodo}. Las existentes no se duplicaron.", "ok")
    return redirect(url_for("admin.pagos", periodo=periodo))


@bp.route("/pagos/nuevo", methods=["POST"])
@roles_required("admin")
def pago_nuevo():
    f = request.form
    deportista_id = a_entero(f.get("deportista_id"))
    monto = a_monto(f.get("monto"))
    concepto = f.get("concepto", "").strip()[:80] or "Mensualidad"
    periodo = f.get("periodo", "")
    try:
        vence = date.fromisoformat(f.get("fecha_vencimiento", ""))
        anio, mes = map(int, periodo.split("-"))
        date(anio, mes, 1)
    except ValueError:
        vence = None
    if not deportista_id or not monto or not vence:
        flash("Completa deportista, periodo, monto y vencimiento.", "error")
        return redirect(url_for("admin.pagos"))
    pagado = f.get("pagado") == "1"
    metodo = f.get("metodo") if f.get("metodo") in METODOS_PAGO else None
    try:
        execute("""INSERT INTO pagos (deportista_id, concepto, periodo, monto, fecha_vencimiento, estado,
                                      fecha_pago, metodo, notas, registrado_por)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (deportista_id, concepto, periodo, monto, vence, "pagado" if pagado else "pendiente",
                 date.today() if pagado else None, metodo if pagado else None,
                 f.get("notas", "").strip()[:255] or None, g.user["id"]))
        flash("Pago registrado.", "ok")
    except IntegrityError:
        flash("Ese deportista ya tiene un cobro con el mismo concepto en ese periodo.", "error")
    return redirect(url_for("admin.pagos"))


@bp.route("/pagos/<int:pago_id>/pagar", methods=["POST"])
@roles_required("admin")
def pago_marcar(pago_id):
    metodo = request.form.get("metodo")
    if metodo not in METODOS_PAGO:
        metodo = "efectivo"
    execute("""UPDATE pagos SET estado = 'pagado', fecha_pago = CURDATE(), metodo = %s, registrado_por = %s
               WHERE id = %s AND estado = 'pendiente'""", (metodo, g.user["id"], pago_id))
    flash("Pago marcado como pagado.", "ok")
    volver = request.form.get("volver")
    return redirect(volver if es_url_segura(volver) else url_for("admin.pagos"))


@bp.route("/pagos/<int:pago_id>/eliminar", methods=["POST"])
@roles_required("admin")
def pago_eliminar(pago_id):
    execute("DELETE FROM pagos WHERE id = %s", (pago_id,))
    flash("Cobro eliminado.", "ok")
    return redirect(url_for("admin.pagos"))
