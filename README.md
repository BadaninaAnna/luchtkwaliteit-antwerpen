# Luchtkwaliteit Antwerpen: live dashboard met datakwaliteitscontrole

**▶ Live dashboard: [badaninaanna.github.io/luchtkwaliteit-antwerpen](https://badaninaanna.github.io/luchtkwaliteit-antwerpen/)**

*Elk uur automatisch bijgewerkt met de nieuwste metingen van 37 officiële meetstations rond Antwerpen.*

**Tools:** Python (pandas) · GitHub Actions (geplande ETL) · GitHub Pages · Plotly · REST-API · metrologische kwaliteitscontrole

---

## Wat doet dit project?

Een volledig geautomatiseerde datapijplijn, zonder server of betaalde diensten:

```
IRCEL-CELINE API  ──(elk uur, GitHub Actions)──►  ophalen.py  ──►  data/metingen/*.csv
                                                                          │
                                       kwaliteit.py (controles + normen) ◄┘
                                                    │
                                       dashboard.py ─►  docs/index.html  ──►  GitHub Pages
```

1. **Ophalen.** Elk uur haalt een GitHub Actions-workflow de uurwaarden van 81 meetreeksen op
   (NO₂, PM2,5, PM10, black carbon, ozon) bij de REST-API van IRCEL-CELINE. De laatste 7 dagen worden telkens
   opnieuw opgehaald, omdat recente (voorlopige) waarden nog gecorrigeerd worden.
2. **Controleren.** Elke uurwaarde krijgt automatische kwaliteitsvlaggen (zie hieronder).
3. **Toetsen.** Daggemiddelden en jaargemiddelden worden getoetst aan de WHO-richtlijnen 2021 en de nieuwe
   EU-grenswaarden die vanaf 2030 gelden.
4. **Publiceren.** Een statische webpagina met interactieve grafieken wordt opnieuw gebouwd en via GitHub Pages
   gepubliceerd. De data blijft als CSV in de repository, zodat de volledige historiek controleerbaar is.

## Datakwaliteit: het metrologische deel

Ruwe meetdata van een sensornetwerk bevat altijd fouten. Het dashboard controleert elke meetreeks automatisch:

| Controle | Regel | Waarom |
|---|---|---|
| **Storing** | > 6 uur geen data | toestel of datatransmissie uitgevallen |
| **Vastgelopen meting** | ≥ 24 opeenvolgende identieke uurwaarden | een echte concentratie is nooit een dag lang exact constant |
| **Lokale piek** | waarde > 5× de netwerkmediaan **én** ruim erboven | onderscheidt een lokale fout of bron van een regionale gebeurtenis |
| **Verschuiving** | verhouding station/netwerk wijkt ≥ 3 dagen > 40 % af van haar eigen 90-daagse niveau | mogelijke drift of kalibratiefout |
| **Volledigheid** | < 75 % van de uren in de laatste 7 dagen | onvoldoende data voor betrouwbare gemiddelden |

**Wat de controles in de historiek vonden (jan 2025 – okt 2026):**

- Een PM10-meter die **114 uur** (bijna 5 dagen) exact dezelfde waarde gaf, en twee andere met 89 en 112 uur.
- Een station dat sinds 13 oktober 2026 geen data meer levert.
- Een **lokale piek** van 1 016 µg/m³ PM10 (Van Averbekelaan, 12 maart 2026), terwijl de netwerkmediaan op dat
  uur 17 µg/m³ was: gemarkeerd. De meeste lokale pieken komen van de stations in Beveren, naast de haven.
- **Regionale fijnstofepisodes** in maart 2025 en maart 2026, met een netwerkmediaan PM10 tot 95 µg/m³:
  alle stations stijgen samen, dus geen meetfout en ook niet gemarkeerd. Dat onderscheid is precies waarom
  de piekcontrole met het netwerk vergelijkt en niet alleen met de eigen historiek.

## Normen: haalt Antwerpen de EU-grenswaarden van 2030?

Jaargemiddelden 2025 over alle stations (mediaan van de stations):

| Stof | Antwerpen 2025 | EU nu | EU 2030 | WHO 2021 |
|---|---|---|---|---|
| PM2,5 | 10,5 µg/m³ | 25 | **10** | 5 |
| PM10 | 19,3 µg/m³ | 40 | **20** | 15 |
| NO₂ | 22,8 µg/m³ | 40 | **20** | 10 |

Alle stations halen de huidige EU-normen ruim. Maar voor PM2,5 en NO₂ ligt de mediaan van de stations nog
**boven de strengere grenswaarden die vanaf 2030 gelden**, en overal boven de WHO-richtlijnen.

## Projectstructuur

```
├── .github/workflows/bijwerken.yml   # geplande workflow: elk uur ophalen, controleren, publiceren
├── src/
│   ├── ophalen.py                    # REST-API → maandelijkse CSV's (incrementeel, idempotent)
│   ├── kwaliteit.py                  # uurrooster, kwaliteitsvlaggen, status, dag- en jaarnormen
│   ├── dashboard.py                  # bouwt docs/index.html
│   └── sjabloon.html                 # HTML/JS-sjabloon (Plotly)
├── data/
│   ├── reeksen.csv                   # metadata van de meetreeksen (station, stof, ligging)
│   └── metingen/JJJJ-MM.csv          # uurwaarden, tijd in UTC
└── docs/index.html                   # het gepubliceerde dashboard
```

## Zelf uitvoeren

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python src/ophalen.py --ontdek --vanaf 2025-01-01   # eenmalig: meetreeksen zoeken en historiek ophalen
python src/ophalen.py                               # bijwerken
python src/dashboard.py                             # dashboard bouwen
```

## Bron en voorbehoud

Data: [IRCEL-CELINE](https://www.irceline.be), het Belgisch interregionaal centrum voor luchtkwaliteit
(Vlaamse Milieumaatschappij, Leefmilieu Brussel, AwAC). Recente uurwaarden zijn **voorlopig**: IRCEL-CELINE
valideert ze later nog. Dit dashboard is een persoonlijk portfolioproject en geen officiële informatiebron.
