"""De smart_charging-proef rekent met een prijs uit het verleden (v3.93.0).

Gemeld: "deze proef wil ik nog eens herzien, smart_charging zou ik
vooral overdag tijdens PV verwachten".

Uit de kaart van 31 augustus:

    Kwartieren met een tekort      20 van 54
    Waarvan het net goedkoper was   0
    Duurste prijs vandaag          38,3 ct   (om 19:45)
    Waard om vast te houden        20,2 ct/kWh

De twintig rijen lopen van 19:00 tot 23:45. Overdag staat er niets, en
dat is precies wat er nagekeken moest worden.

Drie dingen kloppen niet.

1. `waarde_later` gebruikt de duurste prijs uit de HELE tabel, ook als
   die al voorbij is. Voor het kwartier van 23:45 wordt gerekend met de
   38,3 ct van 19:45 - vier uur eerder. Je kunt geen energie vasthouden
   om hem eerder te verkopen. De uitkomst wordt daardoor stelselmatig te
   gunstig voor smart_charging.

2. `uit_accu_kosten_ct` en `uit_net_kosten_ct` zijn allebei
   `prijs * tekort`, dus letterlijk hetzelfde getal. Een vergelijking
   van iets met zichzelf.

3. Er staat niets overdag omdat `tekort = verbruik - zon` rekent met de
   VOORSPELDE zon. Op 30 augustus zei die 10,78 kWh en werd het 6,04 -
   44% ernaast. Op zo'n dag waren er overdag wel degelijk kwartieren
   waarin het huis aan het net hing, en de proef laat er geen enkele
   zien. De tabel meet dus de voorspelling, niet de dag.
"""
from datetime import datetime, timezone

import pytest

NU = datetime(2026, 8, 31, 10, 30, tzinfo=timezone.utc)


def _plan(rijen):
    """(van, prijs_ct, zon_kwh, verbruik_kwh)"""
    return [
        {
            "van": van,
            "prijs_ct": prijs,
            "zon_kwh": zon,
            "verbruik_kwh": verbruik,
        }
        for van, prijs, zon, verbruik in rijen
    ]


def _proef(c, monkeypatch, rijen, rendement=83.9, slijtage=11.9):
    """`learned_battery_efficiency_percent` is een property op de KLASSE.

    Die met de hand overschrijven lekt naar elke volgende toets in de
    hele verzameling - dat gebeurde hier ook, en het viel pas op in de
    volledige run. Via monkeypatch wordt hij netjes teruggezet.
    """
    c.get_quarter_plan = lambda now=None: _plan(rijen)
    monkeypatch.setattr(
        type(c),
        "learned_battery_efficiency_percent",
        property(lambda self: rendement),
    )
    c.get_wear_cost_overview = lambda: {"slijtage_ct_per_kwh": slijtage}
    return c.get_smart_charging_proefplanning(NU)


# --- 1. de piek moet nog komen ----------------------------------------


def test_een_piek_die_voorbij_is_telt_niet_mee(make_coordinator, hass, monkeypatch):
    """Het geval uit de kaart: 38,3 ct om 19:45, en daarna nog vier uur

    goedkopere kwartieren die met die 38,3 rekenden.
    """
    c = make_coordinator({})
    uitkomst = _proef(
        c,
        monkeypatch,
        [
            ("19:45", 38.3, 0.019, 0.085),
            ("23:45", 30.6, 0.0, 0.067),
        ],
    )

    piekrij = uitkomst["rijen"][0]

    # Op 19:45 stond de duurste prijs van de tabel. Vasthouden kan dan
    # alleen nog tot 23:45, en dat is 30,6 ct: 30,6 * 0,839 - 11,9.
    assert piekrij["hoogste_prijs_hierna_ct"] == 30.6
    assert piekrij["waarde_later_ct_per_kwh"] == pytest.approx(13.8, abs=0.2)


def test_de_laatste_rij_kan_niets_meer_vasthouden(make_coordinator, hass, monkeypatch):
    """Na het laatste kwartier komt er geen prijs meer, dus is

    vasthouden per definitie niets waard.
    """
    c = make_coordinator({})
    uitkomst = _proef(c, monkeypatch, [("23:45", 30.6, 0.0, 0.067)])

    assert uitkomst["rijen"][-1]["smart_charging_beter"] is False
    assert uitkomst["rijen"][-1]["waarde_later_ct_per_kwh"] == 0.0


def test_een_piek_die_nog_komt_telt_wel(make_coordinator, hass, monkeypatch):
    """De rem zit op prijzen uit het verleden, niet op de proef zelf."""
    c = make_coordinator({})
    uitkomst = _proef(
        c,
        monkeypatch,
        [
            ("14:00", 5.0, 0.0, 0.100),
            ("19:45", 60.0, 0.0, 0.100),
        ],
    )

    eerste = uitkomst["rijen"][0]

    assert eerste["smart_charging_beter"] is True
    assert eerste["voordeel_eur"] > 0


# --- 2. geen vergelijking van iets met zichzelf ------------------------


def test_er_staan_geen_twee_gelijke_kosten_meer_in(make_coordinator, hass, monkeypatch):
    """`uit_accu_kosten_ct` en `uit_net_kosten_ct` waren allebei

    `prijs * tekort`.
    """
    c = make_coordinator({})
    rij = _proef(c, monkeypatch, [("20:00", 34.8, 0.0, 0.094)])["rijen"][0]

    assert "uit_accu_kosten_ct" not in rij
    assert "uit_net_kosten_ct" not in rij
    assert rij["kosten_nu_ct"] == pytest.approx(34.8 * 0.094, abs=0.01)


# --- 3. overdag ontbreekt omdat de voorspelling dat zegt --------------


def test_de_proef_meldt_hoeveel_kwartieren_op_de_zon_leunen(
    make_coordinator, hass, monkeypatch
):
    """De tabel toont alleen kwartieren met een tekort. Dat er overdag

    niets staat, is een UITKOMST van de zonvoorspelling en geen
    eigenschap van smart_charging - en dat hoort erbij te staan.
    """
    c = make_coordinator({})
    uitkomst = _proef(
        c,
        monkeypatch,
        [
            ("12:00", 12.0, 0.400, 0.090),
            ("13:00", 11.0, 0.380, 0.090),
            ("20:00", 34.8, 0.0, 0.094),
        ],
    )

    assert uitkomst["kwartieren_gedekt_door_zon"] == 2
    assert "VOORSPELDE zon" in uitkomst["toelichting"]


def test_de_duurste_prijs_heet_niet_meer_van_vandaag(make_coordinator, hass, monkeypatch):
    """De tabel loopt zover als er prijzen zijn, tot in de nacht en soms

    tot morgen. "Duurste prijs vandaag" klopte dus niet.
    """
    c = make_coordinator({})
    uitkomst = _proef(c, monkeypatch, [("20:00", 34.8, 0.0, 0.094)])

    assert "duurste_prijs_ct" in uitkomst
    assert uitkomst["duurste_prijs_venster_ct"] == 34.8
