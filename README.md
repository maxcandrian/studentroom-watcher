# studentroom-watcher

Automatischer Bot, der jeden Abend die Angebotsseiten der **Student Mentor
Foundation Lucerne** auf [studentroom.ch](https://www.studentroom.ch) prüft
(Standorte **Eichhof** und **Schweighof**) und per **Telegram** benachrichtigt,
sobald **ein Zimmer frei** wird. Die Nachricht enthält den **Link zur Website**
zum manuellen Prüfen; die Miete wird nur als Info mit angezeigt.

## Wie es funktioniert

- [`check_studentroom.py`](check_studentroom.py) lädt beide Angebotsseiten und
  liest die Zimmerliste. Jede Zimmerzeile hat eine Status-Klasse:
  `status1` = frei, `status2` = reserviert, `status3`/`status4` = vermietet.
  Die Miete steht in der Spalte `spalte5` („Miete inkl. NK").
  Der Inhalt ist serverseitig gerendert → es genügt ein einfacher HTTP-Abruf,
  **kein Browser/Playwright nötig**.
- Der GitHub-Actions-Workflow
  [`.github/workflows/check-studentroom.yml`](.github/workflows/check-studentroom.yml)
  führt das Skript **alle 5 Minuten** aus.
- Sobald **irgendein freies** Zimmer existiert, wird eine Telegram-Nachricht
  gesendet (beim manuellen Start immer eine Nachricht = Test).
- **Wiederhol-Schutz:** Ein Zimmer wird nur **einmal** gemeldet (wenn es neu
  frei wird), nicht bei jeder Prüfung. Der zuletzt gemeldete Stand wird über den
  GitHub-Actions-Cache gehalten (`STATE_FILE`). So gibt es kein Spam.
- **Status-Update 2×/Woche** (Mo & Do, ~09:00): Kontroll-Nachricht auch ohne
  freie Zimmer – als Lebenszeichen und zum manuellen Nachprüfen (mit Zählern
  frei / reserviert / vermietet pro Standort und Website-Link).
- Der Bot läuft komplett auf GitHubs Servern – **kein Akku-/Datenverbrauch auf
  dem Handy**, das empfängt nur die Telegram-Nachricht.

## Einrichtung

### 1. Telegram-Bot erstellen

1. In Telegram [@BotFather](https://t.me/BotFather) öffnen → `/newbot` → Namen
   und Benutzernamen wählen. Du erhältst ein **Token** (`123456:ABC-...`).
2. Deinen neuen Bot in Telegram öffnen und **Start** drücken (`/start`).
3. Deine **Chat-ID** ermitteln: im Browser
   `https://api.telegram.org/bot<TOKEN>/getUpdates` öffnen und das Feld
   `chat.id` ablesen.

### 2. GitHub Secrets setzen

Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Name               | Wert                     |
| ------------------ | ------------------------ |
| `TELEGRAM_TOKEN`   | Token von @BotFather     |
| `TELEGRAM_CHAT_ID` | deine Chat-ID            |

### 3. Manuell testen

Repo → **Actions → „Studentroom Zimmer-Check" → Run workflow**.
Beim manuellen Lauf wird immer eine Telegram-Nachricht gesendet (auch wenn
gerade keine Zimmer frei sind) – so siehst du, dass alles funktioniert.

## Zeitplan & Zuverlässigkeit

`cron: "*/5 * * * *"` – Prüfung **alle 5 Minuten** (Minimum bei GitHub).
Bei einem freien Zimmer kommt die Meldung also typischerweise innerhalb von
**~5–15 Minuten**. Hinweise:

- GitHub-Cron ist **nicht sekundengenau**; bei hoher Last können Läufe sich um
  einige Minuten verschieben. Es gibt keine echte Push-/Sofort-Benachrichtigung,
  weil die Website keine API dafür anbietet – jede Lösung muss regelmäßig pollen.
- Häufiges Pollen verbraucht auf **öffentlichen** Repos **keine** Actions-Minuten
  (unbegrenzt gratis). Bei privaten Repos würde es das Gratis-Kontingent sprengen.
- [`.github/workflows/keepalive.yml`](.github/workflows/keepalive.yml) macht 1×
  im Monat einen leeren Commit, damit GitHub den Zeitplan nicht nach 60 Tagen
  Inaktivität pausiert.

## Lokal ausführen

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt

venv/bin/python check_studentroom.py --selftest   # Parser-Test
venv/bin/python check_studentroom.py --dry-run    # Live-Check ohne Versand
```

## Konfiguration

Über Umgebungsvariablen (im Workflow gesetzt):

| Variable           | Default | Bedeutung                                        |
| ------------------ | ------- | ------------------------------------------------ |
| `ALWAYS_NOTIFY`    | –       | `1` → auch ohne Treffer senden (manueller Test)  |
| `TELEGRAM_TOKEN`   | –       | Bot-Token                                        |
| `TELEGRAM_CHAT_ID` | –       | Ziel-Chat-ID                                     |
