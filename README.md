# Patterno Prototyp: Calls & Formulare der richtigen Person, Firma, Deal zuordnen
**Start:** `python3 match.py` (nur Python-Standardbibliothek). Liest `crm.json` + `events.json`, druckt eine Tabelle, schreibt `ergebnis.json`.
**Regeln:** 1) Firma über die Mail-Domain (nicht bei gmail & Co.), sonst über den bereinigten Namen (ohne GmbH, & Co. KG, -Systeme, klein geschrieben). Passt das auf mehrere Firmen, entscheidet die im CRM bekannte Person, sonst kommt das Ereignis auf die Prüfliste.
2) Person über die Mail. Bei Calls über die **tatsächlich verbundene** Nummer, nicht die angerufene (wegen Weiterleitungen).
3) Deal: der offene Deal der Firma. Kunde ohne offenen Deal → Vorschlag Expansion-Deal, Lead → Vorschlag neuer Deal.
4) Branche + Ausschreibungen/Jahr kommen an die Firma, der Sprint an den Deal. 5) Doppelte event_id wird übersprungen. 6) Unklare Fälle werden nicht geraten, sie kommen auf die Prüfliste.
**Was läuft:** Zuordnung mit Begründung je Ereignis und Quote am Ende, auf 20 Testereignissen (Weiterleitungen, Müller-Dublette, Bestandskunde, Doppel-Submit, unbekannte Nummer).
**Was nicht:** keine echte Anbindung an Attio, Cloudtalk oder Supabase. Es wird nichts geschrieben, nur vorgeschlagen. Wer per Freemail kommt, wird als neue Person vorgeschlagen, auch wenn die Person schon existiert.
**Als Nächstes:** Webhook-Empfänger für Fillout + Cloudtalk, Abgleich gegen die Firmen in Supabase, Schreiben über die Attio-API (idempotent über event_id), Prüfliste als Attio-Liste oder Slack-Nachricht.
