from flask import Flask, request, jsonify, send_from_directory

APP_VERSION = "0.3.0"

app = Flask(__name__, static_folder="static")

# --- État système (aucune simulation) ---
state = {
    "mode": "manuel",               # "manuel" | "auto_tvc" | "demo"
    "setpoint_deg": 0.0,
    "angle_limit_deg": 0.0,
    "zero_offset_deg": 0.0,
    "origin_deg": 0.0,
    "gains": {"kp": 0.0, "ki": 0.0, "kd": 0.0},
    "u": 0.0,
    "angle_deg": 0.0,
    "gyro_dps": 0.0,
    "sat": False
}

# --- Routes HTTP ---
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.get("/api/health")
def health():
    return jsonify(ok=True, version=APP_VERSION)

@app.get("/api/state")
def api_state():
    return jsonify(state)

@app.post("/api/mode")
def api_mode():
    m = (request.json or {}).get("mode")
    if m not in ("manuel", "auto_tvc", "demo"):
        return jsonify(error="mode invalide"), 400
    state["mode"] = m
    return jsonify(ok=True, mode=m)

@app.post("/api/setpoint")
def api_setpoint():
    sp = float((request.json or {}).get("deg", 0.0))
    state["setpoint_deg"] = sp
    return jsonify(ok=True, setpoint_deg=sp)

@app.post("/api/angle_limit")
def api_angle_limit():
    lim = float((request.json or {}).get("deg", 0.0))
    state["angle_limit_deg"] = max(0.0, min(60.0, lim))
    return jsonify(ok=True, angle_limit_deg=state["angle_limit_deg"])

@app.post("/api/set_zero")
def api_set_zero():
    state["zero_offset_deg"] = 0.0
    return jsonify(ok=True, zero_offset_deg=state["zero_offset_deg"])

@app.post("/api/set_origin")
def api_set_origin():
    state["origin_deg"] = 0.0
    return jsonify(ok=True, origin_deg=state["origin_deg"])

@app.post("/api/gains")
def api_gains():
    g = request.json or {}
    for k in ("kp", "ki", "kd"):
        if k in g:
            state["gains"][k] = float(g[k])
    return jsonify(ok=True, gains=state["gains"])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
