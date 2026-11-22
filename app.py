"""AthleteHub - Gestión de deportistas, asistencia, pagos y avisos (Flask + MySQL)."""
import os
from datetime import date, datetime, timedelta

from dotenv import load_dotenv
from flask import Flask, g, redirect, render_template, session, url_for
from flask_wtf.csrf import CSRFError
from werkzeug.middleware.proxy_fix import ProxyFix

import db
from extensions import csrf, limiter
from helpers import DIAS, MESES, avisos_no_leidos, nombre_periodo


def create_app():
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
    secret = os.getenv("SECRET_KEY")
    if not secret or len(secret) < 32:
        raise RuntimeError("Define SECRET_KEY (mínimo 32 caracteres) en el archivo .env")

    app = Flask(__name__)
    app.config.update(
        APP_NAME="AthleteHub",
        SECRET_KEY=secret,
        DB_HOST=os.getenv("DB_HOST", "127.0.0.1"),
        DB_PORT=int(os.getenv("DB_PORT", "3306")),
        DB_USER=os.getenv("DB_USER", "root"),
        DB_PASSWORD=os.getenv("DB_PASSWORD", ""),
        DB_NAME=os.getenv("DB_NAME", "athletehub"),
        QR_MINUTOS=int(os.getenv("QR_MINUTOS", "15")),
        # Cookies de sesión seguras
        SESSION_COOKIE_NAME="athletehub_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "0") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=2),
        WTF_CSRF_TIME_LIMIT=7200,
        MAX_CONTENT_LENGTH=1 * 1024 * 1024,
    )

    csrf.init_app(app)
    limiter.init_app(app)
    db.init_app(app)

    if os.getenv("TRUST_PROXY", "0") == "1":
        # Detrás de Cloudflare Tunnel: usa el esquema (https) y el host públicos
        # para cookies seguras, CSRF y los enlaces del QR.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    from routes.admin import bp as admin_bp
    from routes.auth import bp as auth_bp
    from routes.avisos import bp as avisos_bp
    from routes.deportista import bp as deportista_bp
    from routes.entrenador import bp as entrenador_bp
    from routes.perfil import bp as perfil_bp

    for bp in (auth_bp, admin_bp, entrenador_bp, deportista_bp, avisos_bp, perfil_bp):
        app.register_blueprint(bp)

    @app.before_request
    def cargar_usuario():
        g.user = None
        uid = session.get("user_id")
        if uid is None:
            return
        user = db.query("SELECT id, nombre, apellido, email, rol, activo FROM usuarios WHERE id = %s",
                        (uid,), one=True)
        # Si el usuario fue desactivado o cambió de rol, la sesión deja de ser válida.
        if not user or not user["activo"] or user["rol"] != session.get("rol"):
            session.clear()
            return
        g.user = user

    @app.context_processor
    def contexto_global():
        datos = {"app_name": app.config["APP_NAME"], "hoy": date.today(), "avisos_pendientes": 0}
        if g.get("user"):
            datos["avisos_pendientes"] = avisos_no_leidos(g.user)
        return datos

    @app.after_request
    def cabeceras_seguridad(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://cdn.jsdelivr.net; "
            "style-src 'self' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "frame-ancestors 'none'; form-action 'self'; base-uri 'self'"
        )
        if g.get("user"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    # ---------- Filtros de plantilla
    @app.template_filter("fecha")
    def f_fecha(valor):
        if not valor:
            return "—"
        if isinstance(valor, datetime):
            valor = valor.date()
        return f"{DIAS[valor.weekday()]} {valor.day} {MESES[valor.month - 1][:3]} {valor.year}"

    @app.template_filter("fecha_corta")
    def f_fecha_corta(valor):
        return f"{valor.day} {MESES[valor.month - 1][:3]}" if valor else "—"

    @app.template_filter("fecha_hora")
    def f_fecha_hora(valor):
        return f"{f_fecha_corta(valor)} · {valor:%H:%M}" if valor else "—"

    @app.template_filter("hora")
    def f_hora(valor):
        if valor is None:
            return "—"
        if isinstance(valor, timedelta):  # PyMySQL devuelve TIME como timedelta
            minutos = int(valor.total_seconds()) // 60
            return f"{minutos // 60:02d}:{minutos % 60:02d}"
        return valor.strftime("%H:%M")

    @app.template_filter("dinero")
    def f_dinero(valor):
        return "$ " + f"{float(valor or 0):,.0f}".replace(",", ".")

    @app.template_filter("periodo")
    def f_periodo(valor):
        return nombre_periodo(valor)

    @app.template_filter("iniciales")
    def f_iniciales(u):
        return (u.get("nombre", " ")[:1] + u.get("apellido", " ")[:1]).upper()

    # ---------- Rutas base y errores
    @app.route("/")
    def inicio():
        if not g.user:
            return redirect(url_for("auth.login"))
        return redirect(url_for({"admin": "admin.panel", "entrenador": "entrenador.panel"}
                                .get(g.user["rol"], "deportista.panel")))

    @app.errorhandler(403)
    def prohibido(_e):
        return render_template("error.html", codigo=403, mensaje="No tienes permiso para ver esta página."), 403

    @app.errorhandler(404)
    def no_encontrado(_e):
        return render_template("error.html", codigo=404, mensaje="La página que buscas no existe."), 404

    @app.errorhandler(429)
    def demasiados_intentos(_e):
        return render_template("error.html", codigo=429,
                               mensaje="Demasiados intentos seguidos. Espera unos minutos y vuelve a intentarlo."), 429

    @app.errorhandler(CSRFError)
    def csrf_error(_e):
        return render_template("error.html", codigo=400,
                               mensaje="El formulario expiró o no es válido. Recarga la página e inténtalo de nuevo."), 400

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "5000")),
            debug=os.getenv("FLASK_DEBUG", "0") == "1")
