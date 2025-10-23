from flask import Flask, request, jsonify, send_from_directory
import time, math, threading

app = Flask(__name__, static_folder="static")

# --- Etat applicatif (simulé pour l'instant) ---
state = {
    "mode": "manuel",       # "manuel" | "auto_tvc" | "demon"
    "setpoint_deg": 0.0,
    "angle_limit_deg": 15.0,
    "zero_offset_deg": 0.0,
    "origin_deg": 0.0,
    "gains": {"kp": 1.0, "ki": 0.0, "kd": 0.0},
    "u": 0.0,               # sortie contrôleur simulée
    "angle_deg": 0.0,       # télémétrie simulée
    "gyro_dps": 0.0,        # télémétrie simulée
    "sat": False
}

# --- Télémétrie simulée (remplacée plus tard par l'ESP32/UDP) ---
running = True
def sim_loop():
    t0 = time.time()
    while running:
        t = time.time() - t0
        if state["mode"] == "demon":
            # cercle simple: angle = A*sin(2πft)
            A = min(abs(state["angle_limit_deg"]), 20.0)
            f = 0.3
            state["setpoint_deg"] = A * math.sin(2*math.pi*f*t)
        # simulate a first-order response toward setpoint
        err = (state["setpoint_deg"] + state["zero_offset_deg"]) - state["angle_deg"]
        state["u"] = 0.8*err
        # saturations simulées
        lim = max(5.0, state["angle_limit_deg"])
        state["sat"] = abs(state["u"]) > lim
        state["u"] = max(-lim, min(lim, state["u"]))
        # dynamique lente
        state["angle_deg"] += 0.2 * state["u"] * 0.05
        state["gyro_dps"] = (state["u"] - 0.1*state["angle_deg"])
        time.sleep(0.05)  # 20 Hz

thr = threading.Thread(target=sim_loop, daemon=True)
thr.start()

# --- Static: page UI ---
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

# --- API ---
@app.get("/api/state")
def api_state():
    return jsonify(state)

@app.post("/api/mode")
def api_mode():
    m = request.json.get("mode")
    if m not in ("manuel","auto_tvc","demon"):
        return jsonify(error="mode invalide"), 400
    state["mode"] = m
    return jsonify(ok=True, mode=m)

@app.post("/api/setpoint")
def api_setpoint():
    sp = float(request.json.get("deg", 0.0))
    state["setpoint_deg"] = sp
    return jsonify(ok=True, setpoint_deg=sp)

@app.post("/api/angle_limit")
def api_angle_limit():
    lim = float(request.json.get("deg", 15.0))
    state["angle_limit_deg"] = max(1.0, min(60.0, lim))
    return jsonify(ok=True, angle_limit_deg=state["angle_limit_deg"])

@app.post("/api/set_zero")
def api_set_zero():
    state["zero_offset_deg"] = -state["angle_deg"]
    return jsonify(ok=True, zero_offset_deg=state["zero_offset_deg"])

@app.post("/api/set_origin")
def api_set_origin():
    state["origin_deg"] = state["angle_deg"]
    return jsonify(ok=True, origin_deg=state["origin_deg"])

@app.post("/api/gains")
def api_gains():
    g = request.json or {}
    for k in ("kp","ki","kd"):
        if k in g:
            state["gains"][k] = float(g[k])
    return jsonify(ok=True, gains=state["gains"])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
