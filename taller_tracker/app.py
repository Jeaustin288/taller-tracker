from flask import Flask, request, jsonify, render_template
import psycopg2
import psycopg2.extras
import csv
import io
import os

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

def get_db():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS vehiculos (
            chasis        TEXT PRIMARY KEY,
            marca         TEXT,
            modelo        TEXT,
            color         TEXT,
            cliente       TEXT,
            estado2       TEXT,
            ubicacion     TEXT,
            localizacion2 TEXT,
            producto      TEXT,
            ultima_toma   TEXT
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS taller_data (
            chasis           TEXT PRIMARY KEY,
            taller           TEXT DEFAULT 'mecanica',
            fecha_entrada    TEXT,
            fecha_salida_est TEXT,
            problemas        TEXT,
            notas            TEXT,
            FOREIGN KEY (chasis) REFERENCES vehiculos(chasis)
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

init_db()

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

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
               t.taller, t.fecha_entrada, t.fecha_salida_est, t.problemas, t.notas
        FROM vehiculos v
        INNER JOIN taller_data t ON v.chasis = t.chasis
        ORDER BY t.fecha_entrada DESC NULLS LAST
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
        SELECT v.*, t.taller, t.fecha_entrada, t.fecha_salida_est, t.problemas, t.notas
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
    cur.execute("""
        INSERT INTO taller_data (chasis, taller, fecha_entrada, fecha_salida_est, problemas, notas)
        VALUES (%s,%s,%s,%s,%s,%s)
        ON CONFLICT (chasis) DO UPDATE SET
            taller=%s, fecha_entrada=%s, fecha_salida_est=%s,
            problemas=%s, notas=%s
    """, (chasis, data.get("taller"), data.get("fecha_entrada"),
          data.get("fecha_salida_est"), data.get("problemas"), data.get("notas"),
          data.get("taller"), data.get("fecha_entrada"),
          data.get("fecha_salida_est"), data.get("problemas"), data.get("notas")))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/eliminar_taller/<chasis>", methods=["DELETE"])
def eliminar_taller(chasis):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM taller_data WHERE chasis=%s", (chasis,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
