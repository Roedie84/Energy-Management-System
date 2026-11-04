"""v5.185.0: het saldo van een afgesloten dag gaat niet meer verloren.

Onderzoek 04-11 19:44 (Ruud: "Kloppen alle kosten/besparings waardes?"): de
besparing per periode gaf maand 11,07 EUR en week 19,29 EUR, terwijl de
besparingssensor deze maand -0,26 EUR (ongecorrigeerd) zegt. De dagstand
bewaarde het saldo onder `kosten_eur` en geen `netto_eur`; het afsluiten viel
voor `netto_eur` terug op de live teller, die al op nul stond. De besparing
per dag (zonder sturing - saldo) werd zo de hele rekening zonder accu.
"""
from pathlib import Path

import custom_components.energy_management_system as pkg


def test_herstel_van_oude_dagregels(make_coordinator):
    c = make_coordinator({})
    c.energy_daily_history = [
        {"datum": "2026-11-01", "kosten_eur": 3.62, "netto_eur": 0.0, "zonder_sturing_eur": 3.05,
         "inkoop_eur": 3.90, "teruglever_eur": 0.21},
        {"datum": "2026-11-02", "kosten_eur": 4.10, "netto_eur": 4.12, "zonder_sturing_eur": 4.0,
         "dagregel_v5185": True},
        {"datum": "2024-08-30", "kosten_eur": 1.5},   # ingelezen dag: blijft
    ]
    c._migreer_dagreeks_kosten()
    a, b, ingelezen = c.energy_daily_history
    assert a["netto_eur"] == 3.62 and a["kosten_eur"] == 3.90 and a["dagregel_v5185"]
    assert b["netto_eur"] == 4.12 and b["kosten_eur"] == 4.10
    assert ingelezen == {"datum": "2024-08-30", "kosten_eur": 1.5}
    c._migreer_dagreeks_kosten()                  # tweede keer: niets meer
    assert a["netto_eur"] == 3.62


def test_dagstand_draagt_saldo_en_meter():
    code = (Path(pkg.__file__).parent / "coordinator.py").read_text(encoding="utf-8")
    assert '"kosten_eur": self._kosten_vandaag_uit_meter(),\n            "netto_eur": self.actual_cost_today_eur,' in code
    assert '("netto_eur", "Saldo", "EUR"),' in code


def test_cockpit_week_en_maand_als_saldo():
    js = (Path(pkg.__file__).parent / "www" / "ems-cockpit.js").read_text(encoding="utf-8")
    assert "num(week.netto_eur) ?? num(week.kosten_eur)" in js
    assert "num(maand.netto_eur) ?? num(maand.kosten_eur)" in js
