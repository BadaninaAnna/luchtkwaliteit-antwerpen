"""Datakwaliteitscontrole en toetsing aan normen voor de meetreeksen.

Controles per uurwaarde (zie README voor de motivatie):
  - ontbrekend   : geen waarde in het uurrooster
  - vlak         : ≥ VLAK_UREN opeenvolgende identieke waarden (vastgelopen meting)
  - lokale piek  : waarde > PIEK_FACTOR × netwerkmediaan én > PIEK_MARGE erboven
                   (een regionale piek, zoals vuurwerk op nieuwjaar, zit ook in de mediaan
                   en wordt dus niet gemarkeerd)
  - verschuiving : de verhouding reeks / netwerkmediaan (7-daagse mediaan) wijkt > DRIFT_GRENS
                   af van haar eigen 90-daagse niveau: mogelijke kalibratie- of driftfout
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TZ = "Europe/Brussels"
VLAK_UREN = 24
PIEK_FACTOR = 5
PIEK_MARGE = {"PM10": 100, "PM2.5": 50, "NO2": 100, "BC": 5, "O3": 100}
DRIFT_GRENS = 0.40
STORING_UREN = 6

# Normen in µg/m³: (WHO-richtlijn 2021, EU-grenswaarde vanaf 2030 (Richtlijn 2024/2881))
DAGNORM = {"PM2.5": (15, 25), "PM10": (45, 45), "NO2": (25, 50)}
JAARNORM = {"PM2.5": (5, 10), "PM10": (15, 20), "NO2": (10, 20)}
# Huidige EU-jaargrenswaarde (Richtlijn 2008/50/EG)
JAARNORM_NU = {"PM2.5": 25, "PM10": 40, "NO2": 40}


def uurrooster(metingen: pd.DataFrame, reeksen: pd.DataFrame, tot: pd.Timestamp) -> pd.DataFrame:
    """Volledig uurrooster per reeks (vanaf de eerste meting), met NaN voor ontbrekende uren."""
    delen = []
    for rid, g in metingen.groupby("reeks_id"):
        uren = pd.date_range(g.tijdstip_utc.min(), tot, freq="h", tz="UTC")
        s = g.set_index("tijdstip_utc").waarde.reindex(uren)
        delen.append(pd.DataFrame({"tijdstip_utc": uren, "reeks_id": rid, "waarde": s.to_numpy()}))
    df = pd.concat(delen, ignore_index=True)
    return df.merge(reeksen[["reeks_id", "stof"]], on="reeks_id")


def markeer(df: pd.DataFrame) -> pd.DataFrame:
    """Voegt kwaliteitsvlaggen toe aan het uurrooster."""
    df = df.sort_values(["reeks_id", "tijdstip_utc"]).copy()
    df["ontbrekend"] = df.waarde.isna()

    # Vlakke reeksen: lengte van elke run identieke (niet-lege) waarden.
    nieuwe_run = (df.waarde != df.groupby("reeks_id").waarde.shift()) | df.waarde.isna()
    run_id = nieuwe_run.cumsum()
    df["vlak"] = (df.groupby(run_id).waarde.transform("size") >= VLAK_UREN) & df.waarde.notna()

    # Netwerkmediaan per stof en uur (zonder vlakke waarden).
    geldig = df.waarde.where(~df.vlak)
    df["netwerk"] = geldig.groupby([df.stof, df.tijdstip_utc]).transform("median")
    marge = df.stof.map(PIEK_MARGE)
    df["lokale_piek"] = (df.waarde > PIEK_FACTOR * df.netwerk) & (df.waarde - df.netwerk > marge)

    # Verschuiving t.o.v. het netwerk.
    verh = (geldig / df.netwerk).replace([np.inf, -np.inf], np.nan)
    g = verh.groupby(df.reeks_id)
    kort = g.transform(lambda s: s.rolling(24 * 7, min_periods=24 * 4).median())
    lang = g.transform(lambda s: s.rolling(24 * 90, min_periods=24 * 30).median())
    df["verschuiving"] = (kort / lang - 1).abs() > DRIFT_GRENS
    return df


def status(df: pd.DataFrame, reeksen: pd.DataFrame, nu: pd.Timestamp) -> pd.DataFrame:
    """Actuele status per reeks: OK / Waarschuwing / Storing, met de reden."""
    rijen = []
    for rid, g in df.groupby("reeks_id"):
        g = g.set_index("tijdstip_utc")
        laatste = g.waarde.last_valid_index()
        week = g.loc[nu - pd.Timedelta(days=7):]
        dag = g.loc[nu - pd.Timedelta(hours=24):]
        maand = g.loc[nu - pd.Timedelta(days=30):]
        uren_stil = (nu - laatste).total_seconds() / 3600 if laatste is not None else np.inf
        volledig_7d = week.waarde.notna().mean()
        redenen = []
        if uren_stil > STORING_UREN:
            niveau = "Storing"
            redenen.append(f"geen data sinds {uren_stil / 24:.0f} dagen" if uren_stil >= 48
                           else f"geen data sinds {uren_stil:.0f} uur")
        else:
            niveau = "OK"
            if dag.vlak.any():
                redenen.append("vlakke meting (vastgelopen?)")
            if volledig_7d < 0.75:
                redenen.append(f"volledigheid 7 dagen {volledig_7d:.0%}")
            if dag.lokale_piek.any():
                redenen.append("lokale piek")
            if week.verschuiving.sum() >= 72:      # minstens 3 dagen aanhoudend
                redenen.append("verschuiving t.o.v. netwerk")
            if redenen:
                niveau = "Waarschuwing"
        rijen.append({
            "reeks_id": rid, "status": niveau, "reden": "; ".join(redenen),
            "laatste_meting": laatste, "laatste_waarde": g.waarde.get(laatste) if laatste is not None else None,
            "volledigheid_7d": volledig_7d, "volledigheid_30d": maand.waarde.notna().mean(),
            "vlakke_uren_30d": int(maand.vlak.sum()), "lokale_pieken_30d": int(maand.lokale_piek.sum()),
        })
    s = pd.DataFrame(rijen)
    return reeksen.merge(s, on="reeks_id")


def dagwaarden(df: pd.DataFrame) -> pd.DataFrame:
    """Daggemiddelden (lokale tijd) met minstens 18 geldige uren (75 %)."""
    d = df[~df.vlak].assign(datum=df.tijdstip_utc.dt.tz_convert(TZ).dt.date)
    agg = d.groupby(["reeks_id", "stof", "datum"]).waarde.agg(["mean", "count"]).reset_index()
    agg = agg[agg["count"] >= 18].rename(columns={"mean": "daggemiddelde", "count": "uren"})
    agg["datum"] = pd.to_datetime(agg.datum)
    agg["who"] = agg.stof.map(lambda s: DAGNORM.get(s, (np.nan,))[0])
    agg["eu_2030"] = agg.stof.map(lambda s: DAGNORM.get(s, (np.nan, np.nan))[1])
    agg["boven_who"] = agg.daggemiddelde > agg.who
    agg["boven_eu_2030"] = agg.daggemiddelde > agg.eu_2030
    return agg


def jaarwaarden(dag: pd.DataFrame) -> pd.DataFrame:
    """Jaargemiddelde en aantal overschrijdingsdagen per reeks en kalenderjaar."""
    j = dag.assign(jaar=dag.datum.dt.year).groupby(["reeks_id", "stof", "jaar"]).agg(
        jaargemiddelde=("daggemiddelde", "mean"), geldige_dagen=("daggemiddelde", "size"),
        dagen_boven_who=("boven_who", "sum"), dagen_boven_eu_2030=("boven_eu_2030", "sum")).reset_index()
    j["who_jaar"] = j.stof.map(lambda s: JAARNORM.get(s, (np.nan,))[0])
    j["eu_2030_jaar"] = j.stof.map(lambda s: JAARNORM.get(s, (np.nan, np.nan))[1])
    j["eu_nu_jaar"] = j.stof.map(JAARNORM_NU)
    return j
