from flask import Flask, request, jsonify, send_from_directory
import time, math, threading

APP_VERSION = "0.2.0"

app = Flask(__name__, static_folder="static")

# --- Etat applicatif (simulation pour démarrer ; remplacée plus tard par l'ESP32) ---
state = {
    "mode": "manuel",               # "manuel" | "auto_tvc" | "demon"
    "setpoint_deg": 0.0,
    "angle_limit_deg": 15.0,
    "zero_offset_deg": 0.0,
    "origin_deg": 0.0,
    "gains": {"kp": 1.0, "ki": 0.0, "kd": 0.0},
    "u": 0.0,                       # sortie contrôleur (simulée)
    "angle_deg": 0.0,               # télémétrie (simulée)
    "gyro_dps": 0.0,                # télémétrie (simulée)
    "sat": False
}

_running = True
def _sim_loop():
    t0 = time.time()
    dt = 0.05  # 20 Hz côté UI (la vraie boucle contrôle sera sur ESP32)
    while _running:
        t = time.time() - t0
        if state["mode"] == "demon":
            A = max(1.0, min(abs(state["angle_limit_deg"]), 20.0))
            f = 0.3
            state["setpoint_deg"] = A * math.sin(2*math.pi*f*t)

        # modèle jouet: 1er ordre vers consigne (avec offset zero)
        err = (state["setpoint_deg"] + state["zero_offset_deg"]) - state["angle_deg"]
        u_raw = state["gains"]["kp"]*err  # on garde simple pour l'UI
        lim = max(5.0, float(state["angle_limit_deg"]))
        state["sat"] = abs(u_raw) > lim
        state["u"] = max(-lim, min(lim, u_raw))

        # dynamique lente pour visualisation
        state["angle_deg"] += 0.25 * state["u"] * dt
        state["gyro_dps"] = (state["u"] - 0.1*state["angle_deg"])

        time.sleep(dt)

_thr = threading.Thread(target=_sim_loop, daemon=True)
_thr.start()

# --- Routes HTTP ---
@app.get("/")
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
    if m not in ("manuel","auto_tvc","demon"):
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
    lim = float((request.json or {}).get("deg", 15.0))
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
    # Host 0.0.0.0 pour accès réseau ; port 8000 par convention locale
    app.run(host="0.0.0.0", port=8000)
