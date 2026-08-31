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
  führt das Skript täglich zeitgesteuert aus.
- Sobald **irgendein freies** Zimmer existiert, wird eine Telegram-Nachricht
  gesendet (beim manuellen Start immer eine Nachricht = Test).

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

## Zeitplan

`cron: "0 16 * * *"` (UTC). GitHub-Cron kennt keine Sommer-/Winterzeit:

- **Sommerzeit** (CEST): 16:00 UTC = **18:00** Europe/Zurich
- **Winterzeit** (CET): 16:00 UTC = **17:00** Europe/Zurich

Für exakt 18:00 ganzjährig kann man eine zweite Cron-Zeile `0 17 * * *`
ergänzen. Hinweis: geplante GitHub-Actions-Läufe können sich um einige Minuten
verzögern.

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
