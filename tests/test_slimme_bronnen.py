"""Toetsen voor de rekenlogica van de nieuwe bronnen (v5.14).

Met de getallen die live in Home Assistant stonden op 21 september:

    Gas tegen dagprijzen          1,7427 euro/m3
    Stroom (kwartier)             0,2371 euro/kWh
    Straling (Groenlo-Hupsel)     284 W/m2
    Solcast vandaag               14,0 kWh  (18 sep)
    Forecast.Solar vandaag        9,4 kWh   (21 sep)
    Ventilatoren Thuisaccu        325 kWh op de teller
"""
import pytest

from custom_components.energy_management_system import slimme_bronnen as sb


# --- verwarmen ----------------------------------------------------------


def test_bij_de_prijzen_van_21_september_wint_de_airco():
    """Gas 1,74 per m3, stroom 0,237: warmte uit gas kost ongeveer 0,20
    per kWh, uit de airco ongeveer 0,08."""
    uit = sb.verwarmingsadvies(1.7427, 0.2371, buiten_c=12.0)

    assert uit["advies"] == "airco"
    assert uit["gas_eur_per_kwh_warmte"] == pytest.approx(0.198, abs=0.002)
    assert uit["airco_eur_per_kwh_warmte"] < 0.1
    assert uit["omslag_stroomprijs_eur"] > 0.6


def test_bij_een_extreem_dure_stroomprijs_wint_de_cv():
    uit = sb.verwarmingsadvies(1.7427, 1.20, buiten_c=0.0)

    assert uit["advies"] == "cv"


def test_de_cop_daalt_als_het_kouder_wordt():
    assert sb.cop_bij(-5) < sb.cop_bij(5) < sb.cop_bij(15)
    assert sb.COP_MIN <= sb.cop_bij(-40) and sb.cop_bij(40) <= sb.COP_MAX


def test_zonder_gasprijs_geen_advies():
    assert sb.verwarmingsadvies(None, 0.24, 10.0)["advies"] is None


# --- twee zonvoorspellingen ---------------------------------------------


def test_onenigheid_ten_opzichte_van_het_midden():
    # 14,0 tegen 9,4: 4,6 verschil op een midden van 11,7
    assert sb.oneens_procent(14.0, 9.4) == pytest.approx(39.3, abs=0.1)
    assert sb.oneens_procent(None, 9.4) is None


def test_te_weinig_dagen_geeft_geen_oordeel():
    uit = sb.pv_ensemble_analyse(
        [{"solcast_kwh": 10, "tweede_kwh": 9, "werkelijk_kwh": 8}] * 3
    )

    assert uit["dagen"] == 3
    assert "te weinig" in uit["oordeel"].lower()


def test_de_betere_voorspelling_wordt_herkend():
    dagen = [
        {"solcast_kwh": 14.0, "tweede_kwh": 10.0, "werkelijk_kwh": 10.0},
        {"solcast_kwh": 12.0, "tweede_kwh": 9.0, "werkelijk_kwh": 9.2},
    ] * 4

    uit = sb.pv_ensemble_analyse(dagen)

    assert uit["beste"] == "tweede"


def test_onenigheid_als_teken_van_een_onzekere_dag():
    """Waar het om gaat: zijn ze het oneens, zit Solcast er dan verder
    naast? Dan is onenigheid bruikbaar voor de reserve."""
    eens = [{"solcast_kwh": 10.0, "tweede_kwh": 10.2, "werkelijk_kwh": 10.1}] * 5
    oneens = [{"solcast_kwh": 14.0, "tweede_kwh": 8.0, "werkelijk_kwh": 3.0}] * 4

    uit = sb.pv_ensemble_analyse(eens + oneens)

    assert uit["onenigheid_voorspelt_fout"] is True


# --- instraling ---------------------------------------------------------


def test_alleen_bruikbare_momenten_tellen():
    assert sb.instraling_telt(284, 31.0, 1383)
    assert not sb.instraling_telt(80, 31.0, 300)       # te weinig licht
    assert not sb.instraling_telt(284, 5.0, 300)       # zon te laag
    assert not sb.instraling_telt(None, 31.0, 300)


def test_azimutvakken():
    assert sb.azimut_vak(222.08) == 220
    assert sb.azimut_vak(271.8) == 260


def test_een_richting_die_achterblijft_bij_gemeten_licht():
    """De bestaande analyse zei: west haalt 16% van de verwachting. Maar die
    verwachting is een voorspelling. Tegen gemeten licht wordt het hard."""
    verhoudingen = {
        "180": [5.0] * 30,   # zuid: 5 W per W/m2
        "260": [1.0] * 30,   # west: 1 W per W/m2 - 20% van zuid
    }

    uit = sb.instraling_analyse(verhoudingen)

    assert uit["vakken"][180]["procent_van_beste"] == 100.0
    assert uit["vakken"][260]["procent_van_beste"] == 20.0
    assert 260 in uit["zwakke_richtingen"]


def test_te_weinig_metingen_geeft_geen_oordeel():
    uit = sb.instraling_analyse({"180": [5.0] * 3})

    assert uit["vakken"] == {}


# --- ventilatoren -------------------------------------------------------


def test_het_ventilatorverbruik_wordt_zichtbaar():
    """325 kWh op de teller, en de koellogica sprak van "een paar watt"."""
    uit = sb.ventilator_overzicht(
        {"2026-09-20": 0.48, "2026-09-21": 0.52}, [40.0, 41.0, 39.0], 0.24
    )

    assert uit["gemiddeld_kwh_per_dag"] == pytest.approx(0.5)
    assert uit["vermogen_aan_w"] == 40.0
    assert uit["kosten_eur_per_jaar"] == pytest.approx(43.8, abs=0.1)
