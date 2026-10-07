"""v5.32 - meerdaags kijken (schaduw).

Gevraagd: "Kunnen we het EMS nog slimmer maken, dus ook de volgende dagen
bekijken, bijvoorbeeld vandaag stroomprijs minimum rond 15 ct en morgen niet
lager dan 30 ct, maar vandaag veel zon en morgen weinig zon."

Het schaduwoptimum rekende al over alle bekende prijzen (tot morgen 24:00),
maar waardeerde wat er aan het eind in de accu zat met een vaste waarde. Nu
telt de zon van de dag erna mee, en laat de Proefstand zien wat een kWh in de
accu waard is - nu en om middernacht - en wat het optimum zou doen.
Schaduw: stuurt niets.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from custom_components.energy_management_system import schaduw

TZ = timezone(timedelta(hours=2))
DAG = datetime(2026, 10, 7, tzinfo=TZ)
RENDEMENT = 84.6


def _scenario(zon_vandaag=True, prijs_morgen=0.30, avond=0.40):
    """Vandaag middag 15 ct en (veel of weinig) zon, avond 40 ct;
    morgen de hele dag minstens 30 ct en weinig zon."""
    kw = []
    for d in range(2):
        for i in range(96):
            t = i / 4
            if d == 0:
                prijs = 0.15 if 11 <= t < 15 else (avond if 18 <= t < 22 else 0.30)
                zon = (0.5 if zon_vandaag else 0.05) if 10 <= t < 16 else 0.0
            else:
                prijs = prijs_morgen
                zon = 0.02 if 11 <= t < 15 else 0.0
            kw.append({"import": prijs, "export": prijs, "verbruik": 0.1, "zon": zon})
    return kw


def _opt(kw, slijtage_ct, eindwaarde=None):
    return schaduw.optimaliseer(
        kw, emax_kwh=7.78, laad_kwh=0.6, ontlaad_kwh=0.6,
        rendement_procent=RENDEMENT, slijtage_ct=slijtage_ct, eindwaarde_eur=eindwaarde,
    )


# --- de eindwaarde -----------------------------------------------------------


def test_weinig_zon_na_de_horizon_houdt_een_kwh_waardevol():
    kw = _scenario()
    eind = schaduw.eindwaarde_meerdaags(
        kw, rendement_procent=RENDEMENT, slijtage_ct=4.22,
        zon_na_horizon_kwh=1.0, verbruik_na_horizon_kwh=9.0,
    )
    assert eind["zon_dekking"] < 0.2
    assert eind["eindwaarde_eur"] > 0.8 * eind["importwaarde_eur"]


def test_volle_zon_na_de_horizon_maakt_een_kwh_alleen_het_terugleveren_waard():
    kw = _scenario()
    for k in kw:
        k["export"] = 0.05
    eind = schaduw.eindwaarde_meerdaags(
        kw, rendement_procent=RENDEMENT, slijtage_ct=4.22,
        zon_na_horizon_kwh=25.0, verbruik_na_horizon_kwh=9.0,
    )
    assert eind["zon_dekking"] == 1.0
    assert eind["eindwaarde_eur"] == eind["exportwaarde_eur"] == 0.05


def test_zonder_zonverwachting_de_oude_vaste_waarde():
    kw = _scenario()
    eind = schaduw.eindwaarde_meerdaags(
        kw, rendement_procent=RENDEMENT, slijtage_ct=4.22,
        zon_na_horizon_kwh=None, verbruik_na_horizon_kwh=9.0,
    )
    oud = _opt(kw, 4.22)["eindwaarde_eur"]
    assert eind["bron"] == "vast"
    assert abs(eind["eindwaarde_eur"] - oud) < 1e-4


# --- het voorbeeld van 7 oktober ----------------------------------------------


def test_15_ct_vandaag_morgen_28_ct_weinig_zon_met_cyclusslijtage_laden():
    """Geen avondpiek: alleen de 28 ct van daarna telt. Het optimum rekent
    slijtage per kWh die de accu afgeeft: (28 - 4,22) x 84,6% = 20,1 ct
    > 15 ct - laden loont."""
    kw = _scenario(zon_vandaag=False, prijs_morgen=0.28, avond=0.28)
    for k in kw[:96]:
        if k["import"] == 0.30:
            k["import"] = k["export"] = 0.28
    opt = _opt(kw, 4.22)
    waarden = schaduw.alternatieven(opt, kw, 12 * 4, 2.0)
    assert schaduw.beste_twee(waarden)[0] == "laden"


def test_met_hoge_slijtage_loont_hetzelfde_laden_niet():
    """(28 - 11,28) x 84,6% = 14,1 ct: onder de 15 ct van de inkoop."""
    kw = _scenario(zon_vandaag=False, prijs_morgen=0.28, avond=0.28)
    for k in kw[:96]:
        if k["import"] == 0.30:
            k["import"] = k["export"] = 0.28
    waarden = schaduw.alternatieven(_opt(kw, 11.28), kw, 12 * 4, 2.0)
    assert schaduw.beste_twee(waarden)[0] != "laden"


def test_met_een_avondpiek_loont_laden_ook_met_hoge_slijtage():
    """40 x 84,6% - 11,28 = 22,6 ct > 15 ct."""
    kw = _scenario(zon_vandaag=False, avond=0.40)
    waarden = schaduw.alternatieven(_opt(kw, 11.28), kw, 12 * 4, 2.0)
    assert schaduw.beste_twee(waarden)[0] == "laden"


def test_weinig_zon_na_de_horizon_maakt_middernacht_meer_waard():
    kw = _scenario()
    q, middernacht = 12 * 4, 96
    somber = _opt(kw, 4.22, eindwaarde=0.22)
    zonnig = _opt(kw, 4.22, eindwaarde=0.02)
    s_somber = schaduw.optimaal_pad(somber, kw, q, 2.0, middernacht)
    s_zonnig = schaduw.optimaal_pad(zonnig, kw, q, 2.0, middernacht)
    assert s_somber >= s_zonnig
    assert schaduw.waarde_per_kwh(somber, middernacht, s_somber) >= schaduw.waarde_per_kwh(zonnig, middernacht, s_zonnig)


def test_het_optimale_pad_blijft_binnen_de_accu():
    kw = _scenario()
    opt = _opt(kw, 4.22)
    for doel in (48, 96, 150):
        s = schaduw.optimaal_pad(opt, kw, 0, 3.0, doel)
        assert 0 <= s <= 7.78


# --- de tekst ---------------------------------------------------------------


def test_de_tekst_zegt_wat_een_kwh_waard_is_en_wat_het_optimum_doet():
    m = {
        "beschikbaar": True, "slijtage_productie_ct": 11.28,
        "prijs_nu_eur": 0.15, "export_nu_eur": 0.15,
        "horizon_tot": "2026-10-08T23:45:00+02:00",
        "na_horizon": {"datum": "2026-10-09", "zon_kwh": 1.2, "verbruik_kwh": 8.9},
        "varianten": {
            11.28: {"waarde_nu_eur": 0.14, "waarde_middernacht_eur": 0.16, "accu_middernacht_kwh": 7.1,
                    "schaduwactie": "bewaren",
                    "eindwaarde": {"eindwaarde_eur": 0.12, "zon_dekking": 0.13, "importwaarde_eur": 0.14, "exportwaarde_eur": 0.15}},
            4.22: {"waarde_nu_eur": 0.21, "waarde_middernacht_eur": 0.22, "accu_middernacht_kwh": 7.78,
                   "schaduwactie": "laden", "eindwaarde": {}},
        },
    }
    tekst = schaduw.meerdaags_tekst(m)
    assert "€ 0,14" in tekst and "laden uit het net" in tekst
    assert "2026-10-09" in tekst and "13%" in tekst
    assert "stuurt niets" in tekst


def test_zonder_berekening_een_korte_reden():
    assert "Nog geen" in schaduw.meerdaags_tekst({"beschikbaar": False, "reden": "geen schaduw"})


# --- de coördinator en de meetlaag ------------------------------------------


def test_zon_per_dag_vandaag_morgen_en_verder(make_coordinator, hass):
    c = make_coordinator({
        "solar_today_forecast_sensor_entity": "sensor.zon_vandaag",
        "solar_forecast_sensor_entity": "sensor.zon_morgen",
        "solar_extended_forecast_sensor_entities": ["sensor.zon_dag_3", "sensor.zon_dag_4"],
    })
    for naam, waarde in (("sensor.zon_vandaag", "12.5"), ("sensor.zon_morgen", "2.1"),
                         ("sensor.zon_dag_3", "1.4"), ("sensor.zon_dag_4", "unknown")):
        hass.states.set(naam, waarde)
    dagen = c.zon_per_dag_kwh(DAG.date())
    assert dagen == {DAG.date(): 12.5, DAG.date() + timedelta(days=1): 2.1, DAG.date() + timedelta(days=2): 1.4}
    na = c.zon_na_horizon(DAG.replace(hour=14), DAG + timedelta(days=2))
    assert na["datum"] == "2026-10-09" and na["zon_kwh"] == 1.4


def test_de_meetlaag_geeft_de_meerdaagse_afweging(make_coordinator, hass):
    from gouden_scenarios import draai

    draai(make_coordinator, hass, "middag_goedkoop_leeg")
    laag = draai.laatste._meetlaag
    m = laag.meerdaags
    assert m is not None
    if m.get("beschikbaar"):
        assert m["waarde_nu_eur"] is not None
        assert "stuurt niets" in m["tekst"]
    assert "meerdaags" in laag.samenvatting()


def test_de_proefstand_toont_de_kaart():
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    sjabloon = (Path(pkg.__file__).parent / "dashboard_template.yaml").read_text(encoding="utf-8")
    assert "Meerdaags (schaduw)" in sjabloon
    assert "''meerdaags'')" in sjabloon
