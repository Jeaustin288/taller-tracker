from flask import Flask, request, jsonify, render_template
import psycopg2
import psycopg2.extras
import csv
import io
import os

app = Flask(__name__)

def get_db():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS vehiculos (
            chasis TEXT PRIMARY KEY, marca TEXT, modelo TEXT, color TEXT,
            cliente TEXT, estado2 TEXT, ubicacion TEXT, localizacion2 TEXT,
            producto TEXT, ultima_toma TEXT
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS taller_data (
            chasis TEXT PRIMARY KEY, fecha_reporte TEXT, fecha_entrada TEXT,
            fecha_salida_est TEXT, problemas TEXT, origen_dano TEXT, notas TEXT,
            FOREIGN KEY (chasis) REFERENCES vehiculos(chasis)
        );
    """)
    conn.commit()
    # Agregar columnas nuevas si la tabla ya existe (cada una en su propia transacción)
    for col in [("fecha_reporte", "TEXT"), ("origen_dano", "TEXT")]:
        try:
            cur.execute(f"ALTER TABLE taller_data ADD COLUMN {col[0]} {col[1]}")
            conn.commit()
        except Exception:
            conn.rollback()
    cur.close()
    conn.close()

init_db()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/upload_csv", methods=["POST"])
def upload_csv():
    file = request.files.get("csv_file")
    if not file:
        return jsonify({"error": "No se recibió archivo"}), 400
    content = file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    conn = get_db()
    cur = conn.cursor()
    updated = 0
    inserted = 0
    for row in reader:
        chasis = (row.get("# Chasis") or "").strip()
        if not chasis:
            continue
        estado2       = (row.get("Estado2") or "").strip()
        ubicacion     = (row.get("Toma Fisica Inventarios - UBICACION") or "").strip()
        localizacion2 = (row.get("LOCALIZACION2") or "").strip()
        marca         = (row.get("Marca") or "").strip()
        modelo        = (row.get("Modelo") or "").strip()
        color         = (row.get("Color") or "").strip()
        cliente       = (row.get("Calc-Cliente") or "").strip()
        producto      = (row.get("Nombre del producto") or "").strip()
        ultima_toma   = (row.get("Toma Fisica Inventario - Fecha Ultima Toma") or "").strip()
        cur.execute("""
            INSERT INTO vehiculos
                (chasis, marca, modelo, color, cliente, estado2,
                 ubicacion, localizacion2, producto, ultima_toma)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (chasis) DO UPDATE SET
                estado2=%s, ubicacion=%s, localizacion2=%s,
                marca=%s, modelo=%s, color=%s, cliente=%s,
                producto=%s, ultima_toma=%s
        """, (chasis, marca, modelo, color, cliente, estado2,
              ubicacion, localizacion2, producto, ultima_toma,
              estado2, ubicacion, localizacion2,
              marca, modelo, color, cliente,
              producto, ultima_toma))
        if cur.rowcount == 1:
            inserted += 1
        else:
            updated += 1
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True, "insertados": inserted, "actualizados": updated})

@app.route("/api/vehiculos_taller")
def vehiculos_taller():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT v.chasis, v.marca, v.modelo, v.color, v.cliente,
               v.estado2, v.ubicacion, v.localizacion2, v.producto, v.ultima_toma,
               CASE WHEN v.ubicacion = 'TALLER PINTURA' THEN 'pintura'
                    ELSE 'mecanica' END AS taller,
               t.fecha_reporte, t.fecha_entrada, t.fecha_salida_est, t.problemas, t.origen_dano, t.notas
        FROM vehiculos v
        LEFT JOIN taller_data t ON v.chasis = t.chasis
        WHERE v.ubicacion IN ('TALLER MECANICA', 'TALLER PINTURA')
        ORDER BY v.ubicacion, v.estado2, v.chasis
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/buscar_vehiculo")
def buscar_vehiculo():
    q = request.args.get("q", "").strip()
    if len(q) < 3:
        return jsonify([])
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    like = f"%{q}%"
    cur.execute("""
        SELECT v.*, t.fecha_entrada, t.fecha_salida_est, t.problemas, t.notas
        FROM vehiculos v
        LEFT JOIN taller_data t ON v.chasis = t.chasis
        WHERE v.chasis ILIKE %s OR v.modelo ILIKE %s OR v.marca ILIKE %s
        LIMIT 20
    """, (like, like, like))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/guardar_taller", methods=["POST"])
def guardar_taller():
    data = request.json
    chasis = (data.get("chasis") or "").strip()
    if not chasis:
        return jsonify({"error": "Chasis requerido"}), 400
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO taller_data (chasis, fecha_reporte, fecha_entrada, fecha_salida_est, problemas, origen_dano, notas)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (chasis) DO UPDATE SET
                fecha_reporte=%s, fecha_entrada=%s, fecha_salida_est=%s, problemas=%s, origen_dano=%s, notas=%s
        """, (chasis, data.get("fecha_reporte"), data.get("fecha_entrada"), data.get("fecha_salida_est"),
              data.get("problemas"), data.get("origen_dano"), data.get("notas"),
              data.get("fecha_reporte"), data.get("fecha_entrada"), data.get("fecha_salida_est"),
  