-- =============================================================
--  AthleteHub - Esquema de base de datos (MySQL / MariaDB)
--  Puerto por defecto: 3306
--  Ejecutar con:  python init_db.py   (o importar en phpMyAdmin)
-- =============================================================

CREATE DATABASE IF NOT EXISTS athletehub
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE athletehub;

-- -------------------------------------------------------------
-- Usuarios del sistema (login). Las contraseñas se guardan
-- únicamente como hash bcrypt, nunca en texto plano.
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS usuarios (
  id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  nombre          VARCHAR(60)  NOT NULL,
  apellido        VARCHAR(60)  NOT NULL,
  email           VARCHAR(120) NOT NULL UNIQUE,
  password_hash   VARCHAR(100) NOT NULL,
  rol             ENUM('admin','entrenador','deportista') NOT NULL DEFAULT 'deportista',
  activo          TINYINT(1)   NOT NULL DEFAULT 1,
  ultimo_acceso   DATETIME     NULL,
  creado_en       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_usuarios_rol (rol)
) ENGINE=InnoDB;

-- -------------------------------------------------------------
-- Deportes del club
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS deportes (
  id           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  nombre       VARCHAR(60)  NOT NULL UNIQUE,
  descripcion  VARCHAR(255) NULL
) ENGINE=InnoDB;

-- -------------------------------------------------------------
-- Equipos / categorías (pertenecen a un deporte)
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS equipos (
  id             INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  deporte_id     INT UNSIGNED NOT NULL,
  nombre         VARCHAR(80)  NOT NULL,
  categoria      VARCHAR(40)  NULL,
  entrenador_id  INT UNSIGNED NULL,
  CONSTRAINT fk_equipos_deporte    FOREIGN KEY (deporte_id)    REFERENCES deportes(id) ON DELETE RESTRICT,
  CONSTRAINT fk_equipos_entrenador FOREIGN KEY (entrenador_id) REFERENCES usuarios(id) ON DELETE SET NULL,
  UNIQUE KEY uq_equipo (deporte_id, nombre)
) ENGINE=InnoDB;

-- -------------------------------------------------------------
-- Ficha deportiva (1 a 1 con usuarios de rol deportista)
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS deportistas (
  id                  INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  usuario_id          INT UNSIGNED NOT NULL UNIQUE,
  equipo_id           INT UNSIGNED NULL,
  documento           VARCHAR(20)  NULL,
  fecha_nacimiento    DATE         NULL,
  telefono            VARCHAR(20)  NULL,
  posicion            VARCHAR(40)  NULL,
  dorsal              TINYINT UNSIGNED NULL,
  contacto_emergencia VARCHAR(120) NULL,
  CONSTRAINT fk_deportistas_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
  CONSTRAINT fk_deportistas_equipo  FOREIGN KEY (equipo_id)  REFERENCES equipos(id)  ON DELETE SET NULL
) ENGINE=InnoDB;

-- -------------------------------------------------------------
-- Entrenamientos (sesiones). qr_token / qr_codigo permiten
-- el registro de asistencia por QR o código durante qr_expira.
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS entrenamientos (
  id           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  equipo_id    INT UNSIGNED NOT NULL,
  fecha        DATE         NOT NULL,
  hora_inicio  TIME         NOT NULL,
  hora_fin     TIME         NULL,
  lugar        VARCHAR(100) NULL,
  qr_token     VARCHAR(64)  NULL UNIQUE,
  qr_codigo    CHAR(6)      NULL,
  qr_expira    DATETIME     NULL,
  creado_por   INT UNSIGNED NULL,
  creado_en    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_entrenamientos_equipo FOREIGN KEY (equipo_id)  REFERENCES equipos(id)  ON DELETE CASCADE,
  CONSTRAINT fk_entrenamientos_autor  FOREIGN KEY (creado_por) REFERENCES usuarios(id) ON DELETE SET NULL,
  INDEX idx_entrenamientos_fecha (equipo_id, fecha)
) ENGINE=InnoDB;

-- -------------------------------------------------------------
-- Asistencia por entrenamiento y deportista
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS asistencias (
  id               INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  entrenamiento_id INT UNSIGNED NOT NULL,
  deportista_id    INT UNSIGNED NOT NULL,
  estado           ENUM('presente','ausente','tarde','justificado') NOT NULL,
  metodo           ENUM('manual','qr') NOT NULL DEFAULT 'manual',
  registrado_en    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_asistencias_entrenamiento FOREIGN KEY (entrenamiento_id) REFERENCES entrenamientos(id) ON DELETE CASCADE,
  CONSTRAINT fk_asistencias_deportista    FOREIGN KEY (deportista_id)    REFERENCES deportistas(id)    ON DELETE CASCADE,
  UNIQUE KEY uq_asistencia (entrenamiento_id, deportista_id)
) ENGINE=InnoDB;

-- -------------------------------------------------------------
-- Pagos / mensualidades. El estado "vencido" se calcula:
-- pendiente + fecha_vencimiento < hoy.
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pagos (
  id                 INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  deportista_id      INT UNSIGNED  NOT NULL,
  concepto           VARCHAR(80)   NOT NULL DEFAULT 'Mensualidad',
  periodo            CHAR(7)       NOT NULL,          -- formato AAAA-MM
  monto              DECIMAL(10,2) NOT NULL,
  fecha_vencimiento  DATE          NOT NULL,
  estado             ENUM('pendiente','pagado') NOT NULL DEFAULT 'pendiente',
  fecha_pago         DATE          NULL,
  metodo             ENUM('efectivo','transferencia','tarjeta','otro') NULL,
  notas              VARCHAR(255)  NULL,
  registrado_por     INT UNSIGNED  NULL,
  creado_en          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_pagos_deportista FOREIGN KEY (deportista_id)  REFERENCES deportistas(id) ON DELETE CASCADE,
  CONSTRAINT fk_pagos_usuario    FOREIGN KEY (registrado_por) REFERENCES usuarios(id)    ON DELETE SET NULL,
  UNIQUE KEY uq_pago_periodo (deportista_id, periodo, concepto),
  INDEX idx_pagos_estado (estado, fecha_vencimiento)
) ENGINE=InnoDB;

-- -------------------------------------------------------------
-- Avisos: para todos, para un deporte o para un equipo
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS avisos (
  id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  titulo      VARCHAR(120) NOT NULL,
  contenido   TEXT         NOT NULL,
  alcance     ENUM('todos','deporte','equipo') NOT NULL DEFAULT 'todos',
  deporte_id  INT UNSIGNED NULL,
  equipo_id   INT UNSIGNED NULL,
  prioridad   ENUM('normal','importante') NOT NULL DEFAULT 'normal',
  autor_id    INT UNSIGNED NULL,
  creado_en   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_avisos_deporte FOREIGN KEY (deporte_id) REFERENCES deportes(id) ON DELETE CASCADE,
  CONSTRAINT fk_avisos_equipo  FOREIGN KEY (equipo_id)  REFERENCES equipos(id)  ON DELETE CASCADE,
  CONSTRAINT fk_avisos_autor   FOREIGN KEY (autor_id)   REFERENCES usuarios(id) ON DELETE SET NULL,
  INDEX idx_avisos_fecha (creado_en)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS avisos_leidos (
  aviso_id    INT UNSIGNED NOT NULL,
  usuario_id  INT UNSIGNED NOT NULL,
  leido_en    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (aviso_id, usuario_id),
  CONSTRAINT fk_leidos_aviso   FOREIGN KEY (aviso_id)   REFERENCES avisos(id)   ON DELETE CASCADE,
  CONSTRAINT fk_leidos_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB;
