# Systemd Service Testplan - Block 5.1

**Phase:** Phase 5.1 - Systemd Integration  
**Version:** v1.0  
**Datum:** 2026-04-01  
**Tester:** DevOps / OpenClaw Admin  

---

## Testübersicht

| Test ID | Beschreibung | Kritikalität | Erwartetes Ergebnis |
|---------|--------------|--------------|---------------------|
| T-5.1.1 | Syntax-Check Service-Datei | 🔴 Blocker | Keine Fehler |
| T-5.1.2 | Service starten | 🔴 Blocker | Status: active (running) |
| T-5.1.3 | User/Group Verifikation | 🔴 Blocker | User = node, nicht root |
| T-5.1.4 | Environment-Variablen | 🔴 Blocker | EVENT_STORE_PATH gesetzt |
| T-5.1.5 | WorkingDirectory | 🟡 Medium | /data/.openclaw/workspace/forward_v5/forward_v5 |
| T-5.1.6 | Restart-Policy on-failure | 🔴 Blocker | Automatischer Restart nach crash |
| T-5.1.7 | RestartSec | 🟡 Medium | 10 Sekunden Verzögerung |
| T-5.1.8 | Graceful Shutdown | 🟡 Medium | SIGTERM → sauberer Stop |
| T-5.1.9 | Journal-Logging | 🟡 Medium | Logs in journald sichtbar |
| T-5.1.10 | StandardOutput/Error | 🟢 Low | journal (nicht Datei) |
| T-5.1.11 | Service enable/disable | 🟡 Medium | Autostart funktioniert |
| T-5.1.12 | 24h Stabilität | 🔴 Blocker | Läuft 24h durch ohne Neustart |

---

## Testprozeduren

### T-5.1.1: Syntax-Check

```bash
Test:
  sudo systemd-analyze verify /etc/systemd/system/forward_v5.service

Erwartet:
  Keine Ausgabe (Exit-Code 0)

Bei Fehler:
  Fehlermeldung mit Zeilennummer → Service-Datei korrigieren
```

### T-5.1.2: Service Start

```bash
Vorbedingung:
  Service-Datei installiert und daemon-reload ausgeführt

Test:
  sudo systemctl start forward_v5.service
  sleep 2
  sudo systemctl status forward_v5.service --no-pager

Erwartet:
  ● forward_v5.service - OpenClaw Forward v5 Runtime Validation Service
       Loaded: loaded (/etc/systemd/system/forward_v5.service; enabled; preset: enabled)
       Active: active (running) since ...
     Main PID: XXXX (node)
```

### T-5.1.3: User/Group Verifikation

```bash
Vorbedingung:
  Service läuft (T-5.1.2 erfolgreich)

Test:
  ps aux | grep runtime_validation/runner.js | grep -v grep

Erwartet:
  node ... node runtime_validation/runner.js
          ^^^^
          User = node (kein root!)

Auch testen:
  grep "User=\|Group=" /etc/systemd/system/forward_v5.service
  Erwartet: User=node, Group=node
```

### T-5.1.4: Environment-Variablen

```bash
Vorbedingung:
  Service läuft

Test:
  PID=$(pgrep -f runtime_validation/runner.js)
  sudo cat /proc/$PID/environ | tr '\0' '\n' | grep EVENT_STORE

Erwartet:
  EVENT_STORE_PATH=./runtime/event_store.db

Auch testen:
  NODE_ENV=production
```

### T-5.1.5: WorkingDirectory

```bash
Vorbedingung:
  Service läuft

Test:
  PID=$(pgrep -f runtime_validation/runner.js)
  sudo ls -la /proc/$PID/cwd

Erwartet:
  /data/.openclaw/workspace/forward_v5/forward_v5

Auch verifizieren:
  grep "WorkingDirectory=" /etc/systemd/system/forward_v5.service
```

### T-5.1.6: Restart-Policy (on-failure)

```bash
Vorbedingung:
  Service läuft

Test:
  # PID merken
  OLD_PID=$(pgrep -f runtime_validation/runner.js)
  
  # Simuliere Crash
  sudo kill -9 $OLD_PID
  
  # Warte auf Restart (10s + margin)
  sleep 15
  
  # Neue PID prüfen
  NEW_PID=$(pgrep -f runtime_validation/runner.js)

Erwartet:
  $OLD_PID != $NEW_PID
  $NEW_PID ist nicht leer
  Service Status: active (running)
```

### T-5.1.7: RestartSec

```bash
Vorbedingung:
  Service läuft

Test:
  # Zeit messen zwischen Kill und Restart
  sudo kill -9 $(pgrep -f runtime_validation/runner.js)
  
  # Zeitstempel notieren
  date +%s > /tmp/kill_time
  
  # Warte bis neuer Prozess läuft
  while ! pgrep -f runtime_validation/runner.js > /dev/null; do
      sleep 1
  done
  date +%s > /tmp/restart_time
  
  # Differenz berechnen
  DURATION=$(( $(cat /tmp/restart_time) - $(cat /tmp/kill_time) ))

Erwartet:
  10 <= $DURATION <= 15 (Sekunden)
  
Verifiziert:
  grep "RestartSec=" /etc/systemd/system/forward_v5.service
  Erwartet: RestartSec=10
```

### T-5.1.8: Graceful Shutdown

```bash
Vorbedingung:
  Service läuft

Test:
  sudo systemctl stop forward_v5.service
  
  # Logs prüfen
  sudo journalctl -u forward_v5 -n 10 --no-pager

Erwartet:
  "Shutting down gracefully..."
  "Services stopped"
  Keine "Killed" oder "Failed" Messages

Status:
  sudo systemctl status forward_v5.service
  Erwartet: inactive (dead)
```

### T-5.1.9: Journal-Logging

```bash
Vorbedingung:
  Service läuft seit mind. 5 Minuten

Test:
  # Letzte Logs anzeigen
  sudo journalctl -u forward_v5 -n 50 --no-pager
  
  # Logs seit Service-Start
  sudo journalctl -u forward_v5 --since "10 minutes ago" --no-pager

Erwartet:
  Logs sind sichtbar mit Identifier "forward_v5"
  Zeitstempel sind korrekt
  Keine Fehlermeldungen
```

### T-5.1.10: StandardOutput/Error

```bash
Vorbedingung:
  Service läuft

Test:
  grep -E "StandardOutput|StandardError" /etc/systemd/system/forward_v5.service

Erwartet:
  StandardOutput=journal
  StandardError=journal

Verifizieren (keine Dateien in /var/log):
  ls -la /var/log/ | grep forward
  Erwartet: Keine forward_v5 spezifischen Dateien (geht über journald)
```

### T-5.1.11: Service Enable/Disable

```bash
Test Enable:
  sudo systemctl enable forward_v5.service
  systemctl is-enabled forward_v5.service
  Erwartet: enabled

Test Disable:
  sudo systemctl disable forward_v5.service
  systemctl is-enabled forward_v5.service
  Erwartet: disabled

Rückgängig:
  sudo systemctl enable forward_v5.service
```

### T-5.1.12: 24h Stabilität (Extended)

```bash
Vorbedingung:
  Alle vorherigen Tests erfolgreich

Test:
  # Service starten
  sudo systemctl start forward_v5.service
  
  # Für 24h laufen lassen (oder im Hintergrund)
  # Nach 24h:
  
  # Uptime prüfen
  sudo systemctl status forward_v5.service | grep "Active:"
  
  # Neustarts prüfen
  sudo journalctl -u forward_v5 --since "24 hours ago" | grep -E "(Started|Stopped|Restart)"

Erwartet:
  Active: active (running) since [24h+ ago]
  Keine unerwarteten Restarts
  Keine Memory-Warnungen >90%
```

---

## Test-Checklist

```
□ T-5.1.1 Syntax-Check
□ T-5.1.2 Service Start
□ T-5.1.3 User/Group
□ T-5.1.4 Environment
□ T-5.1.5 WorkingDirectory
□ T-5.1.6 Restart-Policy
□ T-5.1.7 RestartSec
□ T-5.1.8 Graceful Shutdown
□ T-5.1.9 Journal-Logging
□ T-5.1.10 StandardOutput/Error
□ T-5.1.11 Enable/Disable
□ T-5.1.12 24h Stabilität (optional/extended)
```

---

## Sign-Off

| Rolle | Name | Datum | Unterschrift |
|-------|------|-------|--------------|
| Tester | | 2026-04-01 | |
| Reviewer | | 2026-04-01 | |
| Approver | | 2026-04-01 | |

---

**Ergebnis:** ⬜ PASS / ⬜ FAIL / ⬜ PENDING

**Nachfolgende Phase:** 5.2 (wenn zutreffend)
