"""Bouwt het Power BI-project (PBIP) als code: semantisch model in TMDL + rapport in PBIR.

Gebruik:  python src/bouw_pbip.py
Uitvoer:  powerbi/Luchtkwaliteit.pbip  (+ .SemanticModel/ en .Report/)

Het model leest de data rechtstreeks van GitHub (raw.githubusercontent.com). De workflow
werkt die bestanden elk uur bij, dus Vernieuwen in Power BI haalt altijd de laatste metingen op.
"""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PBI = ROOT / "powerbi"
NAAM = "Luchtkwaliteit"
DATA_URL = "https://raw.githubusercontent.com/BadaninaAnna/luchtkwaliteit-antwerpen/main/data/"
T = "\t"


def lt() -> str:
    return str(uuid.uuid4())


# ==========================================================================
# 1. Semantisch model (TMDL)
# ==========================================================================
def csv_bron(pad: str, types: list[tuple[str, str]]) -> str:
    """Power Query: CSV van GitHub lezen met vaste locale (punt als decimaalteken)."""
    t = ", ".join(f'{{"{k}", {v}}}' for k, v in types)
    return (f'let\n'
            f'    Inhoud = Csv.Document ( Web.Contents ( DataUrl & "{pad}" ), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv] ),\n'
            f'    Koppen = Table.PromoteHeaders ( Inhoud, [PromoteAllScalars = true] ),\n'
            f'    Types = Table.TransformColumnTypes ( Koppen, {{{t}}}, "en-US" )\n'
            f'in\n    Types')


UUR_M = """let
    Nu = DateTime.LocalNow (),
    // vorige en huidige maand: genoeg voor de laatste 7 dagen, ook vlak na een maandwissel
    Maanden = List.Transform ( { 1, 0 }, each Date.ToText ( Date.AddMonths ( Date.From ( Nu ), - _ ), "yyyy-MM", "en-US" ) ),
    Lees = ( m as text ) as table =>
        Table.PromoteHeaders ( Csv.Document ( Web.Contents ( DataUrl & "metingen/" & m & ".csv" ), [Delimiter = ",", Encoding = 65001] ), [PromoteAllScalars = true] ),
    Samen = Table.Combine ( List.Transform ( Maanden, Lees ) ),
    Types = Table.TransformColumnTypes ( Samen, { { "reeks_id", Int64.Type }, { "waarde", type number } }, "en-US" ),
    Tijd = Table.AddColumn ( Types, "tijdstip", each DateTimeZone.RemoveZone ( DateTimeZone.ToLocal ( DateTimeZone.FromText ( Text.Replace ( [tijdstip_utc], "Z", ":00+00:00" ) ) ) ), type datetime ),
    Datum = Table.AddColumn ( Tijd, "datum", each DateTime.Date ( [tijdstip] ), type date ),
    UrenGeleden = Table.AddColumn ( Datum, "uren_geleden", each Duration.TotalHours ( Nu - [tijdstip] ), type number ),
    Resultaat = Table.RemoveColumns ( UrenGeleden, { "tijdstip_utc" } )
in
    Resultaat"""

# naam -> (M-expressie, kolommen [(naam, dataType, summarizeBy, formatString, extra)])
TABELLEN = {
    "uurwaarden": (UUR_M, [
        ("reeks_id", "int64", "none", "0", {}),
        ("waarde", "double", "none", "0.0", {}),
        ("tijdstip", "dateTime", "none", "dd-mm-yyyy hh:nn", {}),
        ("datum", "dateTime", "none", "dd-mm-yyyy", {}),
        ("uren_geleden", "double", "none", "0", {}),
    ]),
    "dagwaarden": (csv_bron("powerbi/dagwaarden.csv", [
        ("reeks_id", "Int64.Type"), ("stof", "type text"), ("datum", "type date"),
        ("daggemiddelde", "type number"), ("uren", "Int64.Type"),
        ("boven_who", "Int64.Type"), ("boven_eu_2030", "Int64.Type")]), [
        ("reeks_id", "int64", "none", "0", {}),
        ("stof", "string", "none", None, {}),
        ("datum", "dateTime", "none", "dd-mm-yyyy", {}),
        ("daggemiddelde", "double", "average", "0.0", {}),
        ("uren", "int64", "sum", "0", {}),
        ("boven_who", "int64", "sum", "0", {}),
        ("boven_eu_2030", "int64", "sum", "0", {}),
    ]),
    "reeksen": (csv_bron("powerbi/reeksen.csv", [
        ("reeks_id", "Int64.Type"), ("station_id", "Int64.Type"), ("station_code", "type text"),
        ("station", "type text"), ("lat", "type number"), ("lon", "type number"), ("stof", "type text"),
        ("eenheid", "type text"), ("status", "type text"), ("reden", "type text"),
        ("laatste_meting", "type datetime"), ("laatste_waarde", "type number"),
        ("volledigheid_7d", "type number"), ("volledigheid_30d", "type number"),
        ("vlakke_uren_30d", "Int64.Type"), ("lokale_pieken_30d", "Int64.Type"),
        ("station_label", "type text"), ("status_label", "type text"), ("status_volgorde", "Int64.Type")]), [
        ("reeks_id", "int64", "none", "0", {}),
        ("station_id", "int64", "none", "0", {}),
        ("station_code", "string", "none", None, {}),
        ("station", "string", "none", None, {}),
        ("lat", "double", "none", "0.00000", {"dataCategory": "Latitude"}),
        ("lon", "double", "none", "0.00000", {"dataCategory": "Longitude"}),
        ("stof", "string", "none", None, {}),
        ("eenheid", "string", "none", None, {}),
        ("status", "string", "none", None, {}),
        ("reden", "string", "none", None, {}),
        ("laatste_meting", "dateTime", "none", "dd-mm-yyyy hh:nn", {}),
        ("laatste_waarde", "double", "none", "0.0", {}),
        ("volledigheid_7d", "double", "none", "0%", {}),
        ("volledigheid_30d", "double", "none", "0%", {}),
        ("vlakke_uren_30d", "int64", "none", "0", {}),
        ("lokale_pieken_30d", "int64", "none", "0", {}),
        ("station_label", "string", "none", None, {}),
        ("status_label", "string", "none", None, {"sortByColumn": "status_volgorde"}),
        ("status_volgorde", "int64", "none", "0", {}),
    ]),
    "stoffen": (csv_bron("powerbi/stoffen.csv", [
        ("stof", "type text"), ("naam", "type text"), ("who_dag", "type number"), ("eu_2030_dag", "type number"),
        ("who_jaar", "type number"), ("eu_2030_jaar", "type number"), ("eu_nu_jaar", "type number"),
        ("volgorde", "Int64.Type")]), [
        ("stof", "string", "none", None, {}),
        ("naam", "string", "none", None, {"sortByColumn": "volgorde"}),
        ("who_dag", "double", "none", "0", {}),
        ("eu_2030_dag", "double", "none", "0", {}),
        ("who_jaar", "double", "none", "0", {}),
        ("eu_2030_jaar", "double", "none", "0", {}),
        ("eu_nu_jaar", "double", "none", "0", {}),
        ("volgorde", "int64", "none", "0", {}),
    ]),
    "meta": (csv_bron("powerbi/meta.csv", [("laatste_meting", "type datetime"), ("bijgewerkt", "type datetime")]), [
        ("laatste_meting", "dateTime", "none", "dd-mm-yyyy hh:nn", {}),
        ("bijgewerkt", "dateTime", "none", "dd-mm-yyyy hh:nn", {}),
    ]),
}

# (tabel, naam, DAX, formatString, displayFolder)
MEASURES = [
    ("uurwaarden", "Netwerkmediaan", "MEDIAN ( uurwaarden[waarde] )", "0.0", "Uurwaarden"),
    ("uurwaarden", "Netwerkmediaan laatste uur",
     "VAR t = CALCULATE ( MAX ( uurwaarden[tijdstip] ), REMOVEFILTERS ( Datum ) )\n"
     "RETURN CALCULATE ( MEDIAN ( uurwaarden[waarde] ), REMOVEFILTERS ( Datum ), uurwaarden[tijdstip] = t )",
     "0.0", "Uurwaarden"),
    ("dagwaarden", "Gemiddelde", "AVERAGE ( dagwaarden[daggemiddelde] )", "0.0", "Normen"),
    ("dagwaarden", "Stationsdagen boven WHO", "SUM ( dagwaarden[boven_who] )", "#,0", "Normen"),
    ("dagwaarden", "Aandeel dagen boven WHO",
     "DIVIDE ( SUM ( dagwaarden[boven_who] ), COUNTROWS ( dagwaarden ) )", "0%", "Normen"),
    ("dagwaarden", "Aandeel dagen boven EU 2030",
     "DIVIDE ( SUM ( dagwaarden[boven_eu_2030] ), COUNTROWS ( dagwaarden ) )", "0%", "Normen"),
    ("stoffen", "WHO-dagrichtlijn", "SELECTEDVALUE ( stoffen[who_dag] )", "0", "Normen"),
    ("stoffen", "WHO-jaarrichtlijn", "SELECTEDVALUE ( stoffen[who_jaar] )", "0", "Normen"),
    ("stoffen", "EU 2030-jaargrens", "SELECTEDVALUE ( stoffen[eu_2030_jaar] )", "0", "Normen"),
    ("reeksen", "Meetreeksen", "COUNTROWS ( reeksen )", "0", "Datakwaliteit"),
    ("reeksen", "Reeksen OK", "CALCULATE ( COUNTROWS ( reeksen ), reeksen[status] = \"OK\" ) + 0", "0", "Datakwaliteit"),
    ("reeksen", "Reeksen met waarschuwing",
     "CALCULATE ( COUNTROWS ( reeksen ), reeksen[status] = \"Waarschuwing\" ) + 0", "0", "Datakwaliteit"),
    ("reeksen", "Reeksen in storing",
     "CALCULATE ( COUNTROWS ( reeksen ), reeksen[status] = \"Storing\" ) + 0", "0", "Datakwaliteit"),
    ("reeksen", "Gem. volledigheid 30 dagen", "AVERAGE ( reeksen[volledigheid_30d] )", "0.0%", "Datakwaliteit"),
    ("meta", "Laatste meting", "MAX ( meta[laatste_meting] )", "dd-mm-yyyy hh:nn", "Info"),
]

DATUM_DAX = """VAR basis = CALENDAR ( DATE ( 2025, 1, 1 ), TODAY () )
RETURN
    ADDCOLUMNS (
        basis,
        "Jaar", YEAR ( [Date] ),
        "Maand", FORMAT ( [Date], "yyyy-mm" ),
        "MaandSort", YEAR ( [Date] ) * 100 + MONTH ( [Date] )
    )"""
DATUM_KOLOMMEN = [
    ("Date", "dateTime", "dd-mm-yyyy", {"isKey": None}),
    ("Jaar", "int64", "0", {}),
    ("Maand", "string", None, {"sortByColumn": "MaandSort"}),
    ("MaandSort", "int64", "0", {}),
]

RELATIES = [
    ("uurwaarden", "reeks_id", "reeksen", "reeks_id"),
    ("dagwaarden", "reeks_id", "reeksen", "reeks_id"),
    ("reeksen", "stof", "stoffen", "stof"),
    ("dagwaarden", "datum", "Datum", "Date"),
    ("uurwaarden", "datum", "Datum", "Date"),
]


def naam(n: str) -> str:
    return n if n.replace("_", "").isalnum() else "'" + n.replace("'", "''") + "'"


def inspring(tekst: str, niveau: int) -> str:
    return "\n".join(T * niveau + r for r in tekst.splitlines())


def tmdl_measure(m) -> str:
    _, n, dax, fmt, map_ = m
    kop = f"{T}measure {naam(n)} =\n{inspring(dax, 3)}" if "\n" in dax else f"{T}measure {naam(n)} = {dax}"
    return f"{kop}\n{T*2}formatString: {fmt}\n{T*2}displayFolder: {map_}\n{T*2}lineageTag: {lt()}\n"


def tmdl_kolom(n, dt, summ, fmt, extra, berekend=False) -> str:
    r = [f"{T}column {naam(n)}"]
    if berekend:
        r.append(f"{T*2}isNameInferred")
    r.append(f"{T*2}dataType: {dt}")
    if berekend:
        r.append(f"{T*2}isDataTypeInferred")
    for k, v in extra.items():
        r.append(f"{T*2}{k}" if v is None else f"{T*2}{k}: {v}")
    if fmt:
        r.append(f"{T*2}formatString: {fmt}")
    r += [f"{T*2}lineageTag: {lt()}", f"{T*2}summarizeBy: {summ}",
          f"{T*2}sourceColumn: {'[' + n + ']' if berekend else n}", "",
          f"{T*2}annotation SummarizationSetBy = Automatic"]
    return "\n".join(r) + "\n"


def tmdl_tabel(t: str) -> str:
    m, kolommen = TABELLEN[t]
    delen = [f"table {t}\n{T}lineageTag: {lt()}\n"]
    delen += [tmdl_measure(x) for x in MEASURES if x[0] == t]
    delen += [tmdl_kolom(*k) for k in kolommen]
    delen.append(f"{T}partition {t} = m\n{T*2}mode: import\n{T*2}source =\n{inspring(m, 3)}\n")
    delen.append(f"{T}annotation PBI_ResultType = Table\n")
    return "\n".join(delen)


def tmdl_datum() -> str:
    delen = [f"table Datum\n{T}dataCategory: Time\n{T}lineageTag: {lt()}\n"]
    delen += [tmdl_kolom(n, dt, "none", fmt, extra, berekend=True) for n, dt, fmt, extra in DATUM_KOLOMMEN]
    delen.append(f"{T}partition Datum = calculated\n{T*2}mode: import\n{T*2}source =\n{inspring(DATUM_DAX, 3)}\n")
    return "\n".join(delen)


def schrijf_model(map_: Path):
    d = map_ / "definition"
    (d / "tables").mkdir(parents=True)
    (map_ / "definition.pbism").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.2", "settings": {}}, indent=2), "utf-8")
    (d / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1600\n", "utf-8")
    alle = ["Datum", *TABELLEN]
    (d / "model.tmdl").write_text(
        "model Model\n\tculture: en-US\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
        "\tsourceQueryCulture: en-US\n\tdataAccessOptions\n\t\tlegacyRedirects\n\t\treturnErrorValuesAsNull\n\n"
        f"annotation PBI_QueryOrder = {json.dumps(['DataUrl', *TABELLEN])}\n\n"
        "annotation __PBI_TimeIntelligenceEnabled = 0\n\n"
        + "".join(f"ref table {t}\n" for t in alle), "utf-8")
    (d / "expressions.tmdl").write_text(
        f'expression DataUrl = "{DATA_URL}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n'
        f"\tlineageTag: {lt()}\n\n\tannotation PBI_ResultType = Text\n", "utf-8")
    (d / "relationships.tmdl").write_text("\n".join(
        f"relationship {lt()}\n\tfromColumn: {a}.{b}\n\ttoColumn: {c}.{e}\n" for a, b, c, e in RELATIES), "utf-8")
    for t in TABELLEN:
        (d / "tables" / f"{t}.tmdl").write_text(tmdl_tabel(t), "utf-8")
    (d / "tables" / "Datum.tmdl").write_text(tmdl_datum(), "utf-8")


# ==========================================================================
# 2. Rapport (PBIR)
# ==========================================================================
VC = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.4.0/schema.json"
PG = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json"
PM = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json"
AGG = {0: "Sum", 1: "Avg", 3: "Min", 4: "Max"}


def nid():
    return uuid.uuid4().hex[:20]


def lit(v):
    return {"expr": {"Literal": {"Value": v}}}


def tekst(s):
    return lit("'" + s.replace("'", "''") + "'")


def col(e, p):
    return {"Column": {"Expression": {"SourceRef": {"Entity": e}}, "Property": p}}


def meas(e, p):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": e}}, "Property": p}}


def agg(e, p, f):
    return {"Aggregation": {"Expression": col(e, p), "Function": f}}


def proj(field, display=None, fmt=None, active=None):
    if "Measure" in field:
        m = field["Measure"]
        ref = f"{m['Expression']['SourceRef']['Entity']}.{m['Property']}"
    elif "Aggregation" in field:
        c = field["Aggregation"]["Expression"]["Column"]
        ref = f"{AGG[field['Aggregation']['Function']]}({c['Expression']['SourceRef']['Entity']}.{c['Property']})"
    else:
        ref = f"{field['Column']['Expression']['SourceRef']['Entity']}.{field['Column']['Property']}"
    p = {"field": field, "queryRef": ref}
    if display:
        p["displayName"] = display
    if fmt:
        p["format"] = fmt
    if active is not None:
        p["active"] = active
    return p


def container(naam_, x, y, w, h, visual, filters=None):
    c = {"$schema": VC, "name": naam_,
         "position": {"x": x, "y": y, "z": 0, "width": w, "height": h, "tabOrder": 0}, "visual": visual}
    if filters:
        c["filterConfig"] = {"filters": filters}
    return c


def titel(s):
    return {"title": [{"properties": {"show": lit("true"), "text": tekst(s)}}],
            "subTitle": [{"properties": {"show": lit("false")}}]}


def visual(vtype, roles, titeltekst=None, objects=None, sort=None, **extra):
    v = {"visualType": vtype,
         "query": {"queryState": {r: {"projections": p} for r, p in roles.items()}},
         "drillFilterOtherVisuals": True}
    if sort:
        v["query"]["sortDefinition"] = {"sort": sort, "isDefaultSort": False}
    if objects:
        v["objects"] = objects
    if titeltekst:
        v["visualContainerObjects"] = titel(titeltekst)
    v.update(extra)
    return v


def tekstvak(x, y, w, h, regels):
    par = [{"textRuns": [{"value": t, "textStyle": {"fontSize": f"{g}pt", **({"fontWeight": "bold"} if vet else {})}}]}
           for t, g, vet in regels]
    return container(nid(), x, y, w, h, {"visualType": "textbox",
                                         "objects": {"general": [{"properties": {"paragraphs": par}}]},
                                         "drillFilterOtherVisuals": True})


def in_filter(entity, prop, waarden, alias="f"):
    return {"Version": 2, "From": [{"Name": alias, "Entity": entity, "Type": 0}],
            "Where": [{"Condition": {"In": {
                "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": alias}}, "Property": prop}}],
                "Values": [[{"Literal": {"Value": w}}] for w in waarden]}}}]}


def filter_max(entity, prop, waarde):
    return {"name": nid(), "field": col(entity, prop), "type": "Advanced",
            "filter": {"Version": 2, "From": [{"Name": "f", "Entity": entity, "Type": 0}],
                       "Where": [{"Condition": {"Comparison": {
                           "ComparisonKind": 4,
                           "Left": {"Column": {"Expression": {"SourceRef": {"Source": "f"}}, "Property": prop}},
                           "Right": {"Literal": {"Value": waarde}}}}}]}}


def slicer(x, y, w, h, entity, prop, kop, standaard, groep):
    return container(nid(), x, y, w, h, visual(
        "slicer", {"Values": [proj(col(entity, prop), active=True)]}, kop,
        objects={"data": [{"properties": {"mode": tekst("Basic")}}],
                 "selection": [{"properties": {"singleSelect": lit("true")}}],
                 "general": [{"properties": {"filter": {"filter": in_filter(entity, prop, [standaard], "s")}}}]},
        syncGroup={"groupName": groep, "fieldChanges": True, "filterChanges": True}))


def kaart(x, y, w, h, tabel, maat, kop, fmt=None):
    return container(nid(), x, y, w, h, visual(
        "card", {"Values": [proj(meas(tabel, maat), fmt=fmt)]}, kop,
        objects={"categoryLabels": [{"properties": {"show": lit("false")}}]}))


def breedtes(paren):
    return [{"properties": {"value": lit(f"{b}D")}, "selector": {"metadata": q}} for q, b in paren]


LABELS = {"labels": [{"properties": {"show": lit("true")}}]}
RECHT = {"lineStyles": [{"properties": {"lineChartType": tekst("straight")}}]}
NO2 = "'Stikstofdioxide (NO₂)'"


def kop(t, sub, w=1300):
    return tekstvak(40, 20, w, 130, [(t, 28, True), (sub, 16, False)])


def stofslicer():
    return slicer(1380, 20, 500, 150, "stoffen", "naam", "Stof", NO2, "stof")


def paginas():
    p = {}
    # ------------------------------------------------------------------ Nu
    p["Nu"] = ([
        kop("Luchtkwaliteit Antwerpen: live",
            "37 officiële meetstations · data van IRCEL-CELINE, elk uur bijgewerkt via GitHub Actions · klik op Vernieuwen voor de laatste metingen"),
        stofslicer(),
        kaart(40, 190, 440, 170, "uurwaarden", "Netwerkmediaan laatste uur", "Netwerkmediaan laatste uur (µg/m³)"),
        kaart(500, 190, 440, 170, "stoffen", "WHO-dagrichtlijn", "WHO-dagrichtlijn (µg/m³)"),
        kaart(960, 190, 440, 170, "meta", "Laatste meting", "Laatste meting"),
        kaart(1420, 190, 460, 170, "reeksen", "Meetreeksen", "Meetreeksen voor deze stof"),
        container(nid(), 40, 380, 1180, 670, visual(
            "lineChart",
            {"Category": [proj(col("uurwaarden", "tijdstip"), "Tijdstip", active=True)],
             "Y": [proj(meas("uurwaarden", "Netwerkmediaan"), "Netwerkmediaan (µg/m³)")]},
            "Netwerkmediaan per uur, laatste 7 dagen", objects=RECHT),
            filters=[filter_max("uurwaarden", "uren_geleden", "168D")]),
        container(nid(), 1260, 380, 620, 670, visual(
            "clusteredBarChart",
            {"Category": [proj(col("reeksen", "station_label"), "Station", active=True)],
             "Y": [proj(agg("reeksen", "laatste_waarde", 4), "Laatste waarde (µg/m³)", "0.0")]},
            "Laatste uurwaarde per station", objects=LABELS,
            sort=[{"field": agg("reeksen", "laatste_waarde", 4), "direction": "Descending"}])),
    ], [])

    # -------------------------------------------------------------- Normen
    jaar = slicer(1380, 190, 500, 170, "Datum", "Jaar", "Jaar", "2026L", "jaar")
    p["Normen"] = ([
        kop("Normen: WHO en EU 2030", "Daggemiddelden met minstens 18 geldige uren, getoetst aan de WHO-richtlijnen 2021 en de EU-grenswaarden vanaf 2030"),
        stofslicer(),
        jaar,
        kaart(40, 190, 320, 170, "stoffen", "WHO-jaarrichtlijn", "WHO-jaarrichtlijn (µg/m³)"),
        kaart(380, 190, 320, 170, "stoffen", "EU 2030-jaargrens", "EU 2030-jaargrens (µg/m³)"),
        kaart(720, 190, 320, 170, "dagwaarden", "Aandeel dagen boven WHO", "Stationsdagen boven WHO-dagrichtlijn"),
        kaart(1060, 190, 300, 170, "dagwaarden", "Aandeel dagen boven EU 2030", "Boven EU 2030-daggrens"),
        container(nid(), 40, 380, 900, 670, visual(
            "clusteredBarChart",
            {"Category": [proj(col("reeksen", "station_label"), "Station", active=True)],
             "Y": [proj(meas("dagwaarden", "Gemiddelde"), "Gemiddelde (µg/m³)")]},
            "Gemiddelde per station in het gekozen jaar", objects=LABELS,
            sort=[{"field": meas("dagwaarden", "Gemiddelde"), "direction": "Descending"}])),
        container(nid(), 980, 380, 900, 670, visual(
            "clusteredColumnChart",
            {"Category": [proj(col("Datum", "Maand"), "Maand", active=True)],
             "Y": [proj(meas("dagwaarden", "Stationsdagen boven WHO"), "Stationsdagen boven WHO")]},
            "Overschrijdingen van de WHO-dagrichtlijn per maand", objects=LABELS,
            sort=[{"field": col("Datum", "Maand"), "direction": "Ascending"}])),
    ], [])

    # --------------------------------------------------------------- Trend
    p["Trend"] = ([
        kop("Trend per maand en per station", "Maandgemiddelde van de daggemiddelden, sinds januari 2025"),
        stofslicer(),
        container(nid(), 40, 190, 1840, 330, visual(
            "lineChart",
            {"Category": [proj(col("Datum", "Maand"), "Maand", active=True)],
             "Y": [proj(meas("dagwaarden", "Gemiddelde"), "Gemiddelde (µg/m³)")]},
            "Maandgemiddelde over alle stations",
            objects={"lineStyles": [{"properties": {"showMarker": lit("true"), "lineChartType": tekst("straight")}}]},
            sort=[{"field": col("Datum", "Maand"), "direction": "Ascending"}])),
        container(nid(), 40, 540, 1840, 510, visual(
            "pivotTable",
            {"Rows": [proj(col("reeksen", "station_label"), "Station", active=True)],
             "Columns": [proj(col("Datum", "Maand"), "Maand", active=True)],
             "Values": [proj(meas("dagwaarden", "Gemiddelde"), "Gemiddelde", "0")]},
            "Maandgemiddelde per station (µg/m³)",
            objects={"subTotals": [{"properties": {"rowSubtotals": lit("false"), "columnSubtotals": lit("false")}}],
                     "values": [{"properties": {"backColor": {"solid": {"color": {"expr": {"FillRule": {
                         "Input": meas("dagwaarden", "Gemiddelde"),
                         "FillRule": {"linearGradient2": {
                             "min": {"color": {"Literal": {"Value": "'#fcfcfb'"}}},
                             "max": {"color": {"Literal": {"Value": "'#2a78d6'"}}},
                             "nullColoringStrategy": {"strategy": {"Literal": {"Value": "'noColor'"}}}}}}}}}}},
                         "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}]}}]})),
    ], [])

    # -------------------------------------------------------- Datakwaliteit
    p["Datakwaliteit"] = ([
        kop("Datakwaliteit van het meetnet",
            "Automatische controle per meetreeks: storing (> 6 u geen data), vastgelopen meting (≥ 24 identieke uurwaarden), lokale pieken en verschuiving t.o.v. het netwerk",
            1840),
        kaart(40, 190, 440, 170, "reeksen", "Reeksen OK", "✔ OK"),
        kaart(500, 190, 440, 170, "reeksen", "Reeksen met waarschuwing", "⚠ Waarschuwing"),
        kaart(960, 190, 440, 170, "reeksen", "Reeksen in storing", "✖ Storing"),
        kaart(1420, 190, 460, 170, "reeksen", "Gem. volledigheid 30 dagen", "Gemiddelde volledigheid 30 dagen"),
        container(nid(), 40, 380, 1840, 670, visual(
            "tableEx",
            {"Values": [proj(col("reeksen", "status_label"), "Status"),
                        proj(col("reeksen", "station_label"), "Station"),
                        proj(col("reeksen", "stof"), "Stof"),
                        proj(col("reeksen", "laatste_meting"), "Laatste meting"),
                        proj(col("reeksen", "volledigheid_7d"), "Volledig 7 d", "0%"),
                        proj(col("reeksen", "volledigheid_30d"), "Volledig 30 d", "0%"),
                        proj(col("reeksen", "vlakke_uren_30d"), "Vlakke uren 30 d"),
                        proj(col("reeksen", "lokale_pieken_30d"), "Lokale pieken 30 d"),
                        proj(col("reeksen", "reden"), "Opmerking")]},
            "Alle meetreeksen (problemen eerst)",
            objects={"total": [{"properties": {"totals": lit("false")}}],
                     "columnWidth": breedtes([("reeksen.status_label", 190), ("reeksen.station_label", 380),
                                              ("reeksen.stof", 90), ("reeksen.laatste_meting", 190),
                                              ("reeksen.volledigheid_7d", 130), ("reeksen.volledigheid_30d", 140),
                                              ("reeksen.vlakke_uren_30d", 160), ("reeksen.lokale_pieken_30d", 170),
                                              ("reeksen.reden", 330)])},
            sort=[{"field": col("reeksen", "status_label"), "direction": "Ascending"}])),
    ], [])
    return p


def schrijf_rapport(map_: Path):
    d = map_ / "definition"
    (d / "pages").mkdir(parents=True)
    (map_ / "definition.pbir").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAAM}.SemanticModel"}}}, indent=2), "utf-8")
    (d / "version.json").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
        "version": "2.0.0"}, indent=2), "utf-8")
    basis = "Fluent2-CY26SU10"
    sr = map_ / "StaticResources"
    (sr / "SharedResources" / "BaseThemes").mkdir(parents=True)
    (sr / "RegisteredResources").mkdir(parents=True)
    shutil.copy(PBI / "_bronnen" / f"{basis}.json", sr / "SharedResources" / "BaseThemes" / f"{basis}.json")
    shutil.copy(PBI / "_bronnen" / "thema.json", sr / "RegisteredResources" / "thema.json")
    versie = {"visual": "2.14.0", "report": "3.4.0", "page": "2.3.1"}
    (d / "report.json").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.3.0/schema.json",
        "themeCollection": {
            "baseTheme": {"name": basis, "reportVersionAtImport": versie, "type": "SharedResources"},
            "customTheme": {"name": "thema.json", "reportVersionAtImport": versie, "type": "RegisteredResources"}},
        "objects": {"section": [{"properties": {"verticalAlignment": {"expr": {"Literal": {"Value": "'Top'"}}}}}]},
        "resourcePackages": [
            {"name": "SharedResources", "type": "SharedResources",
             "items": [{"name": basis, "path": f"BaseThemes/{basis}.json", "type": "BaseTheme"}]},
            {"name": "RegisteredResources", "type": "RegisteredResources",
             "items": [{"name": "thema.json", "path": "thema.json", "type": "CustomTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized",
                     "defaultDrillFilterOtherVisuals": True, "allowChangeFilterTypes": True,
                     "useEnhancedTooltips": True, "useDefaultAggregateDisplayName": True}}, indent=2), "utf-8")
    volgorde = []
    for titel_, (visuals, inter) in paginas().items():
        pid = nid()
        volgorde.append(pid)
        pd_ = d / "pages" / pid
        page = {"$schema": PG, "name": pid, "displayName": titel_, "displayOption": "FitToPage",
                "height": 1080, "width": 1920}
        if inter:
            page["visualInteractions"] = inter
        (pd_ / "visuals").mkdir(parents=True)
        (pd_ / "page.json").write_text(json.dumps(page, ensure_ascii=False, indent=2), "utf-8")
        for z, vis in enumerate(visuals):
            vis["position"]["z"] = vis["position"]["tabOrder"] = z * 1000
            vd = pd_ / "visuals" / vis["name"]
            vd.mkdir()
            (vd / "visual.json").write_text(json.dumps(vis, ensure_ascii=False, indent=2), "utf-8")
    (d / "pages" / "pages.json").write_text(json.dumps(
        {"$schema": PM, "pageOrder": volgorde, "activePageName": volgorde[0]}, indent=2), "utf-8")


def main():
    for sub in (f"{NAAM}.SemanticModel", f"{NAAM}.Report"):
        if (PBI / sub).exists():
            shutil.rmtree(PBI / sub)
    schrijf_model(PBI / f"{NAAM}.SemanticModel")
    schrijf_rapport(PBI / f"{NAAM}.Report")
    (PBI / f"{NAAM}.pbip").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0", "artifacts": [{"report": {"path": f"{NAAM}.Report"}}],
        "settings": {"enableAutoRecovery": True}}, indent=2), "utf-8")
    print("Klaar:", PBI / f"{NAAM}.pbip")


if __name__ == "__main__":
    main()
