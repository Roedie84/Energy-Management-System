"""v5.100: welke keuze was achteraf niet de beste, en waarom."""
from custom_components.energy_management_system import keuzeoordeel as K
from custom_components.energy_management_system import nabeschouwing as N

PARAM = dict(capaciteit_kwh=5.0, bodem_kwh=0.0, laad_kw=2.0, ontlaad_kw=2.0, rendement=0.9,
             slijtage_eur_per_kwh=0.0)


def _dag(accu, prijzen, huis=0.25, pv=0.0, reden="x", stand="smart"):
    return [K.Kwartier(tijd=f"{i // 4:02d}:{i % 4 * 15:02d}", huis_kwh=huis, pv_kwh=pv, prijs_eur=p,
                       accu_kwh=a, reden=reden, stand=stand) for i, (a, p) in enumerate(zip(accu, prijzen))]


def test_waardefunctie_gelijk_aan_beste_planning():
    prijzen = [0.20] * 8 + [0.50] * 8
    dag = _dag([0.0] * 16, prijzen)
    nab = [N.Kwartier(huis_kwh=k.huis_kwh, pv_kwh=k.pv_kwh, prijs_eur=k.prijs_eur, accu_kwh=k.accu_kwh) for k in dag]
    beste = N.beste_planning(nab, begin_kwh=2.0, sta_netladen_toe=False, stap_kwh=0.05, **PARAM)
    uit = K.spijt_per_kwartier(dag, begin_kwh=2.0, **PARAM)
    assert abs(uit["beste_kosten_eur"] - beste["kosten_eur"]) < 0.01


def test_spijt_telt_op_tot_het_gemiste_bedrag():
    prijzen = [0.20] * 8 + [0.50] * 8
    # het EMS ontlaadde in de goedkope kwartieren, de accu was leeg in de dure
    accu = [0.25] * 8 + [0.0] * 8
    dag = _dag(accu, prijzen)
    uit = K.spijt_per_kwartier(dag, begin_kwh=2.0, **PARAM)
    werkelijk = sum((k.huis_kwh - k.pv_kwh - k.accu_kwh) * k.prijs_eur for k in dag)
    eind = max(0.0, 2.0 - sum(a / 0.9 ** 0.5 for a in accu))
    restwaarde = eind * (sum(prijzen) / len(prijzen)) * 0.9 ** 0.5
    assert abs(uit["gemist_eur"] - ((werkelijk - restwaarde) - uit["beste_kosten_eur"])) < 0.03
    # de schuld ligt bij het vroege ontladen, niet bij de dure kwartieren
    vroeg = sum(r["spijt_eur"] for r in uit["regels"][:8])
    laat = sum(r["spijt_eur"] for r in uit["regels"][8:])
    assert vroeg > 0.2 and abs(laat) < 0.05


def test_keuzes_groeperen_en_oordelen():
    prijzen = [0.20] * 8 + [0.50] * 8
    accu = [0.25] * 8 + [0.0] * 8
    dag = _dag(accu[:8], prijzen[:8], reden="discharging_window") + _dag(accu[8:], prijzen[8:], reden="default_smart")
    for i, k in enumerate(dag):
        k.tijd = f"{i // 4:02d}:{i % 4 * 15:02d}"
    uit = K.spijt_per_kwartier(dag, begin_kwh=2.0, **PARAM)
    lijst = K.keuzes(uit["regels"], {"discharging_window": "huis dekken"})
    assert [k["kwartieren"] for k in lijst] == [8, 8]
    eerste = lijst[0]
    assert eerste["naam"] == "huis dekken" and eerste["van"] == "00:00" and eerste["tot"] == "02:00"
    assert eerste["niet_de_beste"] and eerste["richting"] == "te veel ontladen"
    assert "kostte € " in K.tekst(eerste)


def test_oorzaak_voorspelling_of_regel():
    assert K.oorzaak({"zon_kwh": 6.0, "verbruik_kwh": 5.0}, {"zon_kwh": 2.0, "verbruik_kwh": 5.1})["oorzaak"] == "voorspelling"
    assert K.oorzaak({"zon_kwh": 2.0, "verbruik_kwh": 5.0}, {"zon_kwh": 2.2, "verbruik_kwh": 5.1})["oorzaak"] == "regel"
    assert K.oorzaak(None, {"zon_kwh": 1.0})["oorzaak"] == "onbekend"


def test_dagoordeel_meldt_alleen_dure_regelkeuzes_en_niet_handmatig():
    keuzes = [
        {"van": "16:00", "tot": "17:00", "naam": "huis dekken", "reden": "discharging_window", "werkelijk_kwh": 1.0,
         "beste_kwh": 0.0, "spijt_eur": 0.40, "richting": "te veel ontladen", "niet_de_beste": True,
         "handmatig": False, "oorzaak": "regel", "toelichting": "", "prijs_ct": 30.0},
        {"van": "18:00", "tot": "19:00", "naam": "verkopen", "reden": "expensive_quarter", "werkelijk_kwh": 1.0,
         "beste_kwh": 0.0, "spijt_eur": 0.30, "richting": "te veel ontladen", "niet_de_beste": True,
         "handmatig": False, "oorzaak": "voorspelling", "toelichting": "zon", "prijs_ct": 40.0},
        {"van": "20:00", "tot": "21:00", "naam": "handmatig_manual", "reden": "handmatig_manual", "werkelijk_kwh": 1.0,
         "beste_kwh": 0.0, "spijt_eur": 0.50, "richting": "te veel ontladen", "niet_de_beste": True,
         "handmatig": True, "oorzaak": "regel", "toelichting": "", "prijs_ct": 40.0},
    ]
    d = K.dagoordeel("2026-10-18", keuzes, 1.2)
    assert len(d["te_melden"]) == 1 and d["te_melden"][0].startswith("16:00-17:00 huis dekken")
    assert "handmatig_manual" not in d["per_reden"]
    assert d["per_reden"]["huis dekken"]["door_regel_eur"] == 0.4
    assert d["per_reden"]["verkopen"]["door_voorspelling_eur"] == 0.3


def test_zelfanalyse_rangschikt_op_regelkosten():
    dag = {"te_becijferen": True, "gemist_eur": 0.5, "per_reden": {
        "huis dekken": {"keuzes": 5, "niet_de_beste": 2, "spijt_eur": 0.6, "door_regel_eur": 0.5,
                        "door_voorspelling_eur": 0.1, "richtingen": {"te veel ontladen": 2}},
        "verkopen": {"keuzes": 2, "niet_de_beste": 1, "spijt_eur": 0.2, "door_regel_eur": 0.0,
                     "door_voorspelling_eur": 0.2, "richtingen": {"te veel ontladen": 1}},
    }}
    z = K.zelfanalyse([dag] * 8)
    assert z["dagen"] == 8 and z["verbeterpunten"][0]["reden"] == "huis dekken"
    assert z["verbeterpunten"][0]["door_regel_eur"] == 4.0
    assert all(p["reden"] != "verkopen" for p in z["verbeterpunten"])
    assert z["trend"]["richting"] == "gelijk"


def test_zelfanalyse_zonder_dagen():
    assert K.zelfanalyse([])["dagen"] == 0


def test_kaart_teksten():
    gisteren = {"te_becijferen": True, "datum": "2026-10-18", "gemist_eur": 0.42, "niet_de_beste": [
        {"tekst": "16:00-17:00 huis dekken: ...", "oorzaak": "voorspelling", "toelichting": "zon verwacht 3,0 kWh, werkelijk 1,0 kWh"}]}
    k = K.kaart(gisteren, {"door_regel_eur": 1.234, "verbeterpunten": [{"tekst": "huis dekken: 2 van 5"}]})
    assert k["kaart_primair"] == "€ 1,23 te verbeteren (30 dagen)"
    assert "gisteren gemist € 0,42" in k["kaart_secundair"] and "huis dekken: 2 van 5" in k["kaart_secundair"]
    assert "(zon verwacht 3,0 kWh" in k["kaart_lijst"] and k["kaart_lijst"].startswith("**Achteraf")
    leeg = K.kaart(None, {"door_regel_eur": 0.0})
    assert "Geen keuze" in leeg["kaart_lijst"] and "nog geen verbeterpunt" in leeg["kaart_secundair"]


def test_neutrale_dag_geeft_geen_spijt():
    """Reviewbevinding: een accu die 100 W dekt bij een vlakke prijs mag geen
    gemist bedrag opleveren (afronden per kwartier liet de stand weglopen)."""
    dag = _dag([0.025] * 96, [0.30] * 96, huis=0.025)
    uit = K.spijt_per_kwartier(dag, begin_kwh=4.0, **PARAM)
    assert abs(uit["gemist_eur"]) < 0.05
