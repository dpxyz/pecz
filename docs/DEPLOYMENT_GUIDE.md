# Deployment Guide — Forward V5 Mission Control

## Wichtig: Einziges Build-Verzeichnis

**Cloudflare Pages baut NUR aus:**
```
/forward_v5/docs/site/          ← HIER arbeiten!
```

**Das äußere `/docs/site/` ist archiviert** (nicht mehr aktiv).

## Schnell-Deployment

```bash
cd /data/.openclaw/workspace/forward_v5/forward_v5/docs/site
# Änderungen vornehmen...
git add .
git commit -m "Update: ..."
git push origin main
```

## Automatischer Sync

Ein Symlink verbindet:
- `/docs/site` → `/forward_v5/docs/site`

So funktioniert beides:
- `cd forward_v5/docs/site` (empfohlen)
- `cd docs/site` (funktioniert auch via Symlink)

## Verzeichnisstruktur

```
pecz/
├── forward_v5/
│   └── docs/site/          ← Cloudflare Build Source (✓)
│       ├── docs/
│       │   ├── index.md    ← Mission Control
│       │   └── ...
│       └── mkdocs.yml
└── docs/
    └── site_ARCHIVED/      ← Alt (✗ nicht verwenden)
```

## Prüfung vor Commit

```bash
# Immer hier arbeiten:
pwd
# Ausgabe: .../forward_v5/docs/site

# Oder hier (via Symlink):
pwd  
# Ausgabe: .../docs/site 
# (zeigt trotzdem auf forward_v5/docs/site)
```

---
*Archiviert: 2026-03-30 | Cleanup by: Pecz*
