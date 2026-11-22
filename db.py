"""Conexión a MySQL (PyMySQL). Todas las consultas usan parámetros (%s) para evitar inyección SQL."""
import pymysql
from flask import current_app, g


def get_db():
    if "db" not in g:
        cfg = current_app.config
        g.db = pymysql.connect(
            host=cfg["DB_HOST"],
            port=cfg["DB_PORT"],
            user=cfg["DB_USER"],
            password=cfg["DB_PASSWORD"],
            database=cfg["DB_NAME"],
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, args=(), one=False):
    """SELECT: devuelve lista de dicts (o un dict / None si one=True)."""
    with get_db().cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchone() if one else cur.fetchall()


def scalar(sql, args=()):
    row = query(sql, args, one=True)
    return next(iter(row.values())) if row else None


def execute(sql, args=()):
    """INSERT/UPDATE/DELETE con commit. Devuelve el último id insertado."""
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(sql, args)
            last_id = cur.lastrowid
        db.commit()
        return last_id
    except Exception:
        db.rollback()
        raise


def execute_many(sql, seq):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.executemany(sql, seq)
            filas = cur.rowcount
        db.commit()
        return filas
    except Exception:
        db.rollback()
        raise


def init_app(app):
    app.teardown_appcontext(close_db)
