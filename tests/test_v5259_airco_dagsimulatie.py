"""v5.259.0: een hele dag van de airco-automaat naspelen (Ruud 25-11, akkoord).

Op 24-11 gingen negen releases de deur uit met twee fouten die pas in huis
opvielen: de knop 'iedereen weg' deed niets op een zelf aangezette airco
(v5.255.0) en de airco ging om 04:24 aan tot 21 °C (v5.253.0-v5.258.0). De
losse tests waren groen. Deze test speelt per minuut een etmaal na door de
echte ronde (`_airco_ronde`), voert de besluiten uit op een nagebootste airco
en kamer, en legt vast wanneer de airco aan en uit gaat en op welk doel.

De instellingen zijn die van Ruud op 25-11: 22:00 uit, werkdagochtend niet
voor 06:30 tot 19 °C, overdag 21 °C, knop 'iedereen weg'.
"""
from datetime import datetime, timedelta, timezone

import pytest

TZ = timezone(timedelta(hours=1))
AIRCO = "climate.woonkamer"
KNOP = "input_boolean.iedereen_weg"
INSTELLINGEN = {
    "airco_climate_entity": AIRCO,
    "slaapkamer_climate_entity": "climate.slaapkamer",
    "airco_uit_om": "22:00",
    "airco_werkdag_warm_om": "07:00",
    "airco_werkdag_aan_om": "06:30",
    "airco_middag_doel_c": 21.0,
    "airco_nacht_c": 0.0,
    "afwezig_knop_entity": KNOP,
}


class Huis:
    """De coordinator met een nagebootste airco, kamer en bewoners."""

    def __init__(self, make_coordinator, hass, begin: datetime, kamer_c: float, aanwezigheid, knop=None,
                 instellingen=None):
        c = make_coordinator(dict(INSTELLINGEN))
        c.config = dict(c.config or {}, **INSTELLINGEN)
        c.airco_automaat_aan = True
        c.get_verwarmingsadvies = lambda: {"advies": "airco"}
        c.get_airco_kansen_per_bakje = lambda: {
            "bakjes": {"19.0": {"probability_percent": 80, "richting": "verwarmen", "voldoende_data": True}}
        }
        c.airco_setpunten = [21.0] * 6
        self.opdrachten: list = []
        hass.async_create_task = self._voer_uit
        hass.states.set(AIRCO, "off", {"temperature": 21.0})
        hass.states.set(KNOP, "off", {})
        self.c, self.hass, self.nu, self.kamer = c, hass, begin, kamer_c
        self.aanwezigheid, self.knop, self.instellingen = aanwezigheid, knop or (lambda t: False), instellingen
        self.log: list = []          # (tijd, stand, doel) bij elke verandering

    def _voer_uit(self, coro):
        coro.close()
        besluit = self.c.last_airco_besluit
        if besluit["actie"] == "verwarmen":
            self.hass.states.set(AIRCO, "heat", {"temperature": besluit["doel_c"]})
            self.c._airco_laatste_ems = {
                "stand": "heat", "doel": besluit["doel_c"],
                "basis": besluit.get("basis_doel_c", besluit["doel_c"]),
            }
            self.c.airco_door_ems = True
            self.c._airco_geschakeld = ("verwarmen", self.nu)
        elif besluit["actie"] == "uit":
            doel = self.hass.states.get(AIRCO).attributes.get("temperature")
            self.hass.states.set(AIRCO, "off", {"temperature": doel})
            self.c._airco_laatste_ems = {"stand": "off", "doel": doel}
            self.c.airco_door_ems = False
            self.c._airco_geschakeld = ("uit", self.nu)

    def zet_met_de_hand(self, stand: str, doel: float):
        self.hass.states.set(AIRCO, stand, {"temperature": doel})

    def stand(self):
        t = self.hass.states.get(AIRCO)
        return t.state, t.attributes.get("temperature")

    def minuut(self):
        if self.instellingen:
            self.c.config.update(self.instellingen(self.nu) or {})
        knop = self.knop(self.nu)
        self.hass.states.set(KNOP, "on" if knop else "off", {})
        self.c.presence_state = "weg" if knop else self.aanwezigheid(self.nu)
        stand, doel = self.stand()
        # de kamer: 3 graden per uur omhoog tot het doel, anders langzaam naar 15
        if stand == "heat" and self.kamer < doel:
            self.kamer = min(doel, self.kamer + 3.0 / 60)
        else:
            self.kamer = max(15.0, self.kamer - 0.4 / 60)
        self.c.living_room_current_temp_c = round(self.kamer, 2)
        voor = self.stand()
        self.c._airco_ronde(self.nu)
        na = self.stand()
        if na != voor:
            self.log.append((self.nu.strftime("%H:%M"), na[0], na[1], self.c.last_airco_besluit["tekst"]))
        self.nu += timedelta(minutes=1)

    def speel_tot(self, eind: datetime):
        while self.nu < eind:
            self.minuut()
        return self


def _tussen(log, van: str, tot: str):
    return [r for r in log if van <= r[0] < tot]


def _werkdag_aanwezigheid(t: datetime) -> str:
    """Di 24 -> wo 25-11: slapen vanaf 23:00, om 04:20 even beneden, om 06:15
    op, om 08:30 de deur uit, om 13:00 weer thuis."""
    m = t.hour * 60 + t.minute
    if t.day == 24:
        return "thuis" if m < 23 * 60 else "slaapt"
    if m < 4 * 60 + 20:
        return "slaapt"
    if m < 4 * 60 + 40:
        return "thuis"
    if m < 6 * 60 + 15:
        return "slaapt"
    if m < 8 * 60 + 30:
        return "thuis"
    if m < 13 * 60:
        return "weg"
    return "thuis" if m < 23 * 60 else "slaapt"


@pytest.fixture
def werkdag(make_coordinator, hass):
    huis = Huis(make_coordinator, hass, datetime(2026, 11, 24, 21, 0, tzinfo=TZ), 20.5, _werkdag_aanwezigheid,
                knop=lambda t: t.day == 25 and 15 * 60 <= t.hour * 60 + t.minute < 15 * 60 + 30,
                instellingen=lambda t: {"airco_middag_doel_c": 20.0} if t.day == 25 and t.hour >= 17 else None)
    # 's avonds verwarmt het EMS al: aan op 21 °C
    huis.hass.states.set(AIRCO, "heat", {"temperature": 21.0})
    huis.c._airco_laatste_ems = {"stand": "heat", "doel": 21.0, "basis": 21.0}
    huis.c._airco_laatst_gezien = ("heat", 21.0)
    huis.c.airco_door_ems = True
    return huis.speel_tot(datetime(2026, 11, 25, 23, 30, tzinfo=TZ))


def test_om_tien_uur_uit_en_de_hele_nacht_uit(werkdag):
    avond = [r for r in werkdag.log if r[0] >= "21:00"][:1]
    assert avond and avond[0][:2] == ("22:00", "off")
    # 25-11 04:24: iemand beneden en de kamer onder de 19,5 °C - de airco blijft uit
    nacht = _tussen(werkdag.log[1:], "00:00", "06:30")
    assert nacht == [], nacht


def test_de_werkdagochtend_begint_om_half_zeven_op_negentien_graden(werkdag):
    ochtend = _tussen(werkdag.log[1:], "06:30", "08:30")
    assert ochtend[0][:3] == ("06:30", "heat", 19.0), ochtend
    # geen halve graad voorverwarmen en niet naar 21 voor elf uur
    assert all(r[2] == 19.0 for r in ochtend), ochtend


def test_weg_blijft_aan_en_gaat_na_twee_uur_naar_achttien(werkdag):
    weg = _tussen(werkdag.log[1:], "08:30", "13:00")
    assert [r[:3] for r in weg] == [("10:30", "heat", 18.0)], weg


def test_thuis_terug_naar_het_dagdoel(werkdag):
    thuis = _tussen(werkdag.log[1:], "13:00", "15:00")
    assert thuis and thuis[0][1:3] == ("heat", 21.0) and thuis[0][0] <= "13:02", thuis


def test_de_knop_iedereen_weg_en_weer_terug(werkdag):
    knop = _tussen(werkdag.log[1:], "15:00", "17:00")
    # v5.263.0: de knop zet de airco uit, en bij terugkomst weer aan
    assert [r[1] for r in knop] == ["off", "heat"] and knop[1][2] == 21.0, knop
    assert knop[0][0] <= "15:02" and "15:30" <= knop[1][0] <= "15:32", knop


def test_een_lager_dagdoel_zet_de_draaiende_airco_lager(werkdag):
    lager = _tussen(werkdag.log[1:], "17:00", "22:00")
    assert lager and lager[0][1:3] == ("heat", 20.0) and lager[0][0] <= "17:02", lager


def test_en_om_tien_uur_weer_uit(werkdag):
    assert werkdag.log[-1][:2] == ("22:00", "off"), werkdag.log[-3:]
    assert werkdag.stand()[0] == "off"


def test_de_knop_werkt_ook_op_een_zelf_aangezette_airco(make_coordinator, hass):
    """v5.255.0: met de hand aangezet (24-11 11:51), knop aan -> er gebeurde niets."""
    huis = Huis(make_coordinator, hass, datetime(2026, 11, 24, 11, 0, tzinfo=TZ), 20.0, lambda t: "thuis",
                knop=lambda t: (13, 36) <= (t.hour, t.minute) < (13, 53))
    huis.speel_tot(datetime(2026, 11, 24, 11, 51, tzinfo=TZ))
    huis.zet_met_de_hand("heat", 23.0)
    huis.speel_tot(datetime(2026, 11, 24, 14, 30, tzinfo=TZ))
    na = [r for r in huis.log if r[0] >= "13:36"]
    assert na and na[0][1] == "off" and na[0][0] <= "13:38", huis.log
    assert any(r[0] >= "13:53" and r[1] == "heat" for r in na), na


def test_in_het_weekend_geen_ingestelde_ochtend(make_coordinator, hass):
    huis = Huis(make_coordinator, hass, datetime(2026, 11, 28, 0, 0, tzinfo=TZ), 17.0,
                lambda t: "slaapt" if t.hour < 8 else "thuis")
    huis.speel_tot(datetime(2026, 11, 28, 10, 59, tzinfo=TZ))
    assert huis.log == [], huis.log


def test_voorverwarmen_overdag_wel_en_in_de_ochtend_niet(make_coordinator, hass):
    """25-11 06:30: 19,5 °C in plaats van 19 (Ruud: "we hadden toch 19 afgesproken")."""
    from custom_components.energy_management_system.const import PRICE_SCALE_FACTOR

    huis = Huis(make_coordinator, hass, datetime(2026, 11, 25, 5, 0, tzinfo=TZ), 16.5,
                lambda t: "slaapt" if (t.hour, t.minute) < (6, 15) else "thuis")
    # nu 40 ct, de komende uren 55 ct: het EMS wil dan een halve graad extra
    huis.c.huidige_prijs_eur_per_kwh = lambda now: 0.40
    huis.c._get_forecast_entries = lambda: [
        (huis.nu + timedelta(minutes=30 * k), huis.nu + timedelta(minutes=30 * k + 15), 0.55 * PRICE_SCALE_FACTOR)
        for k in range(1, 6)
    ]
    huis.speel_tot(datetime(2026, 11, 25, 12, 0, tzinfo=TZ))
    ochtend = _tussen(huis.log, "06:30", "11:00")
    assert ochtend and all(r[2] == 19.0 for r in ochtend), ochtend
    dag = _tussen(huis.log, "11:00", "12:00")
    assert dag and dag[0][2] == 21.5, huis.log


def _herstart(huis):
    """Home Assistant herstart: alleen wat bewaard wordt blijft over."""
    from custom_components.energy_management_system.const import PERSISTED_PLAIN_FIELDS

    assert "_airco_laatste_ems" in PERSISTED_PLAIN_FIELDS and "airco_door_ems" in PERSISTED_PLAIN_FIELDS
    huis.c._airco_laatst_gezien = None
    huis.c._airco_handmatig_bij = None
    huis.c._airco_geschakeld = None


def test_na_een_herstart_gaat_de_ochtendairco_toch_naar_het_dagdoel(make_coordinator, hass):
    """25-11: herstart 10:57, de airco bleef tot 15:53 op 19 staan (Ruud: "nu nog 19?")."""
    huis = Huis(make_coordinator, hass, datetime(2026, 11, 25, 5, 0, tzinfo=TZ), 16.5,
                lambda t: "slaapt" if (t.hour, t.minute) < (6, 15) else "thuis")
    huis.speel_tot(datetime(2026, 11, 25, 10, 57, tzinfo=TZ))
    assert huis.stand() == ("heat", 19.0), huis.log
    _herstart(huis)
    huis.speel_tot(datetime(2026, 11, 25, 12, 0, tzinfo=TZ))
    assert huis.stand() == ("heat", 21.0), huis.log
    assert [r[0] for r in huis.log if r[2] == 21.0][0] <= "11:02", huis.log


def test_na_een_herstart_blijft_een_zelf_verzette_airco_staan(make_coordinator, hass):
    """Tijdens de herstart met de afstandsbediening op 23 gezet: dat blijft."""
    huis = Huis(make_coordinator, hass, datetime(2026, 11, 25, 5, 0, tzinfo=TZ), 16.5,
                lambda t: "slaapt" if (t.hour, t.minute) < (6, 15) else "thuis")
    huis.speel_tot(datetime(2026, 11, 25, 10, 57, tzinfo=TZ))
    _herstart(huis)
    huis.zet_met_de_hand("heat", 23.0)
    huis.speel_tot(datetime(2026, 11, 25, 12, 0, tzinfo=TZ))
    assert huis.stand() == ("heat", 23.0), huis.log


def _dag_met_dagdoel_vanaf(make_coordinator, hass, knop=None):
    huis = Huis(make_coordinator, hass, datetime(2026, 11, 25, 5, 0, tzinfo=TZ), 16.5, _werkdag_aanwezigheid,
                knop=knop, instellingen=lambda t: {"airco_middag_vanaf": "16:00"})
    return huis.speel_tot(datetime(2026, 11, 25, 23, 0, tzinfo=TZ))


def test_het_dagdoel_pas_vanaf_vier_uur(make_coordinator, hass):
    """Ruud 25-11: "om 16:00 pas naar 21 is prima" - tot die tijd 19."""
    huis = _dag_met_dagdoel_vanaf(make_coordinator, hass)
    voor = _tussen(huis.log, "06:30", "16:00")
    assert voor and all(r[2] <= 19.0 for r in voor if r[1] == "heat"), huis.log
    thuis = _tussen(huis.log, "13:00", "16:00")
    assert thuis and thuis[0][1:3] == ("heat", 19.0), huis.log      # terug van 18 naar 19, niet 21
    om_vier = _tussen(huis.log, "16:00", "22:00")
    assert om_vier and om_vier[0][1:3] == ("heat", 21.0) and om_vier[0][0] <= "16:02", huis.log
    assert huis.stand()[0] == "off"


def test_om_vier_uur_niet_omhoog_met_de_knop_iedereen_weg(make_coordinator, hass):
    """Ruud: "tenzij de knop niet thuis uiteraard wordt ingedrukt"."""
    huis = _dag_met_dagdoel_vanaf(
        make_coordinator, hass, knop=lambda t: (15, 30) <= (t.hour, t.minute) < (17, 0))
    knop = _tussen(huis.log, "15:30", "17:00")
    assert knop and all(r[2] <= 19.0 for r in knop), huis.log
    na = _tussen(huis.log, "17:00", "22:00")
    assert na and na[0][1:3] == ("heat", 21.0) and na[0][0] <= "17:02", huis.log


def test_zonder_dagdoel_vanaf_blijft_het_elf_uur(make_coordinator, hass):
    huis = Huis(make_coordinator, hass, datetime(2026, 11, 25, 5, 0, tzinfo=TZ), 16.5,
                lambda t: "slaapt" if (t.hour, t.minute) < (6, 15) else "thuis")
    huis.speel_tot(datetime(2026, 11, 25, 12, 0, tzinfo=TZ))
    assert [r[0] for r in huis.log if r[2] == 21.0][0] <= "11:02", huis.log


def test_de_knop_iedereen_weg_zet_de_airco_uit_en_weer_aan(make_coordinator, hass):
    """Ruud 26-11 08:06: "Airco uit bij indrukken knop aanwezig naar afwezig"."""
    huis = Huis(make_coordinator, hass, datetime(2026, 11, 26, 5, 0, tzinfo=TZ), 16.5,
                lambda t: "slaapt" if (t.hour, t.minute) < (6, 15) else "thuis",
                knop=lambda t: (7, 50) <= (t.hour, t.minute) < (9, 30),
                instellingen=lambda t: {"airco_weg_c": 16.0, "airco_middag_vanaf": "16:00"})
    huis.speel_tot(datetime(2026, 11, 26, 10, 30, tzinfo=TZ))
    weg = _tussen(huis.log, "07:50", "09:30")
    assert [r[1] for r in weg] == ["off"] and weg[0][0] <= "07:52", huis.log
    terug = _tussen(huis.log, "09:30", "10:30")
    assert terug and terug[0][1:3] == ("heat", 19.0) and terug[0][0] <= "09:32", huis.log
    assert huis.c.airco_knop_uit is False and huis.c.airco_knop_sinds is None


def test_met_de_knop_aan_gaat_de_ochtend_niet_van_start(make_coordinator, hass):
    huis = Huis(make_coordinator, hass, datetime(2026, 11, 26, 5, 0, tzinfo=TZ), 16.5,
                lambda t: "slaapt", knop=lambda t: True)
    huis.speel_tot(datetime(2026, 11, 26, 12, 0, tzinfo=TZ))
    assert huis.log == [], huis.log


def test_zelf_aangezet_na_de_knop_blijft_staan(make_coordinator, hass):
    huis = Huis(make_coordinator, hass, datetime(2026, 11, 26, 5, 0, tzinfo=TZ), 16.5,
                lambda t: "slaapt" if (t.hour, t.minute) < (6, 15) else "thuis",
                knop=lambda t: (7, 50) <= (t.hour, t.minute) < (10, 0))
    huis.speel_tot(datetime(2026, 11, 26, 8, 30, tzinfo=TZ))
    assert huis.stand()[0] == "off"
    huis.zet_met_de_hand("heat", 22.0)
    huis.speel_tot(datetime(2026, 11, 26, 9, 30, tzinfo=TZ))
    assert huis.stand() == ("heat", 22.0), huis.log


def test_langer_dan_twee_uur_weg_op_de_ingestelde_temperatuur(make_coordinator, hass):
    """Zonder knop: na twee uur weg naar de ingestelde 16 graden, niet uit."""
    huis = Huis(make_coordinator, hass, datetime(2026, 11, 26, 5, 0, tzinfo=TZ), 16.5,
                lambda t: "slaapt" if (t.hour, t.minute) < (6, 15) else ("thuis" if t.hour < 8 else "weg"),
                instellingen=lambda t: {"airco_weg_c": 16.0})
    huis.speel_tot(datetime(2026, 11, 26, 10, 30, tzinfo=TZ))
    weg = _tussen(huis.log, "08:00", "10:30")
    assert [r[1:3] for r in weg] == [("heat", 16.0)] and "10:00" <= weg[0][0] <= "10:02", huis.log


def test_zonder_instelling_blijft_weg_achttien(make_coordinator, hass):
    c = make_coordinator({})
    assert c._airco_weg_c() == 18.0
    c.config = dict(c.config or {}, airco_weg_c=30)
    assert c._airco_weg_c() == 18.0


def test_wie_de_airco_bediende_wordt_vastgelegd(make_coordinator, hass):
    """v5.263.0: het EMS zette hem aan, daarna iemand met de afstandsbediening."""
    huis = Huis(make_coordinator, hass, datetime(2026, 11, 26, 5, 0, tzinfo=TZ), 16.5,
                lambda t: "slaapt" if (t.hour, t.minute) < (6, 15) else "thuis")
    huis.speel_tot(datetime(2026, 11, 26, 8, 0, tzinfo=TZ))
    huis.zet_met_de_hand("heat", 23.0)
    huis.speel_tot(datetime(2026, 11, 26, 8, 5, tzinfo=TZ))
    regels = huis.c.airco_wijzigingen
    assert [r["oorzaak"] for r in regels] == ["ems", "apparaat"], regels
    assert regels[0]["naar"] == ["heat", 19.0] and regels[1]["naar"] == ["heat", 23.0], regels
    assert huis.stand() == ("heat", 23.0)       # de sturing zelf is niet veranderd
