from flask import Flask, request, jsonify, render_template
import psycopg2
import psycopg2.extras
import csv
import io
import os
import openpyxl
from datetime import datetime, date

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
            produto TEXT, ultima_toma TEXT
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
    for col in [
        ("fecha_reporte","TEXT"),("origen_dano","TEXT"),
        ("dano_logistica","TEXT"),("dano_taller","TEXT"),
        ("fecha_entrega_log","TEXT"),("fecha_recibido_taller","TEXT"),
        ("fecha_salida_real","TEXT"),
    ]:
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
    try:
        file = request.files.get("csv_file")
        if not file:
            return jsonify({"error": "No se recibio archivo"}), 400
        content = file.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        params = []
        for row in reader:
            chasis = (row.get("# Chasis") or "").strip()
            if not chasis:
                continue
            params.append((
                chasis,
                (row.get("Marca") or "").strip(),
                (row.get("Modelo") or "").strip(),
                (row.get("Color") or "").strip(),
                (row.get("Calc-Cliente") or "").strip(),
                (row.get("Estado2") or "").strip(),
                (row.get("Toma Fisica Inventarios - UBICACION") or "").strip(),
                (row.get("LOCALIZACION2") or "").strip(),
                (row.get("Nombre del produto") or row.get("Nombre del producto") or "").strip(),
                (row.get("Toma Fisica Inventario - Fecha Ultima Toma") or "").strip(),
            ))
        if not params:
            return jsonify({"ok": True, "insertados": 0, "actualizados": 0})
        conn = get_db()
        cur = conn.cursor()
        psycopg2.extras.execute_values(cur, """
            INSERT INTO vehiculos
                (chasis, marca, modelo, color, cliente, estado2,
                 ubicacion, localizacion2, produto, ultima_toma)
            VALUES %s
            ON CONFLICT (chasis) DO UPDATE SET
                marca=EXCLUDED.marca, modelo=EXCLUDED.modelo,
                color=EXCLUDED.color, cliente=EXCLUDED.cliente,
                estado2=EXCLUDED.estado2, ubicacion=EXCLUDED.ubicacion,
                localizacion2=EXCLUDED.localizacion2,
                produto=EXCLUDED.produto, ultima_toma=EXCLUDED.ultima_toma
        """, params, page_size=200)
        total = len(params)
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"ok": True, "insertados": total, "actualizados": 0})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/vehiculos_taller")
def vehiculos_taller():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT v.chasis, v.marca, v.modelo, v.color, v.cliente,
               v.estado2, v.ubicacion, v.localizacion2, v.produto, v.ultima_toma,
               CASE WHEN v.ubicacion = 'TALLER PINTURA' THEN 'pintura'
                    ELSE 'mecanica' END AS taller,
               t.fecha_reporte, t.fecha_entrada, t.fecha_salida_est,
               t.problemas, t.origen_dano, t.dano_logistica, t.dano_taller, t.notas,
               t.fecha_entrega_log, t.fecha_recibido_taller, t.fecha_salida_real
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
    try:
        data = request.json or {}
        chasis = (data.get("chasis") or "").strip()
        if not chasis:
            return jsonify({"ok": False, "error": "Chasis requerido"}), 400
        conn = get_db()
        cur = conn.cursor()
        fields = ["fecha_reporte","fecha_entrada","fecha_salida_est","origen_dano",
                  "dano_logistica","dano_taller","notas",
                  "fecha_entrega_log","fecha_recibido_taller","fecha_salida_real"]
        vals = [data.get(f) or None for f in fields]
        cur.execute(f"""
            INSERT INTO taller_data (chasis, {", ".join(fields)})
            VALUES (%s, {", ".join(["%s"]*len(fields))})
            ON CONFLICT (chasis) DO UPDATE SET
            {", ".join([f"{f}=%s" for f in fields])}
        """, [chasis] + vals + vals)
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/stamp", methods=["POST"])
def stamp():
    try:
        data = request.json or {}
        chasis = (data.get("chasis") or "").strip()
        campo = data.get("campo")
        if not chasis or campo not in ("fecha_entrega_log","fecha_recibido_taller"):
            return jsonify({"ok": False, "error": "Parametros invalidos"}), 400
        hoy = date.today().isoformat()
        conn = get_db()
        cur = conn.cursor()
        cur.execute(f"""
            INSERT INTO taller_data (chasis, {campo}) VALUES (%s,%s)
            ON CONFLICT (chasis) DO UPDATE SET {campo}=%s
        """, (chasis, hoy, hoy))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"ok": True, "fecha": hoy})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/marcar_entregado", methods=["POST"])
def marcar_entregado():
    try:
        data = request.json or {}
        chasis = (data.get("chasis") or "").strip()
        if not chasis:
            return jsonify({"ok": False, "error": "Chasis requerido"}), 400
        valor = data.get("fecha") or date.today().isoformat()
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO taller_data (chasis, fecha_salida_real) VALUES (%s,%s)
            ON CONFLICT (chasis) DO UPDATE SET fecha_salida_real=%s
        """, (chasis, valor, valor))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"ok": True, "fecha": valor})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/eliminar_taller/<chasis>", methods=["DELETE"])
def eliminar_taller(chasis):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM taller_data WHERE chasis=%s", (chasis,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/upload_excel", methods=["POST"])
def upload_excel():
    try:
        file = request.files.get("excel_file")
        if not file:
            return jsonify({"ok": False, "error": "No se recibio archivo"}), 400
        wb = openpyxl.load_workbook(io.BytesIO(file.read()))
        ws = wb.active
        def fmt_date(val):
            if not val: return None
            if isinstance(val, datetime): return val.strftime("%Y-%m-%d")
            s = str(val).strip()
            return None if not s or s in ('P.E','X','x','-','—') else s
        conn = get_db()
        cur = conn.cursor()
        actualizados = omitidos = 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            chasis = str(row[1]).strip() if row[1] else None
            if not chasis: continue
            cur.execute("SELECT 1 FROM vehiculos WHERE chasis=%s", (chasis,))
            if not cur.fetchone():
                omitidos += 1
                continue
            fr=fmt_date(row[0]); dl=str(row[2]).strip() if row[2] else None
            fe=fmt_date(row[3]); dt=str(row[4]).strip() if row[4] else None
            fs=fmt_date(row[5])
            cur.execute("""
                INSERT INTO taller_data (chasis,fecha_reporte,fecha_entrada,fecha_salida_est,dano_logistica,dano_taller)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (chasis) DO UPDATE SET
                    fecha_reporte=%s,fecha_entrada=%s,fecha_salida_est=%s,dano_logistica=%s,dano_taller=%s
            """, (chasis,fr,fe,fs,dl,dt, fr,fe,fs,dl,dt))
            actualizados += 1
        conn.commit(); cur.close(); conn.close()
        return jsonify({"ok": True, "actualizados": actualizados, "omitidos": omitidos})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/vehiculos_defectuosos")
def vehiculos_defectuosos():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT v.chasis, v.marca, v.modelo, v.color, v.cliente,
               v.estado2, v.ubicacion, v.localizacion2, v.produto, v.ultima_toma,
               t.fecha_reporte, t.fecha_entrada, t.fecha_salida_est,
               t.origen_dano, t.dano_logistica, t.dano_taller, t.notas
        FROM vehiculos v
        LEFT JOIN taller_data t ON v.chasis = t.chasis
        WHERE v.estado2 IN ('DEFECTUOSO','RECAMBIO')
          AND v.ubicacion NOT IN ('TALLER MECANICA','TALLER PINTURA')
        ORDER BY v.estado2, v.ubicacion, v.chasis
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/descargar_csv_defectuosos")
def descargar_csv_defectuosos():
    estado_filter = request.args.get("estado","all")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT v.chasis,v.marca,v.modelo,v.color,v.estado2,v.ubicacion,
               t.fecha_reporte,t.fecha_entrada,t.fecha_salida_est,
               t.dano_logistica,t.dano_taller,t.origen_dano,t.notas
        FROM vehiculos v LEFT JOIN taller_data t ON v.chasis=t.chasis
        WHERE v.estado2 IN ('DEFECTUOSO','RECAMBIO')
          AND v.ubicacion NOT IN ('TALLER MECANICA','TALLER PINTURA')
        ORDER BY v.estado2,v.ubicacion,v.chasis
    """)
    rows = cur.fetchall(); cur.close(); conn.close()
    if estado_filter != "all":
        rows = [r for r in rows if (r["estado2"] or "").upper()==estado_filter.upper()]
    def dias(e,s):
        if not e: return ""
        try:
            d1=date.fromisoformat(str(e)[:10])
            d2=date.fromisoformat(str(s)[:10]) if s and str(s)[:10]>"2000-01-01" else date.today()
            return f"{(d2-d1).days}d"
        except: return ""
    hdrs=["Chasis","Vehiculo","Ubicacion","Estado2","Fecha Reporte","Entrada","Salida Est.","Dias","Dano Logistica","Dano Taller","Origen Dano","Notas"]
    lines=[",".join(f'"{h}"' for h in hdrs)]
    for r in rows:
        veh=f"{r['marca'] or ''} {r['modelo'] or ''} {r['color'] or ''}".strip()
        row=[r["chasis"] or "",veh,r["ubicacion"] or "",r["estado2"] or "",
             r["fecha_reporte"] or "",r["fecha_entrada"] or "",r["fecha_salida_est"] or "",dias(r["fecha_entrada"],r["fecha_salida_est"]),
             r["dano_logistica"] or "",r["dano_taller"] or "",r["origen_dano"] or "",r["notas"] or ""]
        lines.append(",".join(f'"{str(c).replace(chr(34),chr(34)+chr(34))}"' for c in row))
    from flask import Response
    return Response("﻿"+"\n".join(lines),mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition":f"attachment; filename=defectuosos_{estado_filter}.csv"})

@app.route("/api/descargar_csv")
def descargar_csv():
    tf = request.args.get("taller","all")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT v.chasis,v.marca,v.modelo,v.color,v.estado2,v.ubicacion,
               CASE WHEN v.ubicacion='TALLER PINTURA' THEN 'pintura' ELSE 'mecanica' END AS taller,
               t.fecha_reporte,t.fecha_entrada,t.fecha_salida_est,
               t.dano_logistica,t.dano_taller,t.origen_dano,t.notas
        FROM vehiculos v LEFT JOIN taller_data t ON v.chasis=t.chasis
        WHERE v.ubicacion IN ('TALLER MECANICA','TALLER PINTURA')
        ORDER BY v.ubicacion,v.estado2,v.chasis
    """)
    rows = cur.fetchall(); cur.close(); conn.close()
    if tf != "all":
        rows = [r for r in rows if r["taller"]==tf]
    def dias(e,s):
        if not e: return ""
        try:
            d1=date.fromisoformat(str(e)[:10])
            d2=date.fromisoformat(str(s)[:10]) if s and str(s)[:10]>"2000-01-01" else date.today()
            return f"{(d2-d1).days}d"
        except: return ""
    hdrs=["Chasis","Vehiculo","Ubicacion","Estado","Fecha Reporte","Entrada Taller","Salida Estimada","Dias","Dano Logistica","Dano Taller","Origen Dano","Notas"]
    lines=[",".join(f'"{h}"' for h in hdrs)]
    for r in rows:
        veh=f"{r['marca'] or ''} {r['modelo'] or ''} {r['color'] or ''}".strip()
        row=[r["chasis"] or "",veh,r["ubicacion"] or "",r["estado2"] or "",
             r["fecha_reporte"] or "",r["fecha_entrada"] or "",r["fecha_salida_est"] or "",dias(r["fecha_entrada"],r["fecha_salida_est"]),
             r["dano_logistica"] or "",r["dano_taller"] or "",r["origen_dano"] or "",r["notas"] or ""]
        lines.append(",".join(f'"{str(c).replace(chr(34),chr(34)+chr(34))}"' for c in row))
    from flask import Response
    return Response("﻿"+"\n".join(lines),mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition":f"attachment; filename=control_talleres_{tf}.csv"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
# taller-tracker v4
