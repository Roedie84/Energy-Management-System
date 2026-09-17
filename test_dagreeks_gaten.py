"""De dagreeks vult zijn eigen gaten (v3.32.0)."""
from datetime import date, datetime, timedelta

from custom_components.energy_management_system.coordinator import (
    EnergyManagementSystemCoordinator as C,
)


class _Reeks:
    dagreeks_verwijderd: list = []

    def __init__(self, data, verwijderd=None):
        self.energy_daily_history = [{"datum": d} for d in data]
        self.dagreeks_verwijderd = verwijderd or []

    _ontbrekende_dagen = C._ontbrekende_dagen


def _gaten(data, verwijderd=None, monkeypatch=None, vandaag="2026-08-19"):
    from custom_components.energy_management_system import coordinator as mod

    class _Klok:
        @staticmethod
        def now():
            return datetime.fromisoformat(vandaag + "T12:00:00")

    monkeypatch.setattr(mod, "dt_util", _Klok)
    return _Reeks(data, verwijderd)._ontbrekende_dagen()


def test_the_missing_day_is_found(monkeypatch):
    """16 augustus ontbrak tussen 15 en 17 in, en werd nooit aangevuld:

    de inleesroutine keek alleen naar dagen VOOR de oudste bekende dag,
    en een gat in het midden valt daar per definitie buiten.
    """
    gaten = _gaten(
        ["2026-08-14", "2026-08-15", "2026-08-17", "2026-08-18"],
        monkeypatch=monkeypatch,
    )

    assert gaten == [date(2026, 8, 16)]


def test_a_day_that_was_cleaned_up_is_left_alone(monkeypatch):
    """Opnieuw inlezen zou hem meteen weer weggooien."""
    gaten = _gaten(
        ["2026-08-15", "2026-08-17"],
        verwijderd=[{"datum": "2026-08-16", "reden": "onmogelijk"}],
        monkeypatch=monkeypatch,
    )

    assert gaten == []


def test_today_is_not_a_gap(monkeypatch):
    """Vandaag is nog niet afgesloten."""
    gaten = _gaten(
        ["2026-08-17", "2026-08-18"], monkeypatch=monkeypatch
    )

    assert gaten == []


def test_a_closed_series_has_no_gaps(monkeypatch):
    gaten = _gaten(
        ["2026-08-15", "2026-08-16", "2026-08-17"], monkeypatch=monkeypatch
    )

    assert gaten == []


def test_several_gaps_are_all_reported(monkeypatch):
    gaten = _gaten(
        ["2026-08-10", "2026-08-12", "2026-08-15"], monkeypatch=monkeypatch
    )

    assert gaten == [
        date(2026, 8, 11),
        date(2026, 8, 13),
        date(2026, 8, 14),
    ]


def test_the_bootstrap_reaches_back_to_the_gap():
    """Zonder deze aanpassing haalde de routine alleen dagen op vóór de

    oudste bekende dag - en dan blijft een gat in het midden voorgoed
    weg.
    """
    import inspect

    bron = inspect.getsource(C.async_bootstrap_energy_history)

    assert "_ontbrekende_dagen" in bron


def test_the_gap_day_is_not_filtered_out_again():
    """v3.32.0 verbreedde het ophaalvenster wel, maar de regel die de

    rijen selecteerde bleef `dag < oudste` - en 16 augustus ligt ver ná
    de oudste bekende dag. De dag werd opgehaald en meteen weer
    weggegooid.

    Bewezen door de export van 20 augustus 09:11: 404 meetpunten
    ingelezen, 16 augustus nog steeds weg.
    """
    import inspect

    bron = inspect.getsource(C.async_bootstrap_energy_history)

    assert "if dag < oudste or dag in gaten_set" in bron


def test_a_filled_gap_lands_in_the_right_place():
    """Een bijgehaald gat hoort op zijn eigen plek in de reeks, niet

    vóór de oudste dag: zonder sorteren staat 16 augustus tussen de
    dagen van juli.
    """
    import inspect

    bron = inspect.getsource(C.async_bootstrap_energy_history)

    assert "sorted(" in bron.split("bestaand = {")[1][:400]
