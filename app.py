from flask import Flask, request, jsonify, send_from_directory
import threading, json, time

# pyserial pour le port série
try:
    import serial
except ImportError:
    raise SystemExit("pyserial manquant. Installe :  pip install pyserial")

APP_VERSION = "0.5.0"
app = Flask(__name__, static_folder="static")

AXES = ("x", "y")

# === CONFIG UART ===
UART_PORT = "/dev/ttyUSB0"   # USB de l'ESP branché sur la Pi
UART_BAUD = 115200

# --- État système ---
def _axis_state():
    return {
        "setpoint_deg": 0.0,
        "angle_deg": 0.0,
        "u": 0.0,
        "sat": False,
        "gains": {"kp": 0.0, "ki": 0.0, "kd": 0.0},
    }

def _imu_state():
    return {
        "angle_deg": {"x": 0.0, "y": 0.0},
        "gyro_dps":  {"x": 0.0, "y": 0.0, "z": 0.0},
        "accel_g":   {"x": 0.0, "y": 0.0, "z": 0.0},
        "temp_c": 0.0,
        "t_ms": 0
    }

state = {
    "mode": "manuel",
    "angle_limit_deg": 0.0,
    "zero_offset_deg": 0.0,
    "origin_deg": 0.0,
    "axes": {axis: _axis_state() for axis in AXES},
    "imu": _imu_state(),
}

lock = threading.Lock()

# === Thread UART : lit NDJSON ligne par ligne, met à jour state["imu"] ===
def uart_reader():
    while True:
        try:
            with serial.Serial(UART_PORT, UART_BAUD, timeout=1) as ser:
                while True:
                    line = ser.readline()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line.decode("utf-8", errors="ignore").strip())
                    except json.JSONDecodeError:
                        continue

                    # ESP32 envoie : {"t_ms":..,"accel":{"x":..},"gyro":{"x":..},"temp":..}
                    accel = obj.get("accel") or {}
                    gyro  = obj.get("gyro")  or {}
                    temp  = obj.get("temp", None)
                    t_ms  = obj.get("t_ms", 0)

                    with lock:
                        imu = state["imu"]
                        # map vers notre structure
                        for k in ("x","y","z"):
                            if k in accel: imu["accel_g"][k] = float(accel[k])
                            if k in gyro:  imu["gyro_dps"][k] = float(gyro[k])
                        if temp is not None:
                            imu["temp_c"] = float(temp)
                        if isinstance(t_ms, (int, float)):
                            imu["t_ms"] = int(t_ms)
        except Exception as e:
            # Port indispo / débranché : on retente
            time.sleep(1)

# --- Utilitaires JSON ---
def _coerce_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError("valeur numérique requise")

def _normalize_axis(payload):
    axis = (payload.get("axis") or "").lower()
    if axis == "": return None
    if axis not in AXES: raise ValueError("axis invalide")
    return axis

def _axes_target(axis):
    return AXES if axis is None else (axis,)

# --- Routes HTTP ---
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.get("/api/health")
def health():
    return jsonify(ok=True, version=APP_VERSION, msg="Serveur opérationnel")

@app.get("/api/state")
def api_state():
    with lock:
        snap = json.loads(json.dumps(state))
    return jsonify(snap)

@app.post("/api/mode")
def api_mode():
    m = (request.json or {}).get("mode")
    if m not in ("manuel", "auto_tvc", "demo"):
        return jsonify(ok=False, error="mode invalide", msg="Mode invalide"), 400
    with lock:
        state["mode"] = m
    return jsonify(ok=True, mode=m, msg=f"Mode → {m}")

@app.post("/api/setpoint")
def api_setpoint():
    payload = request.json or {}
    try:
        sp = float(payload.get("deg", 0.0))
        axis = _normalize_axis(payload)
    except ValueError:
        return jsonify(ok=False, error="axis invalide", msg="Axe invalide"), 400
    except Exception:
        return jsonify(ok=False, error="valeur invalide", msg="Setpoint invalide"), 400

    targets = _axes_target(axis)
    with lock:
        for ax in targets:
            state["axes"][ax]["setpoint_deg"] = sp
        updated = {ax: state["axes"][ax]["setpoint_deg"] for ax in AXES}

    axes_msg = ",".join(ax.upper() for ax in targets)
    primary_axis = targets[0]
    return jsonify(
        ok=True,
        axis=axes_msg,
        setpoint_deg=state["axes"][primary_axis]["setpoint_deg"],
        axes_setpoint_deg=updated,
        msg=f"Setpoint ({axes_msg}) = {sp:.2f}°",
    )

@app.post("/api/angle_limit")
def api_angle_limit():
    try:
        lim = float((request.json or {}).get("deg", 0.0))
    except Exception:
        return jsonify(ok=False, error="valeur invalide", msg="Angle limit invalide"), 400
    lim = max(0.0, min(60.0, lim))
    with lock:
        state["angle_limit_deg"] = lim
    return jsonify(ok=True, angle_limit_deg=lim, msg=f"(GLOBAL) Angle limit = {lim:.2f}°")

@app.post("/api/set_zero")
def api_set_zero():
    with lock:
        state["zero_offset_deg"] = 0.0
    return jsonify(ok=True, zero_offset_deg=0.0, msg="(X,Y) Zero appliqué (offset=0)")

@app.post("/api/set_origin")
def api_set_origin():
    with lock:
        state["origin_deg"] = 0.0
    return jsonify(ok=True, origin_deg=0.0, msg="(X,Y) Origine réinitialisée")

@app.post("/api/gains")
def api_gains():
    payload = request.json or {}
    try:
        axis = _normalize_axis(payload)
        gains_payload = {k: float(payload[k]) for k in ("kp","ki","kd") if k in payload}
    except ValueError:
        return jsonify(ok=False, error="axis invalide", msg="Axe invalide"), 400
    except Exception:
        return jsonify(ok=False, error="valeur invalide", msg="Gains invalides"), 400

    if not gains_payload:
        return jsonify(ok=False, error="valeur manquante", msg="Aucun gain fourni"), 400

    targets = _axes_target(axis)
    with lock:
        for ax in targets:
            state["axes"][ax]["gains"].update(gains_payload)
        updated = {ax: state["axes"][ax]["gains"] for ax in AXES}

    axes_msg = ",".join(ax.upper() for ax in targets)
    ref_axis = targets[0]
    gains_ref = updated[ref_axis]
    return jsonify(
        ok=True,
        axis=axes_msg,
        gains=gains_ref,
        axes_gains=updated,
        msg=f"Gains ({axes_msg}) Kp={gains_ref['kp']}, Ki={gains_ref['ki']}, Kd={gains_ref['kd']}",
    )

@app.post("/api/imu/update")
def api_imu_update():
    payload = request.json or {}
    try:
        with lock:
            imu = state["imu"]
            if "angle_deg" in payload:
                for k in ("x","y"):
                    if k in payload["angle_deg"]:
                        imu["angle_deg"][k] = _coerce_float(payload["angle_deg"][k])
            if "gyro_dps" in payload:
                for k in ("x","y","z"):
                    if k in payload["gyro_dps"]:
                        imu["gyro_dps"][k] = _coerce_float(payload["gyro_dps"][k])
            if "accel_g" in payload:
                for k in ("x","y","z"):
                    if k in payload["accel_g"]:
                        imu["accel_g"][k] = _coerce_float(payload["accel_g"][k])
            if "temp_c" in payload:
                imu["temp_c"] = _coerce_float(payload["temp_c"])
    except ValueError as exc:
        return jsonify(ok=False, error="imu invalide", msg=str(exc)), 400

    return jsonify(ok=True, imu=state["imu"], msg="IMU mise à jour")

if __name__ == "__main__":
    threading.Thread(target=uart_reader, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)
