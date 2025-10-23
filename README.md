# TVC

## IMU (Inertial Measurement Unit)

L'API expose désormais l'état de l'IMU via le bloc `imu` renvoyé par `/api/state`.

### Lecture

```bash
curl -s http://localhost:8000/api/state | jq .imu
```

### Injection de test

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

Les valeurs apparaissent immédiatement dans l'interface web (section **IMU**), ainsi que dans la console de debug.