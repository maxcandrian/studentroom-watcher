#!/usr/bin/env python3
"""
studentroom-watcher
===================
Prueft die Angebotsseiten der Student Mentor Foundation Lucerne auf
studentroom.ch (Standorte Eichhof und Schweighof) auf freie Zimmer bis zu
einem Maximalpreis und benachrichtigt per Telegram.

Erkennung (Stand 2026-08, gegen die echte Seite verifiziert)
------------------------------------------------------------
Die Zimmerliste ist ein "cimmotool"-Widget. Jede Zimmerzeile ist ein
    <div class="row statusN ...">
mit einer Status-Klasse, die per CSS eindeutig belegt ist:
    status1 = frei         (gruen)
    status2 = reserviert   (blau)
    status3 / status4 = vermietet (rot)
Die Miete steht in der Zelle  <div class="col spalte5 ...">  ("Miete inkl. NK").
Weitere Spalten: spalte6 = Zimmer-Nr, spalte4 = Wohngemeinschaft,
spalte11 = Bezug (Einzugsdatum).

Der Seiteninhalt wird serverseitig gerendert, deshalb genuegt ein einfacher
HTTP-Abruf mit `requests` -- es wird KEIN Browser (Playwright) benoetigt.

Benutzung
---------
    python check_studentroom.py            # Live-Check
    python check_studentroom.py --selftest # Parser gegen eingebautes Fixture testen
    python check_studentroom.py --dry-run  # Live-Check, Nachricht nur ausgeben statt senden

Umgebungsvariablen
------------------
    TELEGRAM_TOKEN     Bot-Token von @BotFather        (fuer Versand noetig)
    TELEGRAM_CHAT_ID   Ziel-Chat-ID                    (fuer Versand noetig)
    ALWAYS_NOTIFY      "1"/"true" -> auch eine Nachricht senden, wenn nichts
                       gefunden wurde (fuer den manuellen Test-Lauf)

Gemeldet wird, sobald ueberhaupt ein Zimmer frei ist (unabhaengig vom Preis);
die Miete wird nur als Info angezeigt. Zum Pruefen dient der Link zur Website.
"""

from __future__ import annotations

import os
import re
import sys
import json
import html as htmllib

import requests
from bs4 import BeautifulSoup


# --- Konfiguration ----------------------------------------------------------

LOCATIONS = {
    "Eichhof": "https://www.studentroom.ch/angebot-eichhof",
    "Schweighof": "https://www.studentroom.ch/angebot-schweighof",
}

STATUS_MAP = {
    "status1": "frei",
    "status2": "reserviert",
    "status3": "vermietet",
    "status4": "vermietet",
}

# Markierungen fuer den "keine Daten"-Zustand der Liste.
EMPTY_MARKERS = ("keine Zimmer frei", "Kein Datensatz")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 studentroom-watcher"
)


# --- HTTP / Parsing ---------------------------------------------------------

def fetch(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    # Seite ist UTF-8; apparent_encoding als Fallback.
    resp.encoding = resp.encoding or resp.apparent_encoding or "utf-8"
    return resp.text


def parse_price(text: str):
    """Extrahiert die Franken-Miete aus einem Zellentext.

    Beispiele: "CHF 640.-" -> 640, "1'200.-" -> 1200, "735" -> 735.
    Gibt None zurueck, wenn keine plausible Zahl gefunden wird.
    """
    if not text:
        return None
    cleaned = text.replace("'", "").replace("’", "")  # Tausender-Apostroph weg
    nums = re.findall(r"\d+", cleaned)
    if not nums:
        return None
    # Erste Zahlengruppe ist der Frankenbetrag ("640.-" -> ["640"]).
    return int(nums[0])


def parse_rooms(page_html: str):
    """Gibt (rooms, list_is_empty) zurueck.

    rooms: Liste von dicts mit status, price, zimmer, wg, bezug.
    list_is_empty: True, wenn die Seite eine der bekannten "leer"-Meldungen zeigt.
    """
    soup = BeautifulSoup(page_html, "html.parser")
    scope = soup.select_one(".cimmotool.view") or soup

    rooms = []
    for row in scope.select("div.row"):
        classes = row.get("class", []) or []
        status_class = next((c for c in classes if c in STATUS_MAP), None)
        if status_class is None:
            continue  # Kopfzeile / Leer-Meldung / sonstige Zeilen ueberspringen

        def cell(selector: str) -> str:
            el = row.select_one(selector)
            return el.get_text(" ", strip=True) if el else ""

        price_text = cell(".spalte5")
        rooms.append(
            {
                "status": STATUS_MAP[status_class],
                "price": parse_price(price_text),
                "price_text": price_text,
                "zimmer": cell(".spalte6"),
                "wg": cell(".spalte4"),
                "bezug": cell(".spalte11"),
            }
        )

    list_is_empty = any(marker in page_html for marker in EMPTY_MARKERS)
    return rooms, list_is_empty


# --- Auswertung -------------------------------------------------------------

def evaluate():
    """Ruft alle Standorte ab und wertet aus.

    Rueckgabe: (hits, summary_lines, anomalies)
      hits      : Liste (location, room) fuer JEDES freie Zimmer (ohne Preisfilter)
      summary   : Zusammenfassungszeilen pro Standort (fuer den Test-Lauf)
      anomalies : Liste von Fehler-/Warntexten (Abruffehler, Struktur-Aenderung)
    """
    hits = []
    summary_lines = []
    anomalies = []

    for name, url in LOCATIONS.items():
        try:
            page_html = fetch(url)
        except Exception as exc:  # Netzwerk-/HTTP-Fehler
            anomalies.append(f"{name}: Abruf fehlgeschlagen ({exc}).")
            summary_lines.append(f"{name}: ⚠️ Abruf fehlgeschlagen")
            continue

        rooms, list_is_empty = parse_rooms(page_html)
        free = [r for r in rooms if r["status"] == "frei"]

        for r in free:
            hits.append((name, r))

        # Struktur-Warnung: keine erkannten Zimmerzeilen UND keine bekannte
        # "leer"-Meldung -> die Seitenstruktur hat sich evtl. geaendert.
        if not rooms and not list_is_empty:
            anomalies.append(
                f"{name}: Unerwartete Seitenstruktur – weder Zimmerzeilen "
                f"noch eine bekannte 'keine Zimmer frei'-Meldung gefunden. "
                f"Bitte {url} manuell pruefen (evtl. Skript anpassen)."
            )

        if free:
            summary_lines.append(f"{name}: ✅ {len(free)} freie(s) Zimmer")
        else:
            summary_lines.append(f"{name}: keine freien Zimmer")

    return hits, summary_lines, anomalies


LINKS_LINE = (
    "\U0001f517 <a href=\"https://www.studentroom.ch/angebot-eichhof\">Eichhof</a> · "
    "<a href=\"https://www.studentroom.ch/angebot-schweighof\">Schweighof</a>"
)


def build_message(hits, summary_lines, anomalies) -> str:
    parts = []
    if hits:
        parts.append("\U0001f3e0 <b>Freie Zimmer verfuegbar!</b>\n")
        # Treffer pro Standort gruppieren.
        by_loc = {}
        for name, r in hits:
            by_loc.setdefault(name, []).append(r)
        for name in LOCATIONS:
            rooms = by_loc.get(name)
            if rooms:
                parts.append(f"<b>{name}</b> – {len(rooms)} frei:")
                for r in rooms:
                    price = f"CHF {r['price']}" if r["price"] is not None else (r["price_text"] or "Preis unklar")
                    details = " · ".join(
                        p for p in [
                            f"Zimmer {r['zimmer']}" if r["zimmer"] else "",
                            r["wg"],
                            price,
                            f"Bezug {r['bezug']}" if r["bezug"] else "",
                        ] if p
                    )
                    parts.append(f" • {htmllib.escape(details)}")
            else:
                parts.append(f"<b>{name}</b>: keine freien Zimmer")
        parts.append("")
        parts.append("\U0001f449 Jetzt selbst pruefen:")
        parts.append(LINKS_LINE)
    else:
        parts.append("ℹ️ Aktuell keine freien Zimmer.")
        parts.append("")
        parts.extend(summary_lines)
        parts.append("")
        parts.append(LINKS_LINE)

    if anomalies:
        parts.append("")
        parts.append("⚠️ <b>Hinweise:</b>")
        parts.extend(htmllib.escape(a) for a in anomalies)

    return "\n".join(parts)


# --- Telegram ---------------------------------------------------------------

def send_telegram(text: str) -> None:
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_TOKEN / TELEGRAM_CHAT_ID sind nicht gesetzt.")
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        },
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"Telegram-Fehler {resp.status_code}: {resp.text}")


# --- Selbsttest (eingebautes Fixture aus der echten Struktur) ---------------

SELFTEST_HTML = """
<div class="cimmotool view">
  <div class="legend">
    <div><div class="status1"></div><label>Zimmer frei</label></div>
  </div>
  <div class="list top">
    <div class="row header">
      <div class="col spalte8 left">H.Nr</div>
      <div class="col spalte6 left">Zimmer-Nr</div>
      <div class="col spalte2 left">Etage</div>
      <div class="col spalte4 left">Wohngemeinschaft</div>
      <div class="col spalte5 right">Miete inkl. NK</div>
      <div class="col spalte11 left">Bezug</div>
    </div>
  </div>
  <div class="list scroll">
    <div class="row status1">
      <div class="col spalte8">1</div>
      <div class="col spalte6">A 12</div>
      <div class="col spalte2">2. OG</div>
      <div class="col spalte4">Zimmer in 3er-Wohnung</div>
      <div class="col spalte5 right">CHF 640.-</div>
      <div class="col spalte11">01.10.2026</div>
    </div>
    <div class="row status1">
      <div class="col spalte8">2</div>
      <div class="col spalte6">B 04</div>
      <div class="col spalte2">EG</div>
      <div class="col spalte4">Zimmer in 1er-Wohnung</div>
      <div class="col spalte5 right">CHF 935.-</div>
      <div class="col spalte11">01.11.2026</div>
    </div>
    <div class="row status2">
      <div class="col spalte8">3</div>
      <div class="col spalte6">C 07</div>
      <div class="col spalte2">1. OG</div>
      <div class="col spalte4">Zimmer in 4er-Wohnung</div>
      <div class="col spalte5 right">CHF 580.-</div>
      <div class="col spalte11">01.09.2026</div>
    </div>
    <div class="row status3">
      <div class="col spalte8">4</div>
      <div class="col spalte6">D 01</div>
      <div class="col spalte2">3. OG</div>
      <div class="col spalte4">Zimmer in 5er-Wohnung</div>
      <div class="col spalte5 right">CHF 550.-</div>
      <div class="col spalte11">01.09.2026</div>
    </div>
  </div>
</div>
"""

EMPTY_HTML = """
<div class="cimmotool view">
  <div class="list top"><div class="row header"><div class="col spalte5">Miete inkl. NK</div></div></div>
  <div class="list scroll"><div class="row"><div class="col block">Zur Zeit sind keine Zimmer frei</div></div></div>
</div>
"""


def selftest() -> int:
    ok = True

    rooms, empty = parse_rooms(SELFTEST_HTML)
    free = [r for r in rooms if r["status"] == "frei"]
    prices = sorted(r["price"] for r in free)

    checks = [
        ("Zeilen erkannt (4)", len(rooms) == 4),
        ("Freie Zimmer erkannt (2)", len(free) == 2),
        ("Beide freien Zimmer sind Treffer (640 & 935)", prices == [640, 935]),
        ("Zimmer-Nr des 640er 'A 12'", any(r["zimmer"] == "A 12" for r in free if r["price"] == 640)),
        ("Reserviert nicht als frei", all(r["status"] != "frei" for r in rooms if r["price"] == 580)),
        ("Vermietet nicht als frei", all(r["status"] != "frei" for r in rooms if r["price"] == 550)),
        ("Fixture nicht als 'leer' erkannt", empty is False),
    ]

    rooms2, empty2 = parse_rooms(EMPTY_HTML)
    checks.append(("Leere Liste: keine Zeilen", len(rooms2) == 0))
    checks.append(("Leere Liste: als 'leer' erkannt", empty2 is True))

    # Preis-Parser-Faelle
    price_cases = {"CHF 640.-": 640, "1'200.-": 1200, "735": 735, "": None, "CHF -.-": None}
    for text, expected in price_cases.items():
        checks.append((f"parse_price({text!r}) == {expected}", parse_price(text) == expected))

    print("Selbsttest:")
    for label, passed in checks:
        print(f"  [{'OK' if passed else 'FAIL'}] {label}")
        ok = ok and bool(passed)

    print()
    print("Beispiel-Nachricht bei Treffer:")
    hits = [("Eichhof", r) for r in free]
    print(build_message(hits, [], []))
    print()
    return 0 if ok else 1


# --- Zustand / Wiederhol-Schutz ---------------------------------------------
# Damit bei haeufiger Pruefung (z.B. alle 5 Min) nicht bei JEDEM Lauf eine
# Nachricht kommt, merken wir uns den zuletzt gemeldeten Stand. Es wird nur
# gesendet, wenn sich etwas Meldenswertes geaendert hat (ein Zimmer NEU frei
# wird oder eine neue Warnung auftritt). Der Stand wird zwischen den Laeufen
# ueber den GitHub-Actions-Cache erhalten (siehe Workflow, STATE_FILE).

def signature(hits, anomalies) -> dict:
    free_keys = sorted(
        f"{name}|{r['zimmer']}|{r['wg']}|{r['bezug']}|{r['price_text']}"
        for name, r in hits
    )
    return {"free": free_keys, "anom": sorted(anomalies)}


def load_state(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, ValueError):
        return None


def save_state(path, sig) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(sig, fh, ensure_ascii=False)


# --- Einstieg ---------------------------------------------------------------

def main(argv) -> int:
    if "--selftest" in argv:
        return selftest()

    dry_run = "--dry-run" in argv
    always_notify = os.environ.get("ALWAYS_NOTIFY", "").lower() in ("1", "true", "yes")
    state_file = os.environ.get("STATE_FILE")

    hits, summary_lines, anomalies = evaluate()

    print("Zusammenfassung:")
    for line in summary_lines:
        print("  " + line)
    for a in anomalies:
        print("  ! " + a)

    has_report = bool(hits) or bool(anomalies)
    sig = signature(hits, anomalies)

    # Wiederhol-Schutz: nur senden, wenn sich der meldenswerte Stand aenderte.
    if state_file:
        changed = load_state(state_file) != sig
        save_state(state_file, sig)  # immer den aktuellen Stand sichern
    else:
        changed = True  # ohne Zustandsdatei (z.B. lokaler Lauf) wie bisher

    should_notify = always_notify or (has_report and changed)
    if not should_notify:
        reason = "nichts frei" if not has_report else "bereits gemeldet"
        print(f"Nichts Neues zu melden ({reason}) – keine Nachricht gesendet.")
        return 0

    message = build_message(hits, summary_lines, anomalies)

    if dry_run or not (os.environ.get("TELEGRAM_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")):
        print("\n--- Nachricht (nicht gesendet) ---\n" + message)
        return 0

    send_telegram(message)
    print("Telegram-Nachricht gesendet.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
