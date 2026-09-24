"""De testmatrix van de cockpit (v5.18).

Gevraagd: *"test de cockpit niet alleen met mooie voorbeelden"* en
*"de testmatrix is vanaf nu het contract"*.

Negenentwintig gevallen. Per geval: welke primaire waarden zichtbaar zijn,
wat ONBEKEND wordt, welke secundaire velden verdwijnen, en welke status
ontstaat - met de reden erbij.

Eindprincipe: *"een geloofwaardige maar onjuiste waarde is niet
acceptabel."*
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_management_system.const import (
    CONSISTENCY_TICK_STALE_MINUTES,
    MIN_BATTERY_POWER_IDLE_W,
)
from custom_components.energy_management_system.overview_svg import (
    ONBEKEND,
    bouw_scada,
)

NU = datetime(2026, 9, 24, 13, 40, tzinfo=timezone.utc)


def _gezond(c, hass):
    """Een draaiende installatie: geslaagde ronde, niets kapot."""
    from homeassistant.util import dt as dt_util

    c.last_successful_update = dt_util.now()
    c.internal_failures = {}
    c.get_configuratiecontrole = lambda: {
        "entiteiten": [{"oordeel": "in_orde", "instelling": "price_sensor_entity"}]
    }
    c.get_energiebalans_controle = lambda: {"beschikbaar": True, "alles_klopt": True}
    c.get_diagnostic_summary = lambda: {"aandachtspunten": []}
    return c


# --- de dode band rond 25 W ---------------------------------------------


@pytest.mark.parametrize(
    "vermogen,verwacht",
    [
        (0.0, "STANDBY"),
        (12.0, "STANDBY"),
        (-12.0, "STANDBY"),
        (MIN_BATTERY_POWER_IDLE_W - 0.1, "STANDBY"),
        (MIN_BATTERY_POWER_IDLE_W, "ONTLADEN"),
        (-MIN_BATTERY_POWER_IDLE_W, "LADEN"),
        (800.0, "ONTLADEN"),
        (-800.0, "LADEN"),
    ],
)
def test_de_accustand_gebruikt_de_bestaande_dode_band(
    make_coordinator, hass, vermogen, verwacht
):
    """Dezelfde grens als `get_battery_power_display` en de regellogica."""
    c = make_coordinator({})
    c._read_corrected_battery_power = lambda: vermogen

    assert c.accu_stand() == verwacht


def test_cockpit_en_sensor_zeggen_hetzelfde_over_dezelfde_waarde(
    make_coordinator, hass
):
    """Nooit twee antwoorden op één vermogenswaarde."""
    c = make_coordinator({})
    for vermogen in (-800.0, -30.0, -12.0, 0.0, 12.0, 24.9, 25.0, 800.0):
        c._read_corrected_battery_power = lambda v=vermogen: v
        stand = c.accu_stand()
        tekst = c.get_battery_power_display()

        if stand == "STANDBY":
            assert tekst == "rust", (vermogen, tekst)
        else:
            assert stand.lower() in tekst, (vermogen, stand, tekst)


def test_zonder_meting_is_de_accustand_onbekend(make_coordinator, hass):
    """Niet STANDBY: dat zou een stilstaande accu suggereren."""
    c = make_coordinator({})
    c._read_corrected_battery_power = lambda: None

    assert c.accu_stand() is None
    assert ONBEKEND in bouw_scada({"accustand": None})


# --- primaire waarden: 0 is een meting, niets is ONBEKEND ----------------


@pytest.mark.parametrize("veld", ["pv_w", "net_w", "huis_w", "accu_w"])
def test_een_ontbrekende_primaire_waarde_wordt_onbekend(veld):
    plaat = bouw_scada({veld: None})

    assert ONBEKEND in plaat


@pytest.mark.parametrize("veld", ["pv_w", "net_w", "huis_w"])
def test_een_echte_nul_blijft_een_nul(veld):
    """'s Nachts is de zon echt 0 W - dat is geen ontbrekende meting."""
    plaat = bouw_scada({veld: 0.0, "accustand": "STANDBY"})

    # De eenheid staat in een eigen tspan, dus ">0<" is het getal zelf. De
    # ANDERE velden zijn in deze opzet niet meegegeven en staan terecht op
    # ONBEKEND; het gaat erom dat DIT veld een nul toont.
    assert ">0<" in plaat


def test_het_net_vertaalt_het_teken_naar_taal():
    assert "INKOOP" in bouw_scada({"net_w": 620.0})
    assert "TERUGLEVERING" in bouw_scada({"net_w": -620.0})
    assert "GEEN UITWISSELING" in bouw_scada({"net_w": 0.0})
    assert ONBEKEND in bouw_scada({"net_w": None})


# --- het huisverbruik: de bestaande, juiste formule ----------------------


def test_het_huisverbruik_telt_de_accu_erbij(make_coordinator, hass):
    """De cockpit gebruikte `net + zon - accu`, terwijl positief
    accuvermogen ONTLADEN is. 's Nachts gaf dat via max(0, ...) een
    huisverbruik van 0 W, terwijl het dagverloop 163 W toonde.

    Gemeten geval uit de export van 24 september 03:00:
        net -49 W, accu +212 W, zon 0 W  ->  huis 163 W
    """
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config["consumption_power_sensor_entity"] = "sensor.p1"
    c.config["pv_power_sensor_entity"] = "sensor.pv"
    c.config["battery_power_sensor_entity"] = "sensor.accu"
    hass.states.set("sensor.p1", "-49")
    hass.states.set("sensor.pv", "0")
    hass.states.set("sensor.accu", "211.955")

    assert round(c.cockpit_huisverbruik_w()) == 163


def test_zonder_accumeting_is_het_huisverbruik_onbekend(make_coordinator, hass):
    """Anders staat de netafname er als huisverbruik, en dat lijkt
    geloofwaardig."""
    c = make_coordinator({})
    c.config = dict(c.config or {})
    c.config["consumption_power_sensor_entity"] = "sensor.p1"
    c.config["battery_power_sensor_entity"] = "sensor.accu"
    hass.states.set("sensor.p1", "-49")
    hass.states.set("sensor.accu", "unavailable")

    assert c.cockpit_huisverbruik_w() is None


# --- de accubalk: een referentie -----------------------------------------


def _accu(c, hass, soc, beschikbaar, reserve, nominaal="8.64", ondergrens="10"):
    c.config = dict(c.config or {})
    c.config["battery_total_capacity_sensor_entity"] = "sensor.cap"
    c.config["battery_min_soc_number_entity"] = "number.min_soc"
    if nominaal is not None:
        hass.states.set("sensor.cap", nominaal)
    if ondergrens is not None:
        hass.states.set("number.min_soc", ondergrens)
    c.accustand_procent = lambda: soc
    c.beschikbare_energie_kwh = lambda: beschikbaar
    c.last_reserve_margin_breakdown = (
        {"reserve_kwh_after_margin": reserve} if reserve is not None else {}
    )
    return c


def test_de_reservegrens_rekent_vanaf_de_ondergrens(make_coordinator, hass):
    """4,60 kWh reserve boven een ondergrens van 10% bij 8,64 kWh hoort bij
    een laadstand van 63%, niet 53%. Dat was de fout uit de review."""
    c = _accu(make_coordinator({}), hass, soc=10.0, beschikbaar=0.0, reserve=4.60)

    balk = c.cockpit_accu()["balk"]

    assert round(balk["reserve_deel"] * 100) == 63
    assert round(balk["ondergrens_deel"] * 100) == 10
    assert round(balk["soc_deel"] * 100) == 10


def test_zonder_nominale_capaciteit_geen_balk(make_coordinator, hass):
    """Liever geen balk dan een geloofwaardige benadering."""
    c = _accu(make_coordinator({}), hass, 50.0, 3.0, 2.0, nominaal=None)
    hass.states.set("sensor.cap", "unknown")

    assert c.cockpit_accu()["balk"] is None


def test_zonder_ondergrens_geen_balk(make_coordinator, hass):
    c = _accu(make_coordinator({}), hass, 50.0, 3.0, 2.0, ondergrens=None)
    hass.states.set("number.min_soc", "unavailable")

    assert c.cockpit_accu()["balk"] is None


# --- vrij tegenover tekort ------------------------------------------------


@pytest.mark.parametrize(
    "beschikbaar,reserve,vrij,tekort",
    [
        (0.0, 2.01, 0.0, 2.01),      # A. laadstand op de ondergrens
        (2.01, 2.01, 0.0, 0.0),      # B. precies op de reserve
        (7.8, 2.01, 5.79, 0.0),      # C. ruim erboven
        (4.9, 0.0, 4.9, 0.0),        # D. reserve nul
        (0.95, 4.60, 0.0, 3.65),     # E. reserve groter dan beschikbaar
    ],
)
def test_vrij_en_tekort_zijn_allebei_zichtbaar(
    make_coordinator, hass, beschikbaar, reserve, vrij, tekort
):
    """Het tekort mag niet verdwijnen achter een vrij van 0,00."""
    c = _accu(make_coordinator({}), hass, 50.0, beschikbaar, reserve)

    uit = c.cockpit_accu()

    assert round(uit["vrij_kwh"], 2) == vrij
    assert round(uit["tekort_kwh"], 2) == tekort


def test_een_tekort_staat_op_de_plaat():
    plaat = bouw_scada({"tekort_kwh": 3.65, "soc": 10.0})

    assert "tekort" in plaat and "3,65" in plaat


def test_een_onmogelijke_reserve_is_een_aandachtspunt(make_coordinator, hass):
    """Reserve groter dan de accu: dat is een rekenfout, geen weergave."""
    c = _accu(make_coordinator({}), hass, 50.0, 3.0, 9.9)

    assert c.cockpit_accu()["onmogelijke_reserve"] is True
    punten = " ".join(str(p) for p in c._aandachtspunten_over_de_integratie())
    assert "past niet in de accu" in punten


def test_zonder_reserve_is_er_geen_tekort(make_coordinator, hass):
    """v5.19.6 - VERWACHTING BEWUST GEWIJZIGD, en dat hoort gemeld.

    Eerst stond hier dat vrij en tekort allebei leeg blijven zonder
    reserve. Gemeld: "waardes leeg". Zonder reserve is er niets te
    overbruggen, dus legt niets beslag op de beschikbare energie: die is
    helemaal vrij, en een tekort bestaat niet. Leeg laten was een weergave
    van onwetendheid die er niet was."""
    c = _accu(make_coordinator({}), hass, 50.0, 3.0, None)

    uit = c.cockpit_accu()

    assert uit["vrij_kwh"] == 3.0 and uit["tekort_kwh"] == 0.0


# --- de volgende actie ----------------------------------------------------


def _plan(c, regels):
    c.get_quarter_plan = lambda now=None: regels
    return c


def test_de_volgende_actie_komt_uit_het_kwartierplan(make_coordinator, hass):
    from homeassistant.util import dt as dt_util

    nu = dt_util.now()
    c = _plan(
        make_coordinator({}),
        [
            {"van": (nu - timedelta(minutes=10)).isoformat(), "modus": "smart"},
            {"van": (nu + timedelta(minutes=20)).isoformat(), "modus": "smart"},
            {"van": (nu + timedelta(minutes=50)).isoformat(), "modus": "laden"},
        ],
    )

    assert c.volgende_actie(nu).startswith("laden ")


def test_geen_wisseling_in_het_plan_is_geen_volgende_actie(make_coordinator, hass):
    """De oude terugval zette hier het goedkope blok neer - geloofwaardig
    maar onjuist.

    v5.19.1: het antwoord is niet meer None maar "geen wisseling". Gemeld:
    "2 onbekenden?" - het plan bestaat wél en voorziet geen wisseling, en
    dat is iets anders dan niet weten."""
    from homeassistant.util import dt as dt_util

    nu = dt_util.now()
    c = _plan(
        make_coordinator({}),
        [
            {"van": (nu - timedelta(minutes=10)).isoformat(), "modus": "smart"},
            {"van": (nu + timedelta(minutes=20)).isoformat(), "modus": "smart"},
        ],
    )
    c.last_cheap_block_start = nu + timedelta(hours=4)

    assert c.volgende_actie(nu) == "geen wisseling"


def test_een_actie_in_het_verleden_telt_niet(make_coordinator, hass):
    from homeassistant.util import dt as dt_util

    nu = dt_util.now()
    c = _plan(
        make_coordinator({}),
        [{"van": (nu - timedelta(minutes=30)).isoformat(), "modus": "laden"}],
    )

    # v5.19.1: het plan bestaat, maar er komt niets meer - "geen wisseling".
    assert c.volgende_actie(nu) == "geen wisseling"


def test_zonder_plan_geen_volgende_actie(make_coordinator, hass):
    c = _plan(make_coordinator({}), [])

    assert c.volgende_actie() is None


# --- besluit, uitleg en waarom als een momentopname -----------------------


def test_het_snapshot_legt_besluit_uitleg_en_redenen_samen_vast(
    make_coordinator, hass
):
    from homeassistant.util import dt as dt_util

    c = make_coordinator({})
    c.get_why_now = lambda now=None: {
        "beschikbaar": True, "code": "zon_opvangen", "kort": "Zon opvangen",
        "redenen": ["hoge zonverwachting", "reserve voldoende"],
    }
    c.last_explanation = "De accu houdt ruimte vrij."

    c._besluit_snapshot_vastleggen(dt_util.now())
    snapshot = c.get_besluit_snapshot()

    assert snapshot["kort"] == "Zon opvangen"
    assert snapshot["uitleg"] == "De accu houdt ruimte vrij."
    assert snapshot["redenen"] == ["hoge zonverwachting", "reserve voldoende"]


def test_een_oud_snapshot_telt_niet_meer(make_coordinator, hass):
    """Anders staat een nieuw besluit naast een oude verklaring."""
    from homeassistant.util import dt as dt_util

    c = make_coordinator({})
    c.besluit_snapshot = {
        "moment": (dt_util.now() - timedelta(hours=1)).isoformat(),
        "kort": "Oud besluit",
    }

    assert c.get_besluit_snapshot() == {}


def test_zonder_snapshot_is_het_besluit_onbekend():
    assert ONBEKEND in bouw_scada({"besluit": None})


# --- de statusmatrix ------------------------------------------------------


def test_de_ronde_te_lang_geleden_is_storing(make_coordinator, hass):
    from homeassistant.util import dt as dt_util

    c = _gezond(make_coordinator({}), hass)
    c.last_successful_update = dt_util.now() - timedelta(
        minutes=CONSISTENCY_TICK_STALE_MINUTES + 5
    )

    stand, reden = c._ems_status()

    assert stand == "STORING"
    assert "ronde" in reden


def test_een_noodzakelijke_koppeling_kapot_is_storing(make_coordinator, hass):
    c = _gezond(make_coordinator({}), hass)
    c.get_configuratiecontrole = lambda: {
        "entiteiten": [
            {"oordeel": "geen_waarde", "instelling": "price_sensor_entity"}
        ]
    }

    stand, reden = c._ems_status()

    assert stand == "STORING"
    assert "price_sensor_entity" in reden


def test_een_niet_noodzakelijke_koppeling_kapot_is_let_op(make_coordinator, hass):
    """Een weggevallen vaatwassersensor zette het hele EMS op STORING."""
    c = _gezond(make_coordinator({}), hass)
    c.get_configuratiecontrole = lambda: {
        "entiteiten": [
            {"oordeel": "geen_waarde", "instelling": "dishwasher_power_sensor_entity"}
        ]
    }

    assert c._ems_status()[0] == "LET OP"


def test_een_afwijkende_balans_alleen_is_let_op(make_coordinator, hass):
    c = _gezond(make_coordinator({}), hass)
    c.get_energiebalans_controle = lambda: {
        "beschikbaar": True, "alles_klopt": False
    }

    assert c._ems_status()[0] == "LET OP"


def test_een_fout_is_ingrijpen(make_coordinator, hass):
    c = _gezond(make_coordinator({}), hass)
    c.get_diagnostic_summary = lambda: {
        "aandachtspunten": [{"ernst": "fout", "onderwerp": "Celspanning"}]
    }

    assert c._ems_status()[0] == "INGRIJPEN"


def test_zonder_diagnostiek_is_de_status_onbekend(make_coordinator, hass):
    """Kan de gezondheid zelf niet bepaald worden, dan niet GOED zeggen."""
    c = _gezond(make_coordinator({}), hass)

    def stuk():
        raise RuntimeError("diagnostiek stuk")

    c.get_diagnostic_summary = stuk

    assert c._ems_status()[0] == "ONBEKEND"


def test_een_gezonde_installatie_is_goed(make_coordinator, hass):
    c = _gezond(make_coordinator({}), hass)

    stand, regel = c._ems_status()

    assert stand == "GOED"
    assert "koppelingen 1/1" in regel


def test_geen_enkele_lege_waarde_belandt_als_none_op_de_plaat():
    """Bij het renderen stond er letterlijk "None" in de balk."""
    plaat = bouw_scada(
        {
            "balk": [("VOLGENDE ACTIE", None, "#f4f7fa", None)],
            "besluit": None,
            "net_w": None,
        }
    )

    assert ">None<" not in plaat
    assert plaat.count(ONBEKEND) >= 3


def test_de_spreiding_is_een_eigenschap_geen_functie(make_coordinator, hass):
    """Gemeld in bedrijf: "1 onderdeel(en) vallen om - overzichtsplaat",
    met in de export: TypeError: 'float' object is not callable.

    `deviation_stdev_percent` is een @property. Met haakjes erachter
    probeert Python het GETAL aan te roepen. In de toetsen ontbrak de
    zonvolger, dus die regel werd nooit bereikt - deze toets zet er wel
    een neer."""
    from homeassistant.util import dt as dt_util

    class Volger:
        enabled = True
        deviation_stdev_percent = 12.4

    c = _gezond(make_coordinator({}), hass)
    c.solar_tracker = Volger()
    c.last_successful_update = dt_util.now()

    stand, regel = c._ems_status()

    # De bug zat in het AANROEPEN van de eigenschap; dat een zonvolger met
    # spreiding de status niet laat omvallen, is wat hier telt. De spreiding
    # zelf staat sinds v5.19.5 alleen nog in de balk, niet in de statusregel.
    assert stand == "GOED"
    assert "voorspelling" not in regel


def test_de_plaat_komt_er_met_een_zonvolger_erbij(make_coordinator, hass):
    """Het geval dat in bedrijf omviel: een coordinator MET zonvolger."""

    class Volger:
        enabled = True
        deviation_stdev_percent = 12.4
        deviation_history = [1.0, 2.0]

    c = _gezond(make_coordinator({}), hass)
    c.solar_tracker = Volger()

    plaat = c.get_overview_svg()

    assert plaat.startswith("<img")


@pytest.mark.parametrize(
    "naam,verwacht",
    [
        ("Diepvries schuur Vermogen", "Diepvries schuur"),
        ("Diepvries schuur Vermogen fase 1", "Diepvries schuur"),
        ("Koelkast schuur Power", "Koelkast schuur"),
        ("Wasmachine Energie", "Wasmachine"),
        ("Vaatwasser", "Vaatwasser"),
        # v5.18.5: het vermogen tussen haakjes hoort erbij en staat ACHTER
        # het meetwoord - gemeld: "grootste nu: Meterkast Vermogen (18 W)".
        ("Meterkast Vermogen (18 W)", "Meterkast (18 W)"),
        ("Koelkast schuur Vermogen fase 1 (77 W)", "Koelkast schuur (77 W)"),
        ("Vaatwasser (420 W)", "Vaatwasser (420 W)"),
        ("Quooker", "Quooker"),
        (None, None),
    ],
)
def test_de_naam_van_het_apparaat_zonder_meetwoord(
    make_coordinator, hass, naam, verwacht
):
    """Gemeld: "grootste nu: Diepvries schuur Vermogen..." - het apparaat
    heet "Diepvries schuur"."""
    c = make_coordinator({})

    assert c.apparaatnaam_zonder_meetwoord(naam) == verwacht


def test_de_uitleg_breekt_af_op_een_woord():
    """Midden in een zin afkappen leest slecht, en juist die zin is de
    motivatie van het besluit."""
    from custom_components.energy_management_system.overview_svg import _regels

    zin = (
        "De accu heeft niet genoeg beschikbare energie (0.00 kWh) om zowel "
        "het huis te dekken als het dure blok te overbruggen."
    )

    regels = _regels(zin, 78, 2)

    assert len(regels) == 2
    assert all(not r.endswith(" ") for r in regels)
    assert "…" not in " ".join(regels)


def test_een_te_lange_zin_krijgt_een_beletselteken_op_de_laatste_regel():
    from custom_components.energy_management_system.overview_svg import _regels

    regels = _regels(" ".join(["woord"] * 60), 40, 2)

    assert len(regels) == 2
    assert regels[-1].endswith("…")
    assert not regels[0].endswith("…")


def test_geen_wisseling_in_het_plan_zegt_dat_ook(make_coordinator, hass):
    """v5.19.1 - gemeld: "2 onbekenden?". Het plan bestaat wél en voorziet
    geen wisseling; dat is iets anders dan "ik weet het niet"."""
    from homeassistant.util import dt as dt_util

    nu = dt_util.now()
    c = _plan(
        make_coordinator({}),
        [
            {"van": (nu - timedelta(minutes=10)).isoformat(), "modus": "smart"},
            {"van": (nu + timedelta(minutes=20)).isoformat(), "modus": "smart"},
        ],
    )

    assert c.volgende_actie(nu) == "geen wisseling"


def test_zonder_plan_blijft_het_onbekend(make_coordinator, hass):
    """Geen plan is wél "ik weet het niet"."""
    c = _plan(make_coordinator({}), [])

    assert c.volgende_actie() is None


def test_zonder_goedkoop_blok_heet_de_reserve_geen_blok(make_coordinator, hass):
    """Er is geen volgend blok om naar te overbruggen - dat weten we, dus
    zeggen we het."""
    c = _gezond(make_coordinator({}), hass)
    c.last_cheap_block_start = None
    c.last_reserve_margin_breakdown = {}

    balk = dict((label, waarde) for label, waarde, _k, _p in c._schema_gegevens()["balk"])

    assert balk["RESERVE"] == "geen blok"


def test_de_reden_staat_vooraan_zodra_het_niet_goed_is(make_coordinator, hass):
    """Gemeld met een schermafdruk: "waarop letten? niet geheel duidelijk".
    Er stond LET OP, en de aanleiding stond verstopt tussen de andere
    cijfers."""
    c = _gezond(make_coordinator({}), hass)
    c.get_energiebalans_controle = lambda: {"beschikbaar": True, "alles_klopt": False}

    stand, regel = c._ems_status()

    assert stand == "LET OP"
    assert regel.startswith("de energiebalans wijkt af")


def test_bij_ingrijpen_staat_het_onderwerp_vooraan(make_coordinator, hass):
    c = _gezond(make_coordinator({}), hass)
    c.get_diagnostic_summary = lambda: {
        "aandachtspunten": [{"ernst": "fout", "onderwerp": "Celspanning"}]
    }

    stand, regel = c._ems_status()

    assert stand == "INGRIJPEN"
    assert regel.startswith("fout: Celspanning")


def test_een_kapotte_koppeling_wordt_bij_naam_genoemd(make_coordinator, hass):
    c = _gezond(make_coordinator({}), hass)
    c.get_configuratiecontrole = lambda: {
        "entiteiten": [
            {"oordeel": "geen_waarde", "instelling": "dishwasher_power_sensor_entity"}
        ]
    }

    stand, regel = c._ems_status()

    assert stand == "LET OP"
    assert regel.startswith("koppeling kapot: dishwasher_power_sensor_entity")


def test_een_lopend_blok_geeft_geen_reserve_maar_ook_geen_onbekend(
    make_coordinator, hass
):
    """Gemeld: RESERVE stond op ONBEKEND terwijl het goedkope blok om 12:00
    al was begonnen. Er is dan geen volgend blok om naar te overbruggen."""
    from homeassistant.util import dt as dt_util

    c = _gezond(make_coordinator({}), hass)
    c.last_cheap_block_start = dt_util.now() - timedelta(minutes=5)
    c.last_reserve_margin_breakdown = {}

    balk = dict((label, waarde) for label, waarde, _k, _p in c._schema_gegevens()["balk"])

    assert balk["RESERVE"] == "geen blok"



def test_de_voorspelling_staat_maar_een_keer_op_de_plaat(make_coordinator, hass):
    """Gemeld: "2x voorspelling?" - hij stond in de statusregel en in de
    balk. De statusregel gaat over gezondheid; de spreiding van de
    zonvoorspelling is context en hoort in de balk."""

    class Volger:
        enabled = True
        deviation_stdev_percent = 18.0
        deviation_history = [1.0, 2.0]

    c = _gezond(make_coordinator({}), hass)
    c.solar_tracker = Volger()

    _stand, regel = c._ems_status()
    balk = dict((label, waarde) for label, waarde, _k, _p in c._schema_gegevens()["balk"])

    assert "voorspelling" not in regel
    assert balk["VOORSPELLING"] == "±18%"


# --- v5.19.6: resterende tijd en lege waarden ----------------------------


def _resttijd(c, hass, vermogen, soc=47.0, beschikbaar=3.1, nominaal="8.64"):
    c.config = dict(c.config or {})
    c.config["battery_total_capacity_sensor_entity"] = "sensor.cap"
    hass.states.set("sensor.cap", nominaal)
    c._read_corrected_battery_power = lambda: vermogen
    c.accustand_procent = lambda: soc
    c.beschikbare_energie_kwh = lambda: beschikbaar
    return c.accu_resttijd()


def test_laden_rekent_de_tijd_tot_vol(make_coordinator, hass):
    """8,64 kWh x (100 - 47)% = 4,58 kWh, bij 2,0 kW laden = 2u17."""
    assert _resttijd(make_coordinator({}), hass, -2000.0) == "vol over 2u17"


def test_ontladen_rekent_de_tijd_tot_de_ondergrens(make_coordinator, hass):
    """3,1 kWh beschikbaar bij 250 W ontladen = 12u24."""
    assert _resttijd(make_coordinator({}), hass, 250.0) == "ondergrens over 12u24"


def test_binnen_de_dode_band_is_er_geen_tijd(make_coordinator, hass):
    """De accu staat stil; een tijd van dagen zou onzin zijn."""
    assert _resttijd(make_coordinator({}), hass, 12.0) is None


def test_zonder_meting_geen_tijd(make_coordinator, hass):
    assert _resttijd(make_coordinator({}), hass, None) is None
    assert _resttijd(make_coordinator({}), hass, -2000.0, soc=None) is None


def test_zonder_reserve_is_alle_beschikbare_energie_vrij(make_coordinator, hass):
    """Gemeld: "waardes leeg" - er stond "vrij —" terwijl er niets te
    overbruggen was en alle beschikbare energie dus vrij is."""
    c = _accu(make_coordinator({}), hass, 47.0, 3.1, None)

    uit = c.cockpit_accu()

    assert uit["vrij_kwh"] == 3.1
    assert uit["tekort_kwh"] == 0.0


def test_zonder_reserve_geen_markering_in_de_balk():
    """Een streepje op 0% zou een reserve van nul suggereren."""
    from custom_components.energy_management_system.overview_svg import _soc_balk

    zonder = _soc_balk(0, 0, 200, 0.47, None, "#fff", 0.10)
    met = _soc_balk(0, 0, 200, 0.47, 0.33, "#fff", 0.10)

    assert 'stroke="#f4f7fa"' not in zonder
    assert 'stroke="#f4f7fa"' in met
