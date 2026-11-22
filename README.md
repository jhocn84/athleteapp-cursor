# AthleteHub

Sistema web para gestionar deportistas de un club multideporte: asistencia (lista del entrenador + QR/código),
pagos de mensualidades, avisos y login/registro seguros.

**Tecnología:** Python 3.12 · Flask · MySQL/MariaDB (XAMPP, puerto 3306) · Jinja2 · Chart.js

## Instalación (Windows + XAMPP)

1. Enciende **MySQL** desde el panel de control de XAMPP (puerto 3306).
2. En PowerShell, dentro de la carpeta `athletehub`:

```powershell
python -m venv .venv
```

```powershell
.venv\Scripts\python -m pip install -r requirements.txt
```

```powershell
Copy-Item .env.example .env
```

3. Abre `.env` y pon una `SECRET_KEY` aleatoria (puedes generarla con
   `python -c "import secrets; print(secrets.token_hex(32))"`). Si tu usuario `root` de MySQL tiene contraseña, ponla en `DB_PASSWORD`.
   Define también `DEMO_ADMIN_PASSWORD` y `DEMO_USER_PASSWORD` (contraseñas de los usuarios de prueba).
4. Crea la base de datos con datos de prueba:

```powershell
.venv\Scripts\python init_db.py
```

5. Inicia la aplicación y abre http://127.0.0.1:5000

```powershell
.venv\Scripts\python app.py
```

Para borrar todo y volver a empezar: `.venv\Scripts\python init_db.py --reset`.
Para crear solo las tablas y el administrador, sin datos de ejemplo: `--sin-demo`.

## Usuarios de prueba

| Rol | Correo | Contraseña (variable de `.env`) |
|---|---|---|
| Administrador | admin@athletehub.test | `DEMO_ADMIN_PASSWORD` |
| Entrenador | carlos.ruiz@athletehub.test | `DEMO_USER_PASSWORD` |
| Entrenador | ana.torres@athletehub.test | `DEMO_USER_PASSWORD` |
| Deportista | laura.gomez@athletehub.test | `DEMO_USER_PASSWORD` |

Todos los entrenadores y deportistas de prueba usan `DEMO_USER_PASSWORD`. Las contraseñas deben cumplir la política
(8+ caracteres, mayúscula, minúscula, número y símbolo). **Antes de usar el sistema con datos reales,** ejecuta
`init_db.py --reset --sin-demo` y cambia la contraseña del administrador desde *Mi perfil*.

## Roles

- **Administrador:** resumen del club, usuarios (rol, equipo, dorsal, activar/desactivar), deportes y equipos,
  mensualidades (generar el mes completo, registrar y marcar pagos), avisos para todo el club, un deporte o un equipo.
- **Entrenador:** sus equipos con % de asistencia, programar entrenamientos, tomar lista
  (presente, tarde, justificado, ausente), generar QR, avisos para sus equipos.
- **Deportista:** su tarjeta de perfil, asistencia con gráfica, pagos, avisos y registro de asistencia por QR o código.

## Asistencia por QR

1. El entrenador abre el entrenamiento y pulsa **Generar QR** (válido 15 minutos, configurable con `QR_MINUTOS`).
2. El deportista escanea el QR con la cámara del celular o escribe el código de 6 caracteres en *Marcar asistencia*.
3. Si llega más de 10 minutos después de la hora de inicio, queda como **tarde**.

Para que el celular abra el enlace del QR, el servidor debe ser accesible en la red local: pon `HOST=0.0.0.0` en `.env`
y abre la app desde el PC con su IP (por ejemplo `http://192.168.1.20:5000`), no con `127.0.0.1`.
El código de 6 caracteres funciona siempre.

## Seguridad

- Contraseñas con **bcrypt** (12 rondas). Nunca se guardan en texto plano.
- Política de contraseña: 8+ caracteres, mayúscula, minúscula, número y símbolo.
- **CSRF** en todos los formularios (Flask-WTF) y logout solo por POST.
- **Consultas parametrizadas** en todo el código (sin inyección SQL).
- Cookies de sesión `HttpOnly` y `SameSite=Lax`, expiración de 2 horas, rotación de sesión al iniciar sesión
  y al cambiar contraseña. Con HTTPS, activa `SESSION_COOKIE_SECURE=1`.
- Mensajes de login genéricos y tiempo de respuesta constante (no revelan qué correos existen).
- El registro público solo crea **deportistas**; los roles los asigna un administrador.
- Si un usuario se desactiva o cambia de rol, su sesión abierta deja de ser válida en la siguiente petición.
- Cabeceras: Content-Security-Policy, X-Frame-Options, X-Content-Type-Options, Referrer-Policy.
- Control de acceso por rol y por propiedad (un entrenador solo ve y gestiona sus equipos).

## Estructura

```
athletehub/
├── app.py            # aplicación Flask, filtros, cabeceras de seguridad
├── db.py             # conexión MySQL (PyMySQL)
├── security.py       # bcrypt, política de contraseñas, decoradores de rol
├── helpers.py        # consultas compartidas (avisos, asistencia, estado de pago)
├── init_db.py        # crea la BD y los datos de prueba
├── database/schema.sql
├── routes/           # auth, admin, entrenador, deportista, avisos, perfil
├── templates/        # vistas Jinja2
└── static/           # css, js, img
```
