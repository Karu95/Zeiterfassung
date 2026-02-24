# Render Deployment (Anfaengersicher)

## Ziel
- Weltweit erreichbar
- HTTPS automatisch
- Keine Server-Wartung
- Deploy per Git + Render

## 1) Lokal vorbereiten

```bash
cd "/Users/karuanosi/Documents/New project/zeiterfassung"
source .venv/bin/activate
pip install -r requirements.txt
python3 -m py_compile app.py
```

## 2) In ein Git-Repository pushen

Falls noch kein Git-Repo vorhanden ist:

```bash
cd "/Users/karuanosi/Documents/New project/zeiterfassung"
git init
git add .
git commit -m "Initiale Zeiterfassung mit Render-Setup"
```

Neues GitHub-Repo anlegen und dann (Beispiel):

```bash
git branch -M main
git remote add origin https://github.com/DEIN-USER/zeiterfassung.git
git push -u origin main
```

## 3) Render verbinden

1. In Render einloggen
2. **New +** -> **Blueprint**
3. GitHub-Repo `zeiterfassung` waehlen
4. Render erkennt `render.yaml` automatisch
5. **Apply** klicken

Danach erstellt Render automatisch:
- Web Service (`zeiterfassung-app`)
- PostgreSQL Datenbank (`zeiterfassung-db`)

## 4) Nach erstem Deploy testen

- Render URL oeffnen (z. B. `https://zeiterfassung-app.onrender.com`)
- Login testen:
  - `admin@admin.de`
  - `admin123`

## 5) Admin-Passwort sofort aendern

- In der App als Admin einloggen
- Entweder neuen Admin anlegen und alten deaktivieren
- Oder bestehendes Passwort per kleiner Admin-Funktion erweitern (optional im naechsten Schritt)

## 6) Eigene Firmen-Domain von SiteGround anbinden

Beispiel Ziel-Domain: `zeit.deinefirma.de`

### In Render
1. Web Service oeffnen
2. **Settings** -> **Custom Domains**
3. `zeit.deinefirma.de` hinzufuegen
4. Render zeigt DNS-Ziel (meist CNAME) an

### In SiteGround (DNS Zone Editor)
1. `Site Tools` -> `Domain` -> `DNS Zone Editor`
2. CNAME anlegen:
   - **Name/Host**: `zeit`
   - **Wert/Points to**: Render-Ziel aus Custom Domains
3. Speichern

DNS-Check lokal:

```bash
dig +short zeit.deinefirma.de
```

Sobald DNS aktiv ist, stellt Render HTTPS automatisch bereit.

## 7) Kuenftige Updates

```bash
cd "/Users/karuanosi/Documents/New project/zeiterfassung"
git add .
git commit -m "Update"
git push
```

Render deployed danach automatisch neu.
