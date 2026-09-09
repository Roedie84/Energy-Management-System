"""De nabeschouwing: wat had de accu die dag het best kunnen doen?
(v3.99.19)

Gevraagd: "Het gaat er mij om of het verstandiger was geweest om
bijvoorbeeld de accu in een andere modus te hebben gezet, en of dit
financieel dan meer had opgeleverd. De integratie moet immers super slim
en goed worden."
"""
import pytest

from custom_components.energy_management_system.nabeschouwing import (
    Kwartier,
    beste_planning,
    kosten_werkelijk,
    kosten_zonder_accu,
    nabeschouwing,
)


def _dag(goedkoop=0.10, duur=0.40):
    """Zestien kwartieren: vier goedkoop, vier gewoon, vier duur, vier
    gewoon. Geen zon, 0,1 kWh verbruik per kwartier."""
    prijzen = [goedkoop] * 4 + [0.25] * 4 + [duur] * 4 + [0.25] * 4
    return [Kwartier(huis_kwh=0.1, pv_kwh=0.0, prijs_eur=p, accu_kwh=0.0) for p in prijzen]


ACCU = dict(capaciteit_kwh=2.0, begin_kwh=0.5, bodem_kwh=0.2, laad_kw=2.0, ontlaad_kw=1.6, rendement=0.84)


def test_de_beste_planning_laadt_goedkoop_en_ontlaadt_duur():
    beste = beste_planning(_dag(), **ACCU)

    assert beste["te_becijferen"]
    geladen = [a["laden_kwh"] for a in beste["acties"]]
    ontladen = [a["ontladen_kwh"] for a in beste["acties"]]
    assert sum(geladen[:4]) > 0.5
    assert sum(ontladen[8:12]) > 0.3
    assert sum(ontladen[:4]) == 0.0


def test_best_mogelijk_is_nooit_duurder_dan_werkelijk():
    kw = _dag()
    # werkelijk: niets gedaan
    uit = nabeschouwing(kw, eind_kwh=0.5, tijdstippen=[f"{i:02d}:00" for i in range(16)], slijtage_eur_per_kwh=0.0, **ACCU)

    assert uit["kosten_best_mogelijk_eur"] <= uit["kosten_werkelijk_eur"] + 0.001
    assert uit["gemist_eur"] >= 0


def test_een_perfecte_dag_mist_niets():
    """Doe werkelijk wat de beste planning doet: gemist is nul."""
    kw = _dag()
    beste = beste_planning(kw, **ACCU)
    # `accu_kwh` is wat het NET ziet (de sensor meet aan de AC-kant):
    # ontladen komt er met rendement uit, laden gaat er met rendement in.
    eta = ACCU["rendement"] ** 0.5
    for k, a in zip(kw, beste["acties"]):
        k.accu_kwh = a["ontladen_kwh"] * eta - a["laden_kwh"] / eta
    uit = nabeschouwing(kw, eind_kwh=beste["eindstand_kwh"], tijdstippen=[str(i) for i in range(16)], slijtage_eur_per_kwh=0.0, **ACCU)

    assert abs(uit["gemist_eur"]) < 0.02


def test_de_grootste_verschillen_wijzen_naar_het_dure_blok():
    kw = _dag()
    uit = nabeschouwing(kw, eind_kwh=0.5, tijdstippen=[f"{i:02d}:00" for i in range(16)], slijtage_eur_per_kwh=0.0, **ACCU)

    assert uit["grootste_verschillen"]
    assert uit["grootste_verschillen"][0]["prijs_ct"] in (40.0, 10.0)


def test_zonder_accu_is_gewoon_huis_min_zon():
    kw = [Kwartier(0.5, 0.2, 0.30, 0.0)]
    assert kosten_zonder_accu(kw) == pytest.approx(0.09)
    kw[0].accu_kwh = 0.3
    assert kosten_werkelijk(kw) == pytest.approx(0.0)


def test_slijtage_maakt_kleine_prijsverschillen_niet_de_moeite():
    kw = _dag(goedkoop=0.24, duur=0.26)
    beste = beste_planning(kw, slijtage_eur_per_kwh=0.12, **ACCU)

    assert sum(a["laden_kwh"] for a in beste["acties"]) == 0.0


# --- het dagverloop in de coordinator -----------------------------------
#
# Gevraagd: "in de diagnostiek opnemen wat het verloop per dag is."
# Per kwartier: reden, stand, laadstand, zon, huis, net, accu, prijs.
# Eén regel per kwartier (de laatste ronde erin), zeven dagen bewaard.

from datetime import datetime, timedelta, timezone


def _ronde(c, hass, wanneer, soc=50.0, pv=1200.0, huis=400.0, net=-800.0, accu=0.0, prijs=0.25, reden="default_smart"):
    c.config = dict(c.config or {})
    c.config["consumption_power_sensor_entity"] = "sensor.net"
    c.config["battery_power_sensor_entity"] = "sensor.accu"
    c.config["battery_soc_sensor_entity"] = "sensor.soc"
    hass.states.set("sensor.net", str(net))
    hass.states.set("sensor.accu", str(accu))
    hass.states.set("sensor.soc", str(soc))
    c._lees_pv_vermogen_w = lambda: pv
    c._read_corrected_consumption_power = lambda: huis
    c.huidige_prijs_eur_per_kwh = lambda now=None: prijs
    c.last_reason = reden
    c.last_expected_mode = "smart"
    c._leg_dagverloop_vast(wanneer)


def test_een_regel_per_kwartier(make_coordinator, hass):
    c = make_coordinator({})
    c.dagverloop = {}
    t0 = datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc)
    _ronde(c, hass, t0)
    _ronde(c, hass, t0 + timedelta(minutes=5), soc=51.0)
    _ronde(c, hass, t0 + timedelta(minutes=16), soc=52.0)

    dag = c.dagverloop["2026-09-08"]
    assert [r["tijd"] for r in dag] == ["10:00", "10:15"]
    assert dag[0]["soc"] == 51.0   # de laatste ronde in het kwartier


def test_zeven_dagen_bewaard(make_coordinator, hass):
    c = make_coordinator({})
    c.dagverloop = {}
    for d in range(9):
        _ronde(c, hass, datetime(2026, 9, 1 + d, 12, 0, tzinfo=timezone.utc))

    assert len(c.dagverloop) == 7
    assert "2026-09-01" not in c.dagverloop


def test_de_nabeschouwing_van_een_dag_uit_het_verloop(make_coordinator, hass):
    c = make_coordinator({})
    c.dagverloop = {}
    c.bruikbare_capaciteit_kwh = lambda: 8.64
    c.effective_min_soc_percent = lambda: 10.0
    t0 = datetime(2026, 9, 8, 0, 0, tzinfo=timezone.utc)
    for q in range(96):
        uur = q // 4
        prijs = 0.10 if 12 <= uur < 15 else (0.40 if 18 <= uur < 21 else 0.25)
        _ronde(c, hass, t0 + timedelta(minutes=15 * q), soc=40.0, pv=0.0, huis=400.0, net=400.0, accu=0.0, prijs=prijs)

    uit = c.get_nabeschouwing("2026-09-08")

    assert uit["te_becijferen"]
    assert uit["kwartieren"] == 96
    assert uit["gemist_eur"] > 0          # er was winst te halen, we deden niets


# --- v4.1: de gesloten lus ------------------------------------------------


def test_de_richting_wordt_geteld():
    kw = _dag()
    uit = nabeschouwing(kw, eind_kwh=0.5, tijdstippen=[str(i) for i in range(16)], slijtage_eur_per_kwh=0.0, **ACCU)
    # wij deden niets; de beste planning ontlaadde in het dure blok
    assert uit["te_veel_vastgehouden_kwh"] > 0
    assert uit["te_veel_ontladen_kwh"] == 0


def test_de_kandidaat_zegt_te_hoog_bij_vasthouden(make_coordinator, hass):
    c = make_coordinator({})
    c.nabeschouwingen = [
        {"te_becijferen": True, "kwartieren": 96, "datum": f"2026-09-0{d}",
         "te_veel_vastgehouden_kwh": 1.2, "te_veel_ontladen_kwh": 0.1, "gemist_eur": 0.30}
        for d in range(1, 5)
    ]

    k = c._kandidaat_reserve_uit_nabeschouwing()

    assert "te hoog" in k["waarde"]
    assert k["mag_regelen"] is False
    assert k["zou_hebben_opgeleverd"]["eur"] == pytest.approx(1.2, abs=0.01)


def test_te_weinig_dagen_geen_oordeel(make_coordinator, hass):
    c = make_coordinator({})
    c.nabeschouwingen = [{"te_becijferen": True, "kwartieren": 96}]

    assert c._kandidaat_reserve_uit_nabeschouwing()["waarde"] is None


# --- v4.2: gemist door de reserve, apart van gemist door de voorspelling
#
# "Best mogelijk" kent de zon van morgen. Een deel van het gemiste bedrag
# is dus onvermijdelijk: geen sturing weet 's ochtends wat de middag
# doet. Wat WEL te beinvloeden is, is de reserve - de energie die de
# integratie 's avonds vasthield terwijl de beste planning die
# verkocht, omdat de nacht achteraf minder bleek te kosten.
#
# De scheiding: reken de beste planning nog een keer, maar dan met de
# reserve als HARDE ondergrens (de accu mag 's avonds niet onder wat de
# integratie als reserve aanhield). Het verschil tussen die twee
# planningen is precies wat de reserve heeft gekost. De rest is
# voorspelling en regels.

from custom_components.energy_management_system.nabeschouwing import (
    beste_planning,
)


def test_een_hardere_bodem_kost_geld():
    """Zelfde dag, maar de accu mag niet onder 1,0 kWh: duurder."""
    kw = _dag()
    vrij = beste_planning(kw, **ACCU)
    met_bodem = beste_planning(kw, **{**ACCU, "bodem_kwh": 1.0})

    assert met_bodem["kosten_eur"] >= vrij["kosten_eur"] - 0.001


def test_de_nabeschouwing_splitst_het_gemiste_bedrag():
    kw = _dag()
    uit = nabeschouwing(
        kw, eind_kwh=0.5, tijdstippen=[str(i) for i in range(16)],
        slijtage_eur_per_kwh=0.0, reserve_kwh=1.0, **ACCU,
    )

    assert "gemist_door_reserve_eur" in uit
    assert "gemist_door_voorspelling_eur" in uit
    assert uit["gemist_door_reserve_eur"] + uit["gemist_door_voorspelling_eur"] == pytest.approx(uit["gemist_eur"], abs=0.01)
    assert uit["gemist_door_reserve_eur"] >= 0


def test_zonder_reserve_is_alles_voorspelling():
    kw = _dag()
    uit = nabeschouwing(kw, eind_kwh=0.5, tijdstippen=[str(i) for i in range(16)], slijtage_eur_per_kwh=0.0, **ACCU)

    assert uit["gemist_door_reserve_eur"] == 0.0
