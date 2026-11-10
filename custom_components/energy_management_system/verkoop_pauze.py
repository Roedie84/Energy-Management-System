"""Knop "Verkopen uit" (v5.207.0).

Gevraagd 10-11 (Ruud): "Ik weet dat de oven nog een paar keer aan moet,
kunnen we een knop bouwen waarmee ik zeg dat verkopen niet toegestaan is?
Deze moet dagelijks resetten en het plan moet er rekening mee houden."

Aan = tot middernacht (lokale tijd) van de dag waarop hij aanging. In die
periode:
- mag het waardeplan in geen enkel kwartier uit de accu het net op leveren
  (`Kwartier.verkoop_verboden`); de accu blijft dus voor het huis, en het
  plan herverdeelt de lading over de dure kwartieren van het huis zelf;
- zegt de verkooptoets van de oude regels (terugval als het plan er niet is)
  ook nee.
Netladen, zon opslaan en het huis dekken gaan gewoon door. Na middernacht
staat de knop vanzelf weer uit (ook na een herstart: de eindtijd wordt
bewaard, niet de aan/uit-stand).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util

VERKOOP_PAUZE_REDEN = "verkopen uitgezet met de knop (tot middernacht)"


def einde_van_de_dag(moment: datetime) -> datetime:
    """Middernacht (lokaal) na `moment`."""
    lokaal = dt_util.as_local(moment)
    morgen = lokaal.date() + timedelta(days=1)
    return datetime.combine(morgen, datetime.min.time(), tzinfo=lokaal.tzinfo)


class VerkoopPauzeMixin:
    """Toestand als klassestandaard (de `__init__` zit aan zijn grens)."""

    verkoop_pauze_tot: str | None = None

    def verkoop_pauze_einde(self, now: datetime | None = None) -> datetime | None:
        """De eindtijd als de knop aan staat, anders None (en opruimen)."""
        if not self.verkoop_pauze_tot:
            return None
        einde = dt_util.parse_datetime(str(self.verkoop_pauze_tot))
        if einde is None or (now or dt_util.now()) >= einde:
            self.verkoop_pauze_tot = None
            return None
        return einde

    def verkoop_pauze_actief(self, now: datetime | None = None) -> bool:
        return self.verkoop_pauze_einde(now) is not None

    def zet_verkoop_pauze(self, aan: bool, now: datetime | None = None) -> None:
        nu = now or dt_util.now()
        self.verkoop_pauze_tot = einde_van_de_dag(nu).isoformat() if aan else None
        # Het plan van dit kwartier staat in de cache; meteen opnieuw rekenen.
        self._waardeplan_cache = None
        try:
            self.schedule_persisted_state_save()
        except Exception:  # noqa: BLE001 - bewaren mag de knop nooit breken
            pass

    async def async_set_verkoop_pauze(self, aan: bool) -> None:
        self.zet_verkoop_pauze(aan)
        await self.async_update()

    def verkoop_verboden_om(self, begin: datetime) -> bool:
        """Mag het plan in het kwartier dat om `begin` start niet verkopen?"""
        einde = self.verkoop_pauze_einde()
        return einde is not None and begin < einde

    def verkoop_pauze_toets(self, toets: dict | None) -> dict:
        """De verkooptoets van de oude regels, met de knop erover."""
        toets = dict(toets or {})
        if self.verkoop_pauze_actief():
            toets["mag_verkopen"] = False
            toets["reden"] = VERKOOP_PAUZE_REDEN
            toets["verkoop_pauze"] = True
        return toets

    def get_verkoop_pauze_status(self, now: datetime | None = None) -> dict:
        einde = self.verkoop_pauze_einde(now)
        if einde is None:
            return {"actief": False}
        return {
            "actief": True,
            "tot": dt_util.as_local(einde).strftime("%d-%m %H:%M"),
            "uitleg": "Geen verkoop uit de accu tot middernacht; het plan houdt de lading voor het huis.",
        }
