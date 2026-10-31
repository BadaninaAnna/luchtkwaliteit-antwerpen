"""Bouwt het publieke dashboard docs/index.html (GitHub Pages) uit de opgeslagen metingen.

Gebruik:  python src/dashboard.py
De pagina is statisch: alle cijfers zitten als JSON in de HTML, de grafieken tekent Plotly.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from kwaliteit import (DAGNORM, JAARNORM, JAARNORM_NU, TZ, dagwaarden, jaarwaarden, markeer,
                       status, uurrooster)
from ophalen import REEKSEN, ROOT, lees_metingen

DOCS = ROOT / "docs"
STOFFEN = ["NO2", "PM2.5", "PM10", "BC"]
STOF_NAAM = {"NO2": "Stikstofdioxide (NO₂)", "PM2.5": "Fijnstof PM2,5", "PM10": "Fijnstof PM10",
             "BC": "Black carbon (roet)", "O3": "Ozon (O₃)"}


def _r(x, n=1):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), n)


def bouw_data() -> dict:
    reeksen = pd.read_csv(REEKSEN)
    m = lees_metingen()
    nu = m.tijdstip_utc.max()
    df = markeer(uurrooster(m, reeksen, nu))
    st = status(df, reeksen, nu)
    dag = dagwaarden(df)
    jaar = jaarwaarden(dag)

    # Laatste 7 dagen, uurrooster gedeeld door alle reeksen.
    uren = pd.date_range(nu - pd.Timedelta(days=7), nu, freq="h", tz="UTC")
    week = df[df.tijdstip_utc >= uren[0]].pivot(index="tijdstip_utc", columns="reeks_id", values="waarde")
    week = week.reindex(uren)
    netwerk = (df[df.tijdstip_utc >= uren[0]].groupby(["stof", "tijdstip_utc"]).netwerk.first()
               .unstack("stof").reindex(uren))

    # Maandelijkse trend: gemiddelde van de daggemiddelden over alle stations.
    trend = (dag.assign(maand=dag.datum.dt.to_period("M").dt.to_timestamp())
               .groupby(["stof", "maand"]).daggemiddelde.mean().unstack("stof"))

    jaren = sorted(jaar.jaar.unique())
    reeks_json = []
    for _, r in st.iterrows():
        jr = jaar[jaar.reeks_id == r.reeks_id].set_index("jaar")
        reeks_json.append({
            "id": int(r.reeks_id), "stof": r.stof, "code": r.station_code,
            "station": f"{r.station} · {r.station_code}", "lat": r.lat, "lon": r.lon,
            "status": r.status, "reden": r.reden,
            "laatste": r.laatste_meting.tz_convert(TZ).strftime("%d-%m %H:%M") if pd.notna(r.laatste_meting) else None,
            "waarde": _r(r.laatste_waarde, 2 if r.stof == "BC" else 1),
            "vol7": _r(r.volledigheid_7d, 3), "vol30": _r(r.volledigheid_30d, 3),
            "vlak30": int(r.vlakke_uren_30d), "piek30": int(r.lokale_pieken_30d),
            "jaar": {str(j): {"gem": _r(jr.at[j, "jaargemiddelde"], 2 if r.stof == "BC" else 1),
                              "dagen": int(jr.at[j, "geldige_dagen"]),
                              "who": int(jr.at[j, "dagen_boven_who"]),
                              "eu": int(jr.at[j, "dagen_boven_eu_2030"])}
                     for j in jaren if j in jr.index},
            "week": [_r(v, 2) for v in week[r.reeks_id].to_numpy()] if r.reeks_id in week else [],
        })

    nu_lokaal = nu.tz_convert(TZ)
    return {
        "bijgewerkt": pd.Timestamp.now(tz=TZ).strftime("%d-%m-%Y %H:%M"),
        "laatste_uur": nu_lokaal.strftime("%d-%m-%Y %H:%M"),
        "jaar_nu": int(nu_lokaal.year),
        "uren": [u.tz_convert(TZ).strftime("%Y-%m-%d %H:%M") for u in uren],
        "netwerk": {s: [_r(v, 2) for v in netwerk[s].to_numpy()] for s in netwerk.columns},
        "trend": {"maanden": [d.strftime("%Y-%m") for d in trend.index],
                  **{s: [_r(v, 2) for v in trend[s].to_numpy()] for s in trend.columns}},
        "reeksen": reeks_json,
        "stoffen": STOFFEN,
        "stofnaam": STOF_NAAM,
        "dagnorm": DAGNORM, "jaarnorm": JAARNORM, "jaarnorm_nu": JAARNORM_NU,
        "telling": st.status.value_counts().to_dict(),
    }


def main():
    data = bouw_data()
    sjabloon = (ROOT / "src" / "sjabloon.html").read_text("utf-8")
    html = sjabloon.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    DOCS.mkdir(exist_ok=True)
    (DOCS / "index.html").write_text(html, "utf-8")
    print(f"docs/index.html: {len(html) / 1024:.0f} kB, laatste uur {data['laatste_uur']}, status {data['telling']}")


if __name__ == "__main__":
    main()
