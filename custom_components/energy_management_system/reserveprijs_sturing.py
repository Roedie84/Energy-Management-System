"""Tweede prijsbron (v5.251.0): de lijm tussen de coordinator en `reserveprijs.py`.

- Eens per uur (bij een storing van de prijsbron elk kwartier) de
  kwartierprijzen van vandaag en morgen bij EnergyZero ophalen, op de
  achtergrond; alleen als die integratie is ingesteld.
- Zolang Zonneplan levert: per kwartier het verschil leren.
- Valt Zonneplan weg, dan vult `_forecast_met_cache` de bewaarde reeks aan
  met de reserve (Zonneplan-formaat, geleerde opslag erbij).

Stuurt zelf niets en schrijft nergens heen.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util

from . import reserveprijs as rp
from .const import CONF_PRICE_SENSOR

_LOGGER = logging.getLogger(__name__)

RESERVE_DOMEIN = "energyzero"
#: Normaal eens per uur; tijdens een storing van de prijsbron elk kwartier.
RESERVE_VERVERS_S = 3600
RESERVE_VERVERS_STORING_S = 900


class ReserveprijsMixin:
    reserveprijs: dict | None = None
    reserveprijs_verschillen: dict | None = None
    _reserveprijs_bezig: bool = False
    _reserveprijs_gehaald: datetime | None = None
    _reserveprijs_fout: str | None = None
    _reserveprijs_in_gebruik: bool = False

    def _reserveprijs_entry_id(self) -> str | None:
        hass = getattr(self, "hass", None)
        beheer = getattr(hass, "config_entries", None)
        if beheer is None:
            return None
        try:
            for entry in beheer.async_entries(RESERVE_DOMEIN):
                if getattr(entry, "disabled_by", None) is None:
                    return entry.entry_id
        except Exception:  # noqa: BLE001
            return None
        return None

    def _reserveprijs_kwartier(self, now: datetime) -> None:
        """Haak op de kwartiergrens."""
        if self._reserveprijs_bezig:
            return
        entry_id = self._reserveprijs_entry_id()
        if entry_id is None:
            return
        storing = getattr(self, "_prijsbron_weg_sinds", None) is not None
        laatst = self._reserveprijs_gehaald
        wacht = RESERVE_VERVERS_STORING_S if storing else RESERVE_VERVERS_S
        if laatst is not None and (now - laatst).total_seconds() < wacht - 30:
            return
        maker = getattr(self.hass, "async_create_background_task", None)
        if maker is None:
            return
        self._reserveprijs_bezig = True
        self._reserveprijs_gehaald = now
        maker(self._async_reserveprijs_halen(entry_id, now), "ems_reserveprijs")

    async def _async_reserveprijs_halen(self, entry_id: str, now: datetime) -> None:
        try:
            begin = dt_util.as_local(now).replace(hour=0, minute=0, second=0, microsecond=0)
            # v5.251.1: per dag vragen, tot 23:59. Een vraag die morgen raakt
            # terwijl die prijzen er nog niet zijn, wordt in zijn geheel
            # geweigerd ("No price data available"); ook een eind op 00:00
            # telt als de volgende dag. Morgen is dus een losse, vrijblijvende vraag.
            antwoord = {"prices": []}
            for dag in (0, 1):
                van = begin + timedelta(days=dag)
                try:
                    deel = await self.hass.services.async_call(
                        RESERVE_DOMEIN, "get_energy_prices",
                        {"config_entry": entry_id, "incl_vat": True, "interval": "quarter",
                         "start": van.strftime("%Y-%m-%d %H:%M:%S"),
                         "end": van.strftime("%Y-%m-%d 23:59:00")},
                        blocking=True, return_response=True,
                    )
                except Exception:  # noqa: BLE001
                    if dag == 0:
                        raise
                    break       # morgen is nog niet gepubliceerd
                antwoord["prices"].extend((deel or {}).get("prices") or [])
            reeks = rp.lees_energyzero(antwoord)
            if reeks:
                self.reserveprijs = {"om": dt_util.now().isoformat(), "reeks": reeks}
                self._reserveprijs_fout = None
                self._reserveprijs_leren()
                self.schedule_persisted_state_save()
            else:
                self._reserveprijs_fout = "geen prijzen in het antwoord"
        except Exception as fout:  # noqa: BLE001 - een reservebron mag het EMS nooit raken
            self._reserveprijs_fout = f"{type(fout).__name__}: {fout}"
            _LOGGER.debug("Reserveprijzen niet opgehaald", exc_info=True)
        finally:
            self._reserveprijs_bezig = False

    def _reserveprijs_leren(self) -> None:
        """Alleen uit de LEVENDE Zonneplan-reeks, nooit uit de bewaarde."""
        sensor = self.config.get(CONF_PRICE_SENSOR)
        staat = self.hass.states.get(sensor) if sensor else None
        live = staat.attributes.get("forecast") if staat is not None else None
        if not live:
            return
        self.reserveprijs_verschillen = rp.leer_verschillen(
            self.reserveprijs_verschillen, live, (self.reserveprijs or {}).get("reeks") or [])

    def reserveprijs_aanvullen(self, reeks: list, alleen_schatting: bool = False) -> list:
        """De reeks (bewaard of geschat) aangevuld met de reserve. Bij een
        schatting uit de prijsgeschiedenis gaat de reserve voor: dat zijn
        echte prijzen."""
        geleerd = rp.opslag(self.reserveprijs_verschillen)
        if geleerd is None or not self.reserveprijs:
            self._reserveprijs_in_gebruik = False
            return reeks
        items = rp.als_zonneplan(self.reserveprijs.get("reeks") or [], geleerd, dt_util.now())
        uit = rp.vul_aan([] if alleen_schatting else reeks, items)
        if alleen_schatting and items:
            uit = rp.vul_aan(uit, reeks)
        self._reserveprijs_in_gebruik = len(uit) > len(reeks or []) or (alleen_schatting and bool(items))
        return uit

    def get_reserveprijs(self) -> dict:
        reeks = (self.reserveprijs or {}).get("reeks") or []
        return {
            "bron": RESERVE_DOMEIN if self._reserveprijs_entry_id() else "niet ingesteld",
            "opgehaald": (self.reserveprijs or {}).get("om"),
            "kwartieren": len(reeks),
            "tot": reeks[-1]["eind"] if reeks else None,
            "opslag": rp.opslag(self.reserveprijs_verschillen),
            "geleerde_kwartieren": len(self.reserveprijs_verschillen or {}),
            "in_gebruik": self._reserveprijs_in_gebruik,
            "fout": self._reserveprijs_fout,
        }
