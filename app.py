import json
import threading
import time
from collections import deque

from flask import Flask, request, jsonify, send_from_directory

try:
    import serial
    from serial import SerialException
except ImportError:  # pragma: no cover - pyserial peut être absent en dev
    serial = None
    SerialException = Exception

APP_VERSION = "0.4.0"

app = Flask(__name__, static_folder="static")

AXES = ("x", "y")

UART_PORT = "/dev/ttyUSB0"
UART_BAUD = 115200
UART_TIMEOUT_S = 1.0
UART_RETRY_DELAY_S = 1.0
UART_LOG_MAX_LINES = 100


# --- État système (aucune simulation) ---
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
        "gyro_dps": {"x": 0.0, "y": 0.0, "z": 0.0},
        "accel_g": {"x": 0.0, "y": 0.0, "z": 0.0},
        "temp_c": 0.0,
        "t_ms": 0.0,
    }


state = {
    "mode": "manuel",  # "manuel" | "auto_tvc" | "demo"
    "angle_limit_deg": 0.0,
    "zero_offset_deg": 0.0,
    "origin_deg": 0.0,
    "gyro_dps": 0.0,
    "axes": {axis: _axis_state() for axis in AXES},
    "imu": _imu_state(),
}


state_lock = threading.Lock()
uart_log_lock = threading.Lock()
uart_lines = deque(maxlen=UART_LOG_MAX_LINES)


def _normalize_axis(payload):
    axis = (payload.get("axis") or "").lower()
    if axis == "":
        return None
    if axis not in AXES:
        raise ValueError("axis invalide")
    return axis


def _axes_target(axis):
    if axis is None:
        return AXES
    return (axis,)

# --- Routes HTTP ---
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.get("/api/health")
def health():
    return jsonify(ok=True, version=APP_VERSION, msg="Serveur opérationnel")

@app.get("/api/state")
def api_state():
    with state_lock:
        return jsonify(state)

@app.post("/api/mode")
def api_mode():
    m = (request.json or {}).get("mode")
    if m not in ("manuel", "auto_tvc", "demo"):
        return jsonify(ok=False, error="mode invalide", msg="Mode invalide"), 400
    with state_lock:
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

    with state_lock:
        for ax in targets:
            state["axes"][ax]["setpoint_deg"] = sp

        axes_msg = ",".join(ax.upper() for ax in targets)
        updated = {ax: state["axes"][ax]["setpoint_deg"] for ax in AXES}
        primary_axis = targets[0]
        selected = state["axes"][primary_axis]["setpoint_deg"]
    return jsonify(
        ok=True,
        axis=axes_msg,
        setpoint_deg=selected,
        axes_setpoint_deg=updated,
        msg=f"Setpoint ({axes_msg}) = {sp:.2f}°",
    )

@app.post("/api/angle_limit")
def api_angle_limit():
    try:
        lim = float((request.json or {}).get("deg", 0.0))
    except Exception:
        return jsonify(ok=False, error="valeur invalide", msg="Angle limit invalide"), 400
    # garde-fou: 0..60°
    with state_lock:
        state["angle_limit_deg"] = max(0.0, min(60.0, lim))
    return jsonify(
        ok=True,
        angle_limit_deg=state["angle_limit_deg"],
        msg=f"(GLOBAL) Angle limit = {state['angle_limit_deg']:.2f}°"
    )

@app.post("/api/set_zero")
def api_set_zero():
    with state_lock:
        state["zero_offset_deg"] = 0.0
    return jsonify(ok=True, zero_offset_deg=0.0, msg="(X,Y) Zero appliqué (offset=0)")

@app.post("/api/set_origin")
def api_set_origin():
    with state_lock:
        state["origin_deg"] = 0.0
    return jsonify(ok=True, origin_deg=0.0, msg="(X,Y) Origine réinitialisée")

@app.post("/api/gains")
def api_gains():
    payload = request.json or {}
    try:
        axis = _normalize_axis(payload)
        gains_payload = {}
        for k in ("kp", "ki", "kd"):
            if k in payload:
                gains_payload[k] = float(payload[k])
    except ValueError:
        return jsonify(ok=False, error="axis invalide", msg="Axe invalide"), 400
    except Exception:
        return jsonify(ok=False, error="valeur invalide", msg="Gains invalides"), 400

    if not gains_payload:
        return jsonify(ok=False, error="valeur manquante", msg="Aucun gain fourni"), 400

    targets = _axes_target(axis)

    with state_lock:
        for ax in targets:
            state["axes"][ax]["gains"].update(gains_payload)

        axes_msg = ",".join(ax.upper() for ax in targets)
        updated = {ax: dict(state["axes"][ax]["gains"]) for ax in AXES}
        ref_axis = targets[0]
        gains_ref = dict(state["axes"][ref_axis]["gains"])
    return jsonify(
        ok=True,
        axis=axes_msg,
        gains=gains_ref,
        axes_gains=updated,
        msg=(
            f"Gains ({axes_msg}) Kp={gains_ref['kp']}, "
            f"Ki={gains_ref['ki']}, "
            f"Kd={gains_ref['kd']}"
        ),
    )


def _coerce_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError("valeur numérique requise")


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_vector(payload, *keys):
    for key in keys:
        raw = payload.get(key)
        if isinstance(raw, dict):
            vector = {}
            complete = True
            for axis in ("x", "y", "z"):
                if axis not in raw:
                    complete = False
                    break
                val = _safe_float(raw.get(axis))
                if val is None:
                    complete = False
                    break
                vector[axis] = val
            if complete:
                return vector
    return None


def _extract_scalar(payload, *keys):
    for key in keys:
        if key in payload:
            val = _safe_float(payload.get(key))
            if val is not None:
                return val
    return None


def _apply_imu_payload(payload):
    accel_vec = _extract_vector(payload, "accel", "accel_g")
    gyro_vec = _extract_vector(payload, "gyro", "gyro_dps")
    temp_val = _extract_scalar(payload, "temp", "temp_c")
    t_ms = _extract_scalar(payload, "t_ms")

    if accel_vec is None and gyro_vec is None:
        return False

    with state_lock:
        imu = state.setdefault("imu", _imu_state())
        if accel_vec is not None:
            imu["accel_g"].update(accel_vec)
        if gyro_vec is not None:
            imu["gyro_dps"].update(gyro_vec)
        if temp_val is not None:
            imu["temp_c"] = temp_val
        if t_ms is not None:
            imu["t_ms"] = t_ms

    return True


def uart_reader():
    if serial is None:
        app.logger.warning("pyserial manquant: lecture IMU désactivée")
        return

    while True:
        try:
            with serial.Serial(
                UART_PORT,
                UART_BAUD,
                timeout=UART_TIMEOUT_S,
            ) as ser:
                app.logger.info(
                    "IMU UART connecté sur %s @%d bauds", UART_PORT, UART_BAUD
                )
                invalid_logged = False
                while True:
                    try:
                        raw = ser.readline()
                    except SerialException as exc:
                        app.logger.warning("Erreur lecture UART IMU: %s", exc)
                        break

                    if not raw:
                        continue

                    line = raw.decode("utf-8", errors="ignore").strip()
                    if not line:
                        continue
                    with uart_log_lock:
                        uart_lines.append(line)
                    if not (line.startswith("{") and line.endswith("}")):
                        if not invalid_logged:
                            app.logger.warning("IMU UART rejet: %s", line)
                            invalid_logged = True
                        continue

                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        if not invalid_logged:
                            app.logger.warning("IMU UART JSON invalide: %s", line)
                            invalid_logged = True
                        continue

                    if not isinstance(payload, dict):
                        continue

                    if "status" in payload and len(payload) == 1:
                        continue

                    if _apply_imu_payload(payload):
                        invalid_logged = False
                    elif not invalid_logged:
                        app.logger.warning("IMU UART données ignorées: %s", line)
                        invalid_logged = True

        except (SerialException, OSError) as exc:
            app.logger.warning(
                "Impossible d'ouvrir %s (%s), nouvel essai dans %.1fs",
                UART_PORT,
                exc,
                UART_RETRY_DELAY_S,
            )

        time.sleep(UART_RETRY_DELAY_S)


@app.post("/api/imu/update")
def api_imu_update():
    payload = request.json or {}
    with state_lock:
        imu = state.setdefault("imu", _imu_state())

        try:
            angle_payload = payload.get("angle_deg")
            if angle_payload is not None:
                if not isinstance(angle_payload, dict):
                    raise ValueError("angle_deg invalide")
                for axis in ("x", "y"):
                    if axis in angle_payload:
                        imu["angle_deg"][axis] = _coerce_float(angle_payload[axis])

            gyro_payload = payload.get("gyro_dps")
            if gyro_payload is not None:
                if not isinstance(gyro_payload, dict):
                    raise ValueError("gyro_dps invalide")
                for axis in ("x", "y", "z"):
                    if axis in gyro_payload:
                        imu["gyro_dps"][axis] = _coerce_float(gyro_payload[axis])

            accel_payload = payload.get("accel_g")
            if accel_payload is not None:
                if not isinstance(accel_payload, dict):
                    raise ValueError("accel_g invalide")
                for axis in ("x", "y", "z"):
                    if axis in accel_payload:
                        imu["accel_g"][axis] = _coerce_float(accel_payload[axis])

            if "temp_c" in payload:
                imu["temp_c"] = _coerce_float(payload["temp_c"])
            if "t_ms" in payload:
                imu["t_ms"] = _coerce_float(payload["t_ms"])
        except ValueError as exc:
            return (
                jsonify(ok=False, error="imu invalide", msg=str(exc)),
                400,
            )

    return jsonify(ok=True, imu=imu, msg="IMU mise à jour")


@app.get("/api/debug/uart")
def api_debug_uart():
    with uart_log_lock:
        lines = list(uart_lines)
    return jsonify(ok=True, lines=lines, count=len(lines))

if __name__ == "__main__":
    uart_thread = threading.Thread(target=uart_reader, name="imu-uart", daemon=True)
    uart_thread.start()

    # Accès réseau local ; port 8000 par convention
    app.run(host="0.0.0.0", port=8000)