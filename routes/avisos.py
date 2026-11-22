"""Avisos: listado según el rol, marcado como leído y publicación (admin y entrenador)."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from db import execute, query
from helpers import avisos_visibles, filtro_avisos
from security import login_required, roles_required

bp = Blueprint("avisos", __name__, url_prefix="/avisos")


@bp.route("/")
@login_required
def lista():
    avisos = avisos_visibles(g.user)
    return render_template("avisos/lista.html", avisos=avisos)


@bp.route("/<int:aviso_id>/leido", methods=["POST"])
@login_required
def marcar_leido(aviso_id):
    where, args = filtro_avisos(g.user)
    if query(f"SELECT a.id FROM avisos a WHERE a.id = %s AND {where}", [aviso_id, *args], one=True):
        execute("INSERT IGNORE INTO avisos_leidos (aviso_id, usuario_id) VALUES (%s,%s)", (aviso_id, g.user["id"]))
    return redirect(url_for("avisos.lista"))


@bp.route("/leer-todos", methods=["POST"])
@login_required
def leer_todos():
    where, args = filtro_avisos(g.user)
    execute(f"""INSERT IGNORE INTO avisos_leidos (aviso_id, usuario_id)
                SELECT a.id, %s FROM avisos a WHERE {where}""", [g.user["id"], *args])
    flash("Todos los avisos quedaron como leídos.", "ok")
    return redirect(url_for("avisos.lista"))


def destinos_permitidos():
    if g.user["rol"] == "admin":
        deportes = query("SELECT id, nombre FROM deportes ORDER BY nombre")
        equipos = query("SELECT id, nombre FROM equipos ORDER BY nombre")
    else:
        deportes = []
        equipos = query("SELECT id, nombre FROM equipos WHERE entrenador_id = %s ORDER BY nombre", (g.user["id"],))
    return deportes, equipos


@bp.route("/nuevo", methods=["GET", "POST"])
@roles_required("admin", "entrenador")
def nuevo():
    deportes, equipos = destinos_permitidos()
    datos = {}
    if request.method == "POST":
        f = request.form
        datos = {"titulo": f.get("titulo", "").strip()[:120], "contenido": f.get("contenido", "").strip()[:3000],
                 "alcance": f.get("alcance", "todos"), "prioridad": f.get("prioridad", "normal")}
        deporte_id = equipo_id = None
        errores = []
        if len(datos["titulo"]) < 3 or len(datos["contenido"]) < 3:
            errores.append("Escribe un título y un mensaje.")
        if datos["prioridad"] not in ("normal", "importante"):
            datos["prioridad"] = "normal"
        if datos["alcance"] == "todos":
            if g.user["rol"] != "admin":
                errores.append("Solo la administración puede publicar avisos para todo el club.")
        elif datos["alcance"] == "deporte":
            deporte_id = int(f.get("deporte_id", "0")) if f.get("deporte_id", "").isdigit() else 0
            if deporte_id not in {d["id"] for d in deportes}:
                errores.append("Elige un deporte válido.")
        elif datos["alcance"] == "equipo":
            equipo_id = int(f.get("equipo_id", "0")) if f.get("equipo_id", "").isdigit() else 0
            if equipo_id not in {e["id"] for e in equipos}:
                errores.append("Elige uno de tus equipos.")
        else:
            abort(400)
        if not errores:
            execute("""INSERT INTO avisos (titulo, contenido, alcance, deporte_id, equipo_id, prioridad, autor_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (datos["titulo"], datos["contenido"], datos["alcance"], deporte_id, equipo_id,
                     datos["prioridad"], g.user["id"]))
            flash("Aviso publicado.", "ok")
            return redirect(url_for("avisos.lista"))
        for e in errores:
            flash(e, "error")
    return render_template("avisos/nuevo.html", deportes=deportes, equipos=equipos, datos=datos)


@bp.route("/<int:aviso_id>/eliminar", methods=["POST"])
@roles_required("admin", "entrenador")
def eliminar(aviso_id):
    aviso = query("SELECT autor_id FROM avisos WHERE id = %s", (aviso_id,), one=True)
    if not aviso:
        abort(404)
    if g.user["rol"] != "admin" and aviso["autor_id"] != g.user["id"]:
        abort(403)
    execute("DELETE FROM avisos WHERE id = %s", (aviso_id,))
    flash("Aviso eliminado.", "ok")
    return redirect(url_for("avisos.lista"))
