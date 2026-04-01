#!/bin/bash
# PUSH AUTHORIZATION - Muss von Agent vor jedem Push ausgeführt werden
# Dieses Script erzeugt ein temporäres Auth-Token

REPO_ROOT="/data/.openclaw/workspace/forward_v5"
SAFETY_MEMORY="$REPO_ROOT/.GIT_SAFETY_MEMORY.md"
AUTH_FILE="$REPO_ROOT/.git/.push_authorized"

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║     AGENT PUSH AUTHORIZATION                               ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Prüfe Safety Memory existiert
if [ ! -f "$SAFETY_MEMORY" ]; then
    echo "❌ FAIL: $SAFETY_MEMORY nicht gefunden"
    exit 1
fi

echo "📋 Safety Memory gefunden"
echo ""
echo "======================================================="
cat "$SAFETY_MEMORY"
echo "======================================================="
echo ""

# Explizite Abfrage (technisch erzwungen)
echo "Agent Pflicht-Checkliste:"
echo ""
read -p "[1] Hast du SAFETY_CHECKLIST.md gelesen? (ja/nein) " ANSWER1
if [ "$ANSWER1" != "ja" ]; then
    echo "❌ ABORTED - Checkliste nicht bestätigt"
    exit 1
fi

read -p "[2] Hast du alle 5 Pre-Commit Checks verifiziert? (ja/nein) " ANSWER2
if [ "$ANSWER2" != "ja" ]; then
    echo "❌ ABORTED - Checks nicht verifiziert"
    exit 1
fi

read -p "[3] Keine Secrets im diff vorhanden? (ja/nein) " ANSWER3
if [ "$ANSWER3" != "ja" ]; then
    echo "❌ ABORTED - Secrets check fehlt"
    exit 1
fi

read -p "[4] Keine .env Files gestaged? (ja/nein) " ANSWER4
if [ "$ANSWER4" != "ja" ]; then
    echo "❌ ABORTED - .env Check fehlt"
    exit 1
fi

read -p "[5] Red Lines verstanden (--no-verify = VERBOTEN)? (ja/nein) " ANSWER5
if [ "$ANSWER5" != "ja" ]; then
    echo "❌ ABORTED - Red Lines nicht bestätigt"
    exit 1
fi

# Authorization Token erstellen
touch "$AUTH_FILE"
echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║  ✅ AUTHORIZATION GRANTED                                  ║"
echo "║                                                            ║"
echo "║  Du hast 10 Minuten Zeit für: git push origin main        ║"
echo "║  Nach 10 Minuten läuft die Authorization ab.              ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Zeige git status
echo "Gepusht wird:"
git -C "$REPO_ROOT" status -sb
echo ""
