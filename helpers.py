"""Consultas y utilidades compartidas entre módulos."""
from datetime import date, timedelta

from db import query, scalar

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]

# Estado real del pago: "vencido" se calcula a partir de la fecha de vencimiento.
ESTADO_PAGO_SQL = ("CASE WHEN p.estado = 'pendiente' AND p.fecha_vencimiento < CURDATE() "
                   "THEN 'vencido' ELSE p.estado END")

ESTADOS_ASISTENCIA = ["presente", "tarde", "justificado", "ausente"]


def porcentaje(parte, total):
    return round(100 * parte / total) if total else 0


def nombre_periodo(periodo: str) -> str:
    """'2026-11' -> 'noviembre 2026'."""
    try:
        anio, mes = periodo.split("-")
        return f"{MESES[int(mes) - 1]} {anio}"
    except (ValueError, IndexError):
        return periodo


def filtro_avisos(user):
    """Cláusula WHERE (alias a) con los avisos que puede ver el usuario."""
    uid = user["id"]
    if user["rol"] == "admin":
        return "1=1", []
    if user["rol"] == "entrenador":
        return ("(a.alcance = 'todos' OR a.autor_id = %s"
                " OR (a.alcance = 'equipo' AND a.equipo_id IN (SELECT id FROM equipos WHERE entrenador_id = %s))"
                " OR (a.alcance = 'deporte' AND a.deporte_id IN (SELECT deporte_id FROM equipos WHERE entrenador_id = %s)))",
                [uid, uid, uid])
    return ("(a.alcance = 'todos'"
            " OR (a.alcance = 'equipo' AND a.equipo_id = (SELECT d.equipo_id FROM deportistas d WHERE d.usuario_id = %s))"
            " OR (a.alcance = 'deporte' AND a.deporte_id = (SELECT e.deporte_id FROM deportistas d"
            "      JOIN equipos e ON e.id = d.equipo_id WHERE d.usuario_id = %s)))",
            [uid, uid])


def avisos_visibles(user, limite=None):
    where, args = filtro_avisos(user)
    sql = f"""
        SELECT a.*, CONCAT(u.nombre, ' ', u.apellido) AS autor, u.rol AS autor_rol,
               dp.nombre AS deporte, eq.nombre AS equipo,
               (al.usuario_id IS NOT NULL) AS leido
        FROM avisos a
        LEFT JOIN usuarios u ON u.id = a.autor_id
        LEFT JOIN deportes dp ON dp.id = a.deporte_id
        LEFT JOIN equipos eq ON eq.id = a.equipo_id
        LEFT JOIN avisos_leidos al ON al.aviso_id = a.id AND al.usuario_id = %s
        WHERE {where}
        ORDER BY a.creado_en DESC"""
    args = [user["id"], *args]
    if limite:
        sql += " LIMIT %s"
        args.append(limite)
    return query(sql, args)


def avisos_no_leidos(user):
    where, args = filtro_avisos(user)
    return scalar(f"""
        SELECT COUNT(*) FROM avisos a
        LEFT JOIN avisos_leidos al ON al.aviso_id = a.id AND al.usuario_id = %s
        WHERE al.usuario_id IS NULL AND {where}""", [user["id"], *args]) or 0


def resumen_asistencia_equipo(equipo_id, dias=30):
    """% de asistencia (presente + tarde) del equipo en los últimos N días."""
    desde = date.today() - timedelta(days=dias)
    fila = query("""
        SELECT COUNT(a.id) AS registros,
               SUM(a.estado IN ('presente','tarde')) AS asistio
        FROM entrenamientos t
        JOIN asistencias a ON a.entrenamiento_id = t.id
        WHERE t.equipo_id = %s AND t.fecha BETWEEN %s AND CURDATE()""", (equipo_id, desde), one=True)
    return porcentaje(int(fila["asistio"] or 0), int(fila["registros"] or 0))


def puede_gestionar_equipo(user, equipo_id) -> bool:
    if user["rol"] == "admin":
        return True
    if user["rol"] != "entrenador":
        return False
    return bool(scalar("SELECT COUNT(*) FROM equipos WHERE id = %s AND entrenador_id = %s",
                       (equipo_id, user["id"])))
