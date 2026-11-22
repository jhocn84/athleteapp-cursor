"""
Crea la base de datos de AthleteHub en MySQL (puerto 3306) y carga datos de prueba.

Uso:
    python init_db.py             -> crea tablas y datos de prueba (si la BD está vacía)
    python init_db.py --reset     -> BORRA la base de datos y la vuelve a crear
    python init_db.py --reset --sin-demo  -> base de datos LIMPIA para uso real; pide el
                                            correo y la contraseña del administrador

Usuarios de PRUEBA que crea este script (solo para desarrollo local). Sus contraseñas
se leen del archivo .env (DEMO_ADMIN_PASSWORD y DEMO_USER_PASSWORD):
    Administrador:  admin@athletehub.test       ->  DEMO_ADMIN_PASSWORD
    Entrenadores:   carlos.ruiz@athletehub.test ->  DEMO_USER_PASSWORD
                    ana.torres@athletehub.test  ->  DEMO_USER_PASSWORD
    Deportistas:    laura.gomez@athletehub.test ->  DEMO_USER_PASSWORD  (y el resto de deportistas demo)
"""
import argparse
import getpass
import os
import random
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pymysql
from dotenv import load_dotenv

from security import EMAIL_RE, hash_password, password_errors

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")

DB = dict(
    host=os.getenv("DB_HOST", "127.0.0.1"),
    port=int(os.getenv("DB_PORT", "3306")),
    user=os.getenv("DB_USER", "root"),
    password=os.getenv("DB_PASSWORD", ""),
)
DB_NAME = os.getenv("DB_NAME", "athletehub")

# Contraseñas de los usuarios de prueba: se definen en .env, nunca en el código.
ADMIN_PASS = os.getenv("DEMO_ADMIN_PASSWORD", "")
DEMO_PASS = os.getenv("DEMO_USER_PASSWORD", "")


def conectar(con_bd=True):
    params = dict(DB, charset="utf8mb4", autocommit=True,
                  cursorclass=pymysql.cursors.DictCursor)
    if con_bd:
        params["database"] = DB_NAME
    return pymysql.connect(**params)


def ejecutar_schema(cur):
    sql = (BASE / "database" / "schema.sql").read_text(encoding="utf-8")
    sql = sql.replace("athletehub", DB_NAME)  # respeta DB_NAME del .env
    sentencias, actual = [], []
    for linea in sql.splitlines():
        if linea.strip().startswith("--"):
            continue
        actual.append(linea)
        if linea.rstrip().endswith(";"):
            sentencias.append("\n".join(actual))
            actual = []
    for s in sentencias:
        if s.strip():
            cur.execute(s)


def crear_usuario(cur, nombre, apellido, email, password, rol):
    cur.execute(
        "INSERT INTO usuarios (nombre, apellido, email, password_hash, rol) VALUES (%s,%s,%s,%s,%s)",
        (nombre, apellido, email, hash_password(password), rol),
    )
    return cur.lastrowid


def cargar_demo(cur, admin_id):
    random.seed(7)
    hoy = date.today()

    # --- Entrenadores
    carlos = crear_usuario(cur, "Carlos", "Ruiz", "carlos.ruiz@athletehub.test", DEMO_PASS, "entrenador")
    ana = crear_usuario(cur, "Ana", "Torres", "ana.torres@athletehub.test", DEMO_PASS, "entrenador")

    # --- Deportes y equipos
    cur.execute("INSERT INTO deportes (nombre, descripcion) VALUES ('Voleibol','Sala y playa'), ('Fútbol','Fútbol 11')")
    cur.execute("SELECT id, nombre FROM deportes")
    dep = {r["nombre"]: r["id"] for r in cur.fetchall()}
    equipos = [
        (dep["Voleibol"], "Voleibol Sub-18", "Sub-18", carlos),
        (dep["Voleibol"], "Voleibol Mayores", "Mayores", carlos),
        (dep["Fútbol"], "Fútbol Sub-16", "Sub-16", ana),
    ]
    eq_ids = []
    for e in equipos:
        cur.execute("INSERT INTO equipos (deporte_id, nombre, categoria, entrenador_id) VALUES (%s,%s,%s,%s)", e)
        eq_ids.append(cur.lastrowid)

    # --- Deportistas
    plantilla = {
        eq_ids[0]: [("Laura", "Gómez", "Opuesta", 7), ("Sofía", "Martínez", "Armadora", 3),
                    ("Valentina", "Rojas", "Líbero", 1), ("Camila", "Díaz", "Central", 12),
                    ("Mariana", "López", "Punta", 9)],
        eq_ids[1]: [("Daniela", "Pérez", "Punta", 4), ("Paula", "Castro", "Central", 15),
                    ("Andrea", "Vargas", "Armadora", 6)],
        eq_ids[2]: [("Mateo", "Hernández", "Portero", 1), ("Santiago", "Moreno", "Defensa", 4),
                    ("Samuel", "Jiménez", "Mediocampista", 8), ("Tomás", "Romero", "Delantero", 9),
                    ("Nicolás", "Suárez", "Defensa", 5)],
    }
    deportistas = {}  # equipo_id -> [deportista_id]
    for equipo_id, jugadores in plantilla.items():
        for nombre, apellido, posicion, dorsal in jugadores:
            email = f"{nombre}.{apellido}@athletehub.test".lower()
            email = (email.replace("á", "a").replace("é", "e").replace("í", "i")
                          .replace("ó", "o").replace("ú", "u"))
            uid = crear_usuario(cur, nombre, apellido, email, DEMO_PASS, "deportista")
            nacimiento = date(hoy.year - random.randint(15, 25), random.randint(1, 12), random.randint(1, 28))
            cur.execute(
                """INSERT INTO deportistas (usuario_id, equipo_id, documento, fecha_nacimiento, telefono,
                                            posicion, dorsal, contacto_emergencia)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (uid, equipo_id, str(random.randint(10_000_000, 99_999_999)), nacimiento,
                 f"3{random.randint(100_000_000, 199_999_999)}", posicion, dorsal, "Familiar - 3001234567"),
            )
            deportistas.setdefault(equipo_id, []).append(cur.lastrowid)

    # --- Entrenamientos de las últimas 4 semanas (lun, mié, vie) con asistencia
    estados = ["presente"] * 14 + ["tarde"] * 2 + ["ausente"] * 2 + ["justificado"]
    for equipo_id, ids in deportistas.items():
        autor = carlos if equipo_id != eq_ids[2] else ana
        for dias_atras in range(28, -8, -1):
            dia = hoy - timedelta(days=dias_atras)
            if dia.weekday() not in (0, 2, 4):
                continue
            cur.execute(
                """INSERT INTO entrenamientos (equipo_id, fecha, hora_inicio, hora_fin, lugar, creado_por)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (equipo_id, dia, time(18, 0), time(20, 0), "Coliseo principal", autor),
            )
            ent_id = cur.lastrowid
            if dia < hoy:
                for did in ids:
                    cur.execute(
                        "INSERT INTO asistencias (entrenamiento_id, deportista_id, estado, metodo) VALUES (%s,%s,%s,%s)",
                        (ent_id, did, random.choice(estados), random.choice(["manual", "qr"])),
                    )

    # --- Pagos: 2 meses anteriores pagados (casi todos) y el mes actual pendiente
    for equipo_id, ids in deportistas.items():
        for did in ids:
            for meses_atras in (2, 1, 0):
                y, m = hoy.year, hoy.month - meses_atras
                while m <= 0:
                    m += 12
                    y -= 1
                periodo = f"{y}-{m:02d}"
                vence = date(y, m, 5)
                pagado = meses_atras > 0 and random.random() > 0.15
                cur.execute(
                    """INSERT INTO pagos (deportista_id, periodo, monto, fecha_vencimiento, estado,
                                          fecha_pago, metodo)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (did, periodo, 80000, vence, "pagado" if pagado else "pendiente",
                     vence - timedelta(days=random.randint(0, 4)) if pagado else None,
                     random.choice(["efectivo", "transferencia"]) if pagado else None),
                )

    # --- Avisos
    cur.executemany(
        """INSERT INTO avisos (titulo, contenido, alcance, deporte_id, equipo_id, prioridad, autor_id, creado_en)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        [
            ("Cambio de horario", "Desde la próxima semana los entrenamientos inician a las 6:00 p. m.",
             "todos", None, None, "importante", admin_id, datetime.now() - timedelta(days=2)),
            ("Torneo regional", "El sábado jugamos el torneo regional. Presentarse a las 7:00 a. m. con uniforme completo.",
             "equipo", None, eq_ids[0], "importante", carlos, datetime.now() - timedelta(days=1)),
            ("Revisión médica", "Todos los deportistas de voleibol deben entregar el certificado médico este mes.",
             "deporte", dep["Voleibol"], None, "normal", admin_id, datetime.now() - timedelta(days=5)),
            ("Nuevos balones", "Llegaron los balones nuevos para la categoría Sub-16.",
             "equipo", None, eq_ids[2], "normal", ana, datetime.now() - timedelta(days=3)),
        ],
    )


def main():
    parser = argparse.ArgumentParser(description="Inicializa la base de datos de AthleteHub")
    parser.add_argument("--reset", action="store_true", help="borra y recrea la base de datos")
    parser.add_argument("--sin-demo", action="store_true", help="no cargar datos de prueba")
    args = parser.parse_args()

    admin = None
    if args.sin_demo:
        admin = pedir_admin()
    elif not ADMIN_PASS or not DEMO_PASS:
        sys.exit("Define DEMO_ADMIN_PASSWORD y DEMO_USER_PASSWORD en el archivo .env "
                 "para crear los usuarios de prueba (o usa --sin-demo).")

    try:
        con = conectar(con_bd=False)
    except pymysql.err.OperationalError as e:
        sys.exit(f"No se pudo conectar a MySQL en {DB['host']}:{DB['port']}. ¿Está encendido en XAMPP?\n{e}")

    with con.cursor() as cur:
        if args.reset:
            cur.execute(f"DROP DATABASE IF EXISTS `{DB_NAME}`")
            print(f"Base de datos '{DB_NAME}' eliminada.")
        ejecutar_schema(cur)
        cur.execute(f"USE `{DB_NAME}`")
        cur.execute("SELECT COUNT(*) AS n FROM usuarios")
        if cur.fetchone()["n"] > 0:
            print("Las tablas ya existen y tienen datos. Usa --reset para empezar de cero.")
            return
        if admin:
            crear_usuario(cur, admin["nombre"], admin["apellido"], admin["email"], admin["password"], "admin")
        else:
            admin_id = crear_usuario(cur, "Admin", "AthleteHub", "admin@athletehub.test", ADMIN_PASS, "admin")
            cargar_demo(cur, admin_id)
    con.close()
    print(f"Base de datos '{DB_NAME}' lista en {DB['host']}:{DB['port']}.")
    if admin:
        print(f"Administrador creado: {admin['email']}. Ya puedes iniciar sesión.")
    else:
        print("Usuarios de prueba creados. Sus contraseñas son DEMO_ADMIN_PASSWORD y "
              "DEMO_USER_PASSWORD de tu archivo .env.")


def pedir_admin():
    """Pide los datos del administrador real (la contraseña no se muestra al escribir)."""
    print("Datos del administrador del club")
    nombre = input("  Nombre: ").strip()[:60] or "Admin"
    apellido = input("  Apellido: ").strip()[:60] or "AthleteHub"
    while True:
        email = input("  Correo: ").strip().lower()
        if EMAIL_RE.match(email):
            break
        print("  Correo no válido.")
    while True:
        pw = getpass.getpass("  Contraseña (no se ve al escribir): ")
        errores = password_errors(pw, email)
        if errores:
            print("  " + " ".join(errores))
            continue
        if getpass.getpass("  Repite la contraseña: ") != pw:
            print("  No coinciden.")
            continue
        return {"nombre": nombre, "apellido": apellido, "email": email, "password": pw}


if __name__ == "__main__":
    main()
