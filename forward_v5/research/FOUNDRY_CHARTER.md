# OpenClaw Foundry – Gründungsurkunde

1. OpenClaw Foundry ist ein wöchentlicher, vollautomatischer Prozess, der aus einer versionierten Spec wenige Strategiekandidaten erzeugt und nur solche weiterführt, die harte objektive Gates bestehen.
2. Die KI hat genau eine Rolle: Sie entwirft Strategien innerhalb eines klar begrenzten Suchraums, aber sie bewertet niemals selbst die Qualität ihrer Ergebnisse.
3. Die einzige Wahrheit des Systems liegt in spec.yaml, den eingefrorenen Datenfenstern, den Kosten- und Slippage-Annahmen und den versionierten Evaluationsregeln.
4. Jeder Lauf erzeugt zum Beispiel drei Kandidaten, prüft sie deterministisch über Syntax, Backtest, Mindestaktivität, Risiko, Walk-Forward- und Out-of-Sample-Gates und verwirft jeden Kandidaten ohne Diskussion bei FAIL.
5. Ein bestandener Kandidat wird nicht sofort als „live" betrachtet, sondern kontrolliert in den nächsten Betriebszustand wie Shadow oder Paper Trading promoted.
6. Ein nicht bestandener Kandidat wird weder manuell gerettet noch weichoptimiert, sondern vollständig verworfen und erst im nächsten geplanten Run durch neue Kandidaten ersetzt.
7. Das Nutzerprodukt ist kein Research-Dashboard, sondern eine einzige klare Discord-Nachricht, die den Wochenstatus ehrlich meldet: bestanden, promoted, verworfen oder nichts gefunden.
8. Innovation entsteht nicht durch mehr KI, sondern durch die Kombination aus maschineller Suche, harter Spezifikation, binären Entscheidungen und reproduzierbarer Auditierbarkeit.
9. Professionalität entsteht durch strikte Trennung von Generierung und Bewertung, realistische Marktannahmen, versionierte Artefakte und einen nachvollziehbaren Promotion-Pfad in den Betrieb.
10. OpenClaw Foundry ist damit keine Strategie-Spielwiese, sondern eine Strategy Factory, die jede Woche entweder belastbare Kandidaten liefert oder sauber dokumentiert, dass es unter den aktuellen Regeln keine gibt.

---

*Verfasst: 2026-04-18*
*Status: GÜLTIG – Grundlage für alle weiteren Entscheidungen*