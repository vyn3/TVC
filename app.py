from flask import Flask, request, jsonify, send_from_directory

APP_VERSION = "0.4.0"

app = Flask(__name__, static_folder="static")

AXES = ("x", "y")


# --- État système (aucune simulation) ---
def _axis_state():
    return {
        "setpoint_deg": 0.0,
        "angle_deg": 0.0,
        "u": 0.0,
        "sat": False,
        "gains": {"kp": 0.0, "ki": 0.0, "kd": 0.0},
    }


state = {
    "mode": "manuel",  # "manuel" | "auto_tvc" | "demo"
    "angle_limit_deg": 0.0,
    "zero_offset_deg": 0.0,
    "origin_deg": 0.0,
    "gyro_dps": 0.0,
    "axes": {axis: _axis_state() for axis in AXES},
}


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
    return jsonify(state)

@app.post("/api/mode")
def api_mode():
    m = (request.json or {}).get("mode")
    if m not in ("manuel", "auto_tvc", "demo"):
        return jsonify(ok=False, error="mode invalide", msg="Mode invalide"), 400
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

    for ax in targets:
        state["axes"][ax]["setpoint_deg"] = sp

    axes_msg = ",".join(ax.upper() for ax in targets)
    updated = {ax: state["axes"][ax]["setpoint_deg"] for ax in AXES}
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
    # garde-fou: 0..60°
    state["angle_limit_deg"] = max(0.0, min(60.0, lim))
    return jsonify(
        ok=True,
        angle_limit_deg=state["angle_limit_deg"],
        msg=f"(GLOBAL) Angle limit = {state['angle_limit_deg']:.2f}°"
    )

@app.post("/api/set_zero")
def api_set_zero():
    state["zero_offset_deg"] = 0.0
    return jsonify(ok=True, zero_offset_deg=0.0, msg="(X,Y) Zero appliqué (offset=0)")

@app.post("/api/set_origin")
def api_set_origin():
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

    for ax in targets:
        state["axes"][ax]["gains"].update(gains_payload)

    axes_msg = ",".join(ax.upper() for ax in targets)
    updated = {ax: state["axes"][ax]["gains"] for ax in AXES}
    ref_axis = targets[0]
    gains_ref = state["axes"][ref_axis]["gains"]
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

if __name__ == "__main__":
    # Accès réseau local ; port 8000 par convention
    app.run(host="0.0.0.0", port=8000)
