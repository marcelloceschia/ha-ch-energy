# GitHub Setup Anleitung für ha-sec-energy

## Schritt 1: Repo auf GitHub erstellen

1. Gehe zu https://github.com/new
2. **Repository name**: `ha-sec-energy`
3. **Description**: `Home Assistant Integration for SEC Energy Swiss electricity tariffs`
4. Wähle **Public** (für HACS erforderlich)
5. **Add a README file**: ❌ NICHT ankreuzen (wir haben schon eine)
6. **Add .gitignore**: ❌ Nicht nötig
7. **Choose a license**: ❌ Nicht nötig (wir haben schon eine)
8. Klicke **Create repository**

## Schritt 2: Remote hinzufügen & pushen

```bash
# Zum lokalen Repo wechseln
cd /home/hermes/repos/ha-sec-energy

# Remote hinzufügen (ersetze USERNAME mit deinem GitHub-Namen)
git remote add origin https://github.com/marcelloceschia/ha-sec-energy.git

# Push auf main
git branch -M main
git push -u origin main
```

## Schritt 3: Release erstellen (für HACS)

1. Auf GitHub: **Releases** → **Create a new release**
2. **Choose a tag**: `v1.0.0` (neu erstellen)
3. **Release title**: `v1.0.0 - Initial Release`
4. **Description**:
```markdown
## 🎉 Initial Release

### Features
- Dynamic DSO selection (Stadtwerke Wetzikon + custom URLs)
- Live tariff loading from SEC-Energy API
- Current price sensor with real-time calculation
- 24h price forecast sensor
- Base price (monthly fee) sensor
- Multi-step config flow
- German & English translations

### Installation
1. Add to HACS as custom repository
2. Install via HACS
3. Restart Home Assistant
4. Add integration via UI

### Supported Providers
- Stadtwerke Wetzikon
- Any SEC-Energy compatible API
```
5. Klicke **Publish release**

## Schritt 4: HACS einrichten

1. In Home Assistant: **HACS** → **Integrationen**
2. Klicke **⋮** → **Benutzerdefinierte Repositories**
3. **Repository**: `https://github.com/marcelloceschia/ha-sec-energy`
4. **Kategorie**: Integration
5. Klicke **Hinzufügen**
6. Suche nach "SEC Energy" und installiere

## Fertig! ✅

Die Integration ist jetzt über HACS installierbar.
