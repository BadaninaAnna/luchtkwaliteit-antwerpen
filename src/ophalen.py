"""Haalt uurwaarden van luchtkwaliteitsmeetstations rond Antwerpen op bij IRCEL-CELINE.

Gebruik:
    python src/ophalen.py --ontdek            # meetreeksen (opnieuw) zoeken -> data/reeksen.csv
    python src/ophalen.py --vanaf 2025-01-01  # historiek ophalen (eenmalig)
    python src/ophalen.py                     # bijwerken: laatste 7 dagen opnieuw ophalen

De laatste 7 dagen worden telkens opnieuw opgehaald, omdat IRCEL-CELINE recente
(voorlopige) waarden nog corrigeert of aanvult.
Opslag: één CSV per maand in data/metingen/ (tijdstip in UTC).
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REEKSEN = DATA / "reeksen.csv"
METINGEN = DATA / "metingen"
API = "https://geo.irceline.be/sos/api/v1"

CENTRUM = (4.40, 51.22)          # lengte, breedte: centrum Antwerpen
STRAAL_KM = 15
STOFFEN = {                      # IRCEL phenomenon-id -> korte naam
    "8": "NO2",
    "5": "PM10",
    "6001": "PM2.5",
    "391": "BC",
    "7": "O3",
}
HERHAAL_DAGEN = 7
MAX_PER_VERZOEK = 25             # reeksen per bulkverzoek
USER_AGENT = "luchtkwaliteit-antwerpen (portfolio-project; github.com/BadaninaAnna)"


def _get(pad: str):
    req = urllib.request.Request(API + pad, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def _post(pad: str, body: dict):
    req = urllib.request.Request(API + pad, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


# --------------------------------------------------------------------------
# Meetreeksen ontdekken
# --------------------------------------------------------------------------
def ontdek_reeksen() -> pd.DataFrame:
    """Alle actieve reeksen van de gekozen stoffen binnen STRAAL_KM van het centrum."""
    near = urllib.parse.quote(json.dumps(
        {"center": {"type": "Point", "coordinates": list(CENTRUM)}, "radius": STRAAL_KM}))
    grens = datetime.now(timezone.utc) - timedelta(days=30)
    rijen = []
    for st in _get(f"/stations?near={near}"):
        sid = st["properties"]["id"]
        # Labels: "42R804 - Antwerpen (Ring)" of "TOP3M1 -Antwerpen (Neerstraat)"
        code, _, naam = st["properties"]["label"].partition("-")
        lon, lat = st["geometry"]["coordinates"][:2]
        for t in _get(f"/timeseries?station={sid}&expanded=true"):
            fid = t["parameters"]["phenomenon"]["id"]
            laatste = t.get("lastValue", {}).get("timestamp")
            if fid not in STOFFEN or not laatste:
                continue
            if datetime.fromtimestamp(laatste / 1000, timezone.utc) < grens:
                continue          # reeks al > 30 dagen stil: niet meer actief
            rijen.append({"reeks_id": int(t["id"]), "station_id": sid, "station_code": code.strip(),
                          "station": naam.strip().title() if naam.isupper() else naam.strip(),
                          "lat": round(lat, 5), "lon": round(lon, 5), "stof": STOFFEN[fid],
                          "eenheid": "µg/m³"})
        time.sleep(0.2)
    return pd.DataFrame(rijen).sort_values(["stof", "station_code"]).reset_index(drop=True)


# --------------------------------------------------------------------------
# Meetwaarden ophalen
# --------------------------------------------------------------------------
def _iso(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def haal_op(reeks_ids: list[int], van: datetime, tot: datetime) -> pd.DataFrame:
    """Uurwaarden voor alle reeksen in [van, tot], in blokken van max. 1 jaar."""
    delen = []
    for i in range(0, len(reeks_ids), MAX_PER_VERZOEK):
        groep = [str(r) for r in reeks_ids[i:i + MAX_PER_VERZOEK]]
        start = van
        while start < tot:
            einde = min(start + timedelta(days=180), tot)
            antwoord = _post("/timeseries/getData",
                             {"timeseries": groep, "timespan": f"{_iso(start)}/{_iso(einde)}"})
            for rid, inhoud in antwoord.items():
                w = pd.DataFrame(inhoud["values"])
                if w.empty:
                    continue
                w["reeks_id"] = int(rid)
                delen.append(w)
            start = einde
            time.sleep(0.5)
    if not delen:
        return pd.DataFrame(columns=["tijdstip_utc", "reeks_id", "waarde"])
    df = pd.concat(delen, ignore_index=True)
    df["tijdstip_utc"] = pd.to_datetime(df.timestamp, unit="ms", utc=True)
    df = df.rename(columns={"value": "waarde"})[["tijdstip_utc", "reeks_id", "waarde"]]
    # Ontbrekende uren (value = null) bewaren we niet: 'ontbreken' volgt uit het uurrooster.
    df = df.dropna(subset=["waarde"])
    return df.drop_duplicates(["tijdstip_utc", "reeks_id"], keep="last")


# --------------------------------------------------------------------------
# Opslag: één CSV per maand
# --------------------------------------------------------------------------
def lees_metingen(vanaf: str | None = None) -> pd.DataFrame:
    bestanden = sorted(METINGEN.glob("*.csv"))
    if vanaf:
        bestanden = [b for b in bestanden if b.stem >= vanaf[:7]]
    if not bestanden:
        return pd.DataFrame(columns=["tijdstip_utc", "reeks_id", "waarde"])
    df = pd.concat((pd.read_csv(b) for b in bestanden), ignore_index=True)
    df["tijdstip_utc"] = pd.to_datetime(df.tijdstip_utc, utc=True)
    return df


def bewaar(nieuw: pd.DataFrame) -> int:
    METINGEN.mkdir(parents=True, exist_ok=True)
    nieuw = nieuw.assign(maand=nieuw.tijdstip_utc.dt.strftime("%Y-%m"))
    gewijzigd = 0
    for maand, deel in nieuw.groupby("maand"):
        pad = METINGEN / f"{maand}.csv"
        oud = lees_bestand(pad)
        samen = (pd.concat([oud, deel.drop(columns="maand")])
                   .drop_duplicates(["tijdstip_utc", "reeks_id"], keep="last")
                   .sort_values(["tijdstip_utc", "reeks_id"]))
        samen["tijdstip_utc"] = pd.to_datetime(samen.tijdstip_utc, utc=True)
        tekst = samen.assign(tijdstip_utc=samen.tijdstip_utc.dt.strftime("%Y-%m-%dT%H:%MZ")).to_csv(
            index=False, float_format="%.4g", lineterminator="\n")
        if not pad.exists() or pad.read_text("utf-8") != tekst:
            pad.write_text(tekst, "utf-8")
            gewijzigd += 1
    return gewijzigd


def lees_bestand(pad: Path) -> pd.DataFrame:
    if not pad.exists():
        return pd.DataFrame(columns=["tijdstip_utc", "reeks_id", "waarde"])
    df = pd.read_csv(pad)
    df["tijdstip_utc"] = pd.to_datetime(df.tijdstip_utc, utc=True)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ontdek", action="store_true", help="meetreeksen opnieuw zoeken")
    ap.add_argument("--vanaf", help="historiek ophalen vanaf deze datum (JJJJ-MM-DD)")
    args = ap.parse_args()

    if args.ontdek or not REEKSEN.exists():
        r = ontdek_reeksen()
        DATA.mkdir(exist_ok=True)
        r.to_csv(REEKSEN, index=False, lineterminator="\n")
        print(f"{len(r)} reeksen op {r.station_id.nunique()} stations:", r.stof.value_counts().to_dict())

    reeksen = pd.read_csv(REEKSEN)
    nu = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    van = (datetime.fromisoformat(args.vanaf).replace(tzinfo=timezone.utc) if args.vanaf
           else nu - timedelta(days=HERHAAL_DAGEN))
    df = haal_op(reeksen.reeks_id.tolist(), van, nu)
    n = bewaar(df)
    print(f"{len(df):,} waarden opgehaald ({_iso(van)} – {_iso(nu)}), {n} maandbestand(en) bijgewerkt")


if __name__ == "__main__":
    main()
