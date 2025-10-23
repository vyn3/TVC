# TVC

Interface Flask minimale pour piloter un système de Thrust Vector Control.

## API

### `/api/state`

Retourne l'état complet du système, incluant les axes X/Y et le bloc IMU:

```json
{
  "mode": "manuel",
  "angle_limit_deg": 0.0,
  "zero_offset_deg": 0.0,
  "origin_deg": 0.0,
  "gyro_dps": 0.0,
  "axes": {
    "x": {
      "setpoint_deg": 0.0,
      "angle_deg": 0.0,
      "u": 0.0,
      "sat": false,
      "gains": {"kp": 0.0, "ki": 0.0, "kd": 0.0}
    },
    "y": {
      "setpoint_deg": 0.0,
      "angle_deg": 0.0,
      "u": 0.0,
      "sat": false,
      "gains": {"kp": 0.0, "ki": 0.0, "kd": 0.0}
    }
  },
  "imu": {
    "angle_deg": {"x": 0.0, "y": 0.0},
    "gyro_dps": {"x": 0.0, "y": 0.0, "z": 0.0},
    "accel_g": {"x": 0.0, "y": 0.0, "z": 0.0},
    "temp_c": 0.0
  }
}
```

Le bloc `imu` est alimenté par le microcontrôleur (ESP32) et ne contient aucune
simulation côté serveur.

### `/api/imu/update`

Point d'injection temporaire pour mettre à jour les mesures IMU depuis un
script externe (ex: Raspberry Pi) tant que le firmware n'est pas connecté.
Tous les champs sont optionnels; les valeurs sont clampées à des plages
raisonnables et doivent être numériques.

```bash
curl -s -X POST http://localhost:8000/api/imu/update \
  -H 'Content-Type: application/json' \
  -d '{
        "angle_deg": {"x": 5.5, "y": -3.2},
        "gyro_dps": {"x": 0.1, "y": 0.2, "z": 0.0},
        "accel_g": {"x": 0.0, "y": 0.0, "z": 1.0},
        "temp_c": 32.5
      }'
```

La réponse attendue est `{"ok": true, "msg": "IMU mise à jour"}` et les
nouvelles valeurs apparaissent immédiatement dans `/api/state` et sur l'UI.

> **Note :** aucune valeur n'est animée côté backend. Les mesures IMU ne
> changent que lorsqu'elles sont envoyées par le matériel.
