"""Ordnet Fillout- und Cloudtalk-Ereignisse Person, Firma und Deal im CRM zu.
Start: python3 match.py   (nur Standardbibliothek)"""
import json

FREEMAIL = {"gmail.com", "gmx.de", "web.de", "outlook.com", "t-online.de", "icloud.com", "yahoo.de"}
# Rechtsformen und Zusätze, die beim Namensvergleich wegfallen
FUELLWOERTER = {"gmbh", "mbh", "ag", "kg", "co", "ug", "ohg", "se", "systeme", "gruppe", "holding"}


# ---------- Bereinigen ----------

def bereinige_name(name):
    n = (name or "").lower()
    for alt, neu in [("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"), ("-", " "), ("&", " "), (".", " ")]:
        n = n.replace(alt, neu)
    return " ".join(w for w in n.split() if w not in FUELLWOERTER)


def bereinige_nummer(nummer):
    ziffern = "".join(c for c in (nummer or "") if c.isdigit())
    if ziffern.startswith("00"):
        return ziffern[2:]
    if ziffern.startswith("0"):
        return "49" + ziffern[1:]          # 069 ... -> 4969 ...
    return ziffern


# ---------- Webhook -> einheitliches Ereignis ----------

def lies_ereignis(roh):
    if roh["source"] == "fillout":
        f = {q["name"]: q["value"] for q in roh["submission"]["questions"]}
        return {"id": roh["event_id"], "typ": "Formular", "mail": f["E-Mail"].lower(),
                "firma_name": f["Firmenname"], "branche": f["Branche"],
                "ausschreibungen": f["Anzahl Ausschreibungen pro Jahr"], "sprint": f["Sprint"]}
    d = roh["data"]
    return {"id": roh["event_id"], "typ": "Call", "angerufen": d["called_number"],
            "verbunden": d["connected_number"], "notiz": d["note"]}


# ---------- Regeln ----------

def finde_person_per_mail(mail, crm):
    return next((p for p in crm["personen"] if p["mail"].lower() == mail), None)


def finde_firma(ev, crm, person):
    """Gibt (Liste der Treffer, Weg) zurück. Genau 1 Treffer = eindeutig."""
    domain = ev["mail"].split("@")[1]
    if domain not in FREEMAIL:
        treffer = [f for f in crm["firmen"] if f["domain"] == domain]
        if len(treffer) == 1:
            return treffer, f"Domain {domain}"
    else:
        treffer = []
    # Domain fehlt, ist Freemail oder gehört mehreren Firmen -> bereinigter Name
    name = bereinige_name(ev["firma_name"])
    pool = treffer or crm["firmen"]
    nach_name = [f for f in pool if bereinige_name(f["name"]) == name] or treffer
    if len(nach_name) > 1 and person and any(f["id"] == person["firma_id"] for f in nach_name):
        # Dublette: die im CRM bekannte Person entscheidet
        return [f for f in nach_name if f["id"] == person["firma_id"]], "Domain doppelt, bekannte Person entscheidet"
    weg = f'Name "{name}"' if not treffer else f"Domain {domain} + Name"
    return nach_name, weg


def finde_deal(firma, crm):
    offen = [d for d in crm["deals"] if d["firma_id"] == firma["id"] and d["offen"]]
    if len(offen) == 1:
        return offen[0]["name"], "offener Deal", None
    if len(offen) > 1:
        return None, None, f"{len(offen)} offene Deals"
    if firma["status"] == "Kunde":
        return f"Expansion {firma['name']} (Vorschlag)", "Kunde -> Expansion", None
    return f"Neuer Deal {firma['name']} (Vorschlag)", "kein offener Deal -> neu", None


def ordne_zu(ev, crm):
    firmen = {f["id"]: f for f in crm["firmen"]}
    ergebnis = {"event_id": ev["id"], "typ": ev["typ"], "person": "-", "firma": "-", "deal": "-", "updates": {}}

    def pruefen(grund):
        return {**ergebnis, "status": "pruefen", "grund": grund}

    gruende = []
    if ev["typ"] == "Call":
        # Person über die TATSÄCHLICH verbundene Nummer, nie über die angerufene
        nr = bereinige_nummer(ev["verbunden"])
        treffer = [p for p in crm["personen"] if bereinige_nummer(p["telefon"]) == nr]
        if len(treffer) != 1:
            return pruefen(f"verbundene Nummer {ev['verbunden']} " + ("unbekannt" if not treffer else "mehrdeutig"))
        person = treffer[0]
        firma = firmen[person["firma_id"]]
        weitergeleitet = bereinige_nummer(ev["angerufen"]) != nr
        gruende.append("weiterverbunden, Person über verbundene Nr." if weitergeleitet else "Person über Nummer")
    else:
        person = finde_person_per_mail(ev["mail"], crm)
        kandidaten, weg = finde_firma(ev, crm, person)
        if len(kandidaten) > 1:
            return pruefen(f"{weg}: {len(kandidaten)} Firmen möglich (" + " / ".join(f["name"] for f in kandidaten) + ")")
        if person and kandidaten and kandidaten[0]["id"] != person["firma_id"]:
            return pruefen("Mail-Person gehört zu anderer Firma als Domain/Name")
        if kandidaten:
            firma = kandidaten[0]
            gruende.append(f"Firma über {weg}")
        elif person:
            firma = firmen[person["firma_id"]]
            gruende.append("Firma über bekannte Person")
        else:
            firma = {"id": None, "name": ev["firma_name"], "status": "Lead", "neu": True}
            gruende.append("unbekannt -> neue Firma")
        gruende.append("Person über Mail" if person else "neue Person")
        ergebnis["updates"] = {
            "firma": {"branche": ev["branche"], "ausschreibungen_pro_jahr": ev["ausschreibungen"]},
            "deal": {"sprint": ev["sprint"]},
        }

    deal, deal_grund, problem = finde_deal(firma, crm) if firma.get("id") else (
        f"Neuer Deal {firma['name']} (Vorschlag)", "neue Firma -> neuer Deal", None)
    if problem:
        return pruefen(problem)
    gruende.append(deal_grund)

    ergebnis["person"] = person["name"] if person else f"neu: {ev['mail']}"
    ergebnis["firma"] = ("neu: " if firma.get("neu") else "") + firma["name"]
    ergebnis["deal"] = deal
    return {**ergebnis, "status": "auto", "grund": "; ".join(gruende)}


# ---------- Ausgabe ----------

def drucke_tabelle(zeilen):
    spalten = ["event_id", "typ", "person", "firma", "deal", "grund"]
    titel = ["event_id", "Typ", "Person", "Firma", "Deal", "Begründung"]
    breite = [max(len(t), *(len(str(z[s])) for z in zeilen)) for s, t in zip(spalten, titel)]
    zeile = lambda werte: " | ".join(str(w).ljust(b) for w, b in zip(werte, breite))
    print(zeile(titel))
    print("-+-".join("-" * b for b in breite))
    for z in zeilen:
        print(zeile([z[s] for s in spalten]))


def main():
    crm = json.load(open("crm.json", encoding="utf-8"))
    rohdaten = json.load(open("events.json", encoding="utf-8"))

    gesehen, zeilen = set(), []
    for roh in rohdaten:
        if roh["event_id"] in gesehen:   # Webhook doppelt geliefert / doppelt abgeschickt
            zeilen.append({"event_id": roh["event_id"], "typ": "-", "person": "-", "firma": "-", "deal": "-",
                           "status": "skip", "grund": "doppelte event_id, übersprungen"})
            continue
        gesehen.add(roh["event_id"])
        zeilen.append(ordne_zu(lies_ereignis(roh), crm))

    drucke_tabelle(zeilen)
    auto = sum(z["status"] == "auto" for z in zeilen)
    pruef = [z for z in zeilen if z["status"] == "pruefen"]
    skip = sum(z["status"] == "skip" for z in zeilen)

    print("\nPrüfliste:")
    for z in pruef:
        print(f"  - {z['event_id']}: {z['grund']}")
    json.dump(zeilen, open("ergebnis.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n{auto} von {len(rohdaten)} automatisch zugeordnet, {len(pruef)} auf der Prüfliste"
          f" ({skip} Dublette übersprungen). Details inkl. Feld-Updates: ergebnis.json")


if __name__ == "__main__":
    main()
