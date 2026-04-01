# Systemd Service Installation - Block 5.1

## Voraussetzungen

- Linux mit systemd (Version 250+)
- Node.js v22+ installiert unter `/usr/local/bin/node`
- User `node` existiert (uid=1000)
- OpenClaw Workspace unter `/data/.openclaw/workspace/`

---

## A) Installationsschritte

### 1. Service-Datei installieren

```bash
# Als root ausführen:
sudo cp /data/.openclaw/workspace/forward_v5/forward_v5/systemd/forward_v5.service \
        /etc/systemd/system/

# Berechtigungen setzen
sudo chmod 644 /etc/systemd/system/forward_v5.service

# systemd neu laden
sudo systemctl daemon-reload
```

### 2. Verzeichnis-Berechtigungen prüfen

```bash
# Als root:
sudo chown -R node:node /data/.openclaw/workspace/forward_v5/
sudo chmod 755 /data/.openclaw/workspace/
sudo chmod 755 /data/.openclaw/
sudo chmod 755 /data/
```

### 3. Optional: Environment-File erstellen

```bash
# Verzeichnis erstellen
sudo mkdir -p /etc/openclaw
sudo chown root:root /etc/openclaw
sudo chmod 755 /etc/openclaw

# Env-File kopieren (optional)
sudo cp /data/.openclaw/workspace/forward_v5/forward_v5/systemd/config/forward_v5.env.example \
        /etc/openclaw/forward_v5.env

# Berechtigungen (nur root lesbar bei Secrets)
sudo chmod 644 /etc/openclaw/forward_v5.env
```

### 4. Service-Unit patchen (falls Env-File genutzt)

```bash
# Entkommentiere die EnvironmentFile-Zeile:
sudo sed -i 's/^#EnvironmentFile=/EnvironmentFile=/' \
    /etc/systemd/system/forward_v5.service

sudo systemctl daemon-reload
```

### 5. Service enablen (autostart)

```bash
sudo systemctl enable forward_v5.service
```

---

## B) Testplan für start/stop/restart

### Test 1: Dry-Run (Syntax-Check)

```bash
# Prüfe Service-Datei auf Syntax-Fehler
sudo systemd-analyze verify /etc/systemd/system/forward_v5.service
# Erwartet: Keine Ausgabe = OK
```

### Test 2: Service starten

```bash
sudo systemctl start forward_v5.service

# Status prüfen
sudo systemctl status forward_v5.service
# Erwartet: active (running)

# Logs prüfen
sudo journalctl -u forward_v5 -n 50 --no-pager
# Erwartet: "Services started successfully"
```

### Test 3: Prozess-Verifikation

```bash
# PID prüfen
pgrep -f "runtime_validation/runner.js"

# User-Verifikation
ps aux | grep runner.js | grep node
# Erwartet: User = node (nicht root!)

# Environment prüfen
cat /proc/$(pgrep -f runner.js)/environ | tr '\0' '\n' | grep EVENT_STORE
# Erwartet: EVENT_STORE_PATH=./runtime/event_store.db
```

### Test 4: Service stoppen

```bash
sudo systemctl stop forward_v5.service

# Verifikation
sudo systemctl status forward_v5.service
# Erwartet: inactive (dead)

ps aux | grep runner.js | grep -v grep
# Erwartet: Keine Ausgabe (kein Prozess)
```

### Test 5: Restart-Policy testen

```bash
# Service starten
sudo systemctl start forward_v5.service

# PID merken
OLD_PID=$(pgrep -f runner.js)
echo "Old PID: $OLD_PID"

# Prozess hart killen (simuliert crash)
sudo kill -9 $OLD_PID

# Warten auf Restart (10s)
sleep 12

# Neue PID prüfen
NEW_PID=$(pgrep -f runner.js)
echo "New PID: $NEW_PID"

# Verifikation
if [ "$OLD_PID" != "$NEW_PID" ] && [ -n "$NEW_PID" ]; then
    echo "✅ Restart-Policy funktioniert"
else
    echo "❌ Restart-Policy FAILED"
fi

# Status
sudo systemctl status forward_v5.service
```

### Test 6: Graceful Shutdown

```bash
# Service starten
sudo systemctl start forward_v5.service

# Stop mit SIGTERM (graceful)
sudo systemctl stop forward_v5.service

# Logs auf graceful shutdown prüfen
sudo journalctl -u forward_v5 -n 20 --no-pager
# Erwartet: "Shutting down gracefully..."

# State-File prüfen (wenn vorhanden)
cat /data/.openclaw/workspace/forward_v5/forward_v5/runtime_validation/state.json | grep status
```

### Test 7: Journal-Logging

```bashn# Logs in Echtzeit beobachten
sudo journalctl -u forward_v5 -f

# In anderem Terminal:
sudo systemctl restart forward_v5

# Prüfung: Logs erscheinen in journald
# Strg+C zum Beenden
```

---

## C) Troubleshooting

### Service startet nicht

```bashn# Detaillierte Fehlermeldung
sudo systemctl status forward_v5.service --full

# Logs seit Boot
sudo journalctl -u forward_v5 --since today --no-pager
```

### Permission Denied

```bash
# Verzeichnis-Berechtigungen prüfen
ls -la /data/.openclaw/workspace/forward_v5/forward_v5/

# Fix:
sudo chown -R node:node /data/.openclaw/workspace/forward_v5/
```

### Environment-Variablen nicht gesetzt

```bash
# Aktuelle Env des Prozesses prüfen
sudo cat /proc/$(pgrep -f runner.js)/environ | tr '\0' '\n'
```

### Hardening-Flags blockieren

```bash
# Temporarily hardening deaktivieren (Debugging)
sudo systemctl edit forward_v5
# Einfügen:
# [Service]
# ProtectSystem=false
# ProtectHome=false
```

---

## D) Acceptance Criteria

- [ ] Service-Datei installiert unter `/etc/systemd/system/`
- [ ] Syntax-Check erfolgreich (`systemd-analyze verify`)
- [ ] Service startet (`systemctl start` → active)
- [ ] Läuft unter User `node` (nicht root)
- [ ] Environment-Variablen gesetzt (`EVENT_STORE_PATH`)
- [ ] Restart-Policy funktioniert (kill -9 → restart)
- [ ] Graceful Shutdown funktioniert (SIGTERM)
- [ ] Logs in journald sichtbar (`journalctl -u forward_v5`)
- [ ] Service enabled (`systemctl enable`)
- [ ] Service deaktivieren funktioniert (`systemctl disable`)

---

## E) Rollback

```bash
# Service stoppen und disablen
sudo systemctl stop forward_v5.service
sudo systemctl disable forward_v5.service

# Service-Datei entfernen
sudo rm /etc/systemd/system/forward_v5.service
sudo rm -f /etc/systemd/system/forward_v5.service.d/*  # Overrides

# Optional: Env-File entfernen
sudo rm -f /etc/openclaw/forward_v5.env

# systemd neu laden
sudo systemctl daemon-reload
```
