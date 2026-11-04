"""Zuinig schrijven: alleen een nieuwe databaserij bij een echte wijziging (v5.173.0).

Opschoonanalyse 03-11: zo'n dertig EMS-sensoren schreven elke 30 of 60
seconden een nieuwe rij in de database terwijl hun TOESTAND gelijk bleef.
De GACS-zelfbeoordeling stond 30 minuten lang op 17 en schreef in die tijd
61 rijen (~2.900 per dag). Samen ~70.000 rijen per dag; de database was
10,1 GiB en de cloudback-up zat tegen de 5 GB aan.

Waarom `_unrecorded_attributes` dat niet oplost: Home Assistant schrijft
bij ELKE state_changed-gebeurtenis een rij in de tabel `states`. Een
gewijzigd attribuut geeft zo'n gebeurtenis, ook als dat attribuut niet
naar de recorder gaat - alleen de attributenblob wordt dan ontdubbeld.
Een rij wordt pas overgeslagen als toestand EN attributen precies gelijk
blijven. De EMS-sensoren hadden hun attributen al buiten de recorder
(GEEN_ATTRIBUTEN_IN_RECORDER, sinds v5.34/v5.76); de rijen kwamen door
tijdstempels, tellers en afrondingsruis in de attributen.

De oplossing zit dus vóór Home Assistant: deze mixin beslist of een
schrijfbeurt nodig is.

- Toestand of beschikbaarheid veranderd, of de allereerste keer: meteen
  schrijven. De geschiedenis en de statistiek missen niets.
- Alleen attributen veranderd: hoogstens eens per `_zuinig_attr_interval_s`
  (standaard 10 minuten; korter voor sensoren waarvan het dashboard een
  attribuut als live waarde toont).
- Vergeleken wordt een vingerafdruk: de vluchtige sleutels
  (`_zuinig_vluchtig`, bijvoorbeeld `last_successful_update`) tellen niet
  mee en kommagetallen worden op vier significante cijfers afgerond.
  Verandert er alleen iets vluchtigs, dan volgt het pas bij de hartslag
  (`_zuinig_hartslag_s`, 15 minuten).

De sensoren pollen niet meer zelf (Home Assistant riep elke 30 s een
schrijfbeurt aan die niet langs deze poort liep); een eigen tik van 30 s
vraagt de poort. Een sensor die op een andere plek `async_write_ha_state`
aanroept, gaat ook langs de poort.

Opstarten (v5.178.1): de eerste schrijfbeurt komt bij het toevoegen van de
entiteit, vóór de eerste EMS-ronde. De attributen zijn dan nog leeg
(modulegezondheid: `modules: []`). Bleef de toestand daarna gelijk (de
modulegezondheid staat op "0"), dan volgde de gevulde lijst pas na het
attribuutinterval: tot 5-10 minuten "Geen modulegegevens" in de cockpit.
Daarom gaan attribuutwijzigingen in de opwarmtijd (`ZUINIG_OPWARM_S` na de
eerste schrijfbeurt) en een attribuut dat van leeg naar gevuld gaat (of
nieuw verschijnt) meteen door - hoogstens eens per tik.

Bij het stoppen van Home Assistant schrijft elke sensor nog één keer zijn
actuele stand, buiten de poort om. Een aantal sensoren haalt bij de
herstart zijn geleerde gegevens uit de attributen van de laatste toestand
(RestoreEntity); Home Assistant bewaart die bij het afsluiten
(EVENT_HOMEASSISTANT_FINAL_WRITE, na STOP) uit de toestandsmachine. Zonder
deze laatste schrijfbeurt kon dat tot tien minuten achterlopen.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_interval

_LOGGER = logging.getLogger(__name__)

# Tijdstempels die alleen zeggen DAT er gerekend is, niet WAT.
STANDAARD_VLUCHTIG = frozenset(
    {
        "last_successful_update",
        "last_successful_update_short",
        "berekend_om",
        "laatst_berekend",
        "bijgewerkt",
        "rekentijd_ms",
    }
)

ZUINIG_TIK_S = 30
ZUINIG_ATTR_INTERVAL_S = 600
ZUINIG_HARTSLAG_S = 900
# v5.178.1: na de eerste schrijfbeurt zo lang attribuutwijzigingen meteen.
ZUINIG_OPWARM_S = 300
# Ondergrens tussen twee schrijfbeurten voor de snelle routes hierboven.
ZUINIG_MIN_S = 25

_LEEG = (None, (), "", "unknown", "unavailable")

# v5.186.0: hoe lang de attributen van één EMS-ronde hergebruikt worden.
ZUINIG_ATTR_CACHE_S = 55


def _omhul_attributen(fget):
    """`extra_state_attributes` met een cache per EMS-ronde (v5.186.0).

    De poort rekende de (soms zware) attributen elke tik uit voor de
    vingerafdruk, en Home Assistant bij het schrijven meteen nog een keer.
    Nu: binnen één schrijfbeurt altijd hergebruik, en bij de eigen tik
    zolang de coordinator geen nieuwe ronde had (sleutel = tijd van de
    laatste geslaagde ronde), hoogstens ZUINIG_ATTR_CACHE_S. Een directe
    schrijfbeurt (na een ronde of een dienst) rekent altijd vers.
    """

    def lees(self):
        sleutel = self._zuinig_rondesleutel()
        beurt = self.__dict__.get("_zuinig_beurt")
        cache = self.__dict__.get("_zuinig_attr_cache")
        nu = time.monotonic()
        if cache is not None and (
            (beurt is not None and cache[1] == beurt)
            or (self.__dict__.get("_zuinig_via_tik") and sleutel is not None
                and cache[0] == sleutel and nu - cache[2] < ZUINIG_ATTR_CACHE_S)
        ):
            return cache[3]
        waarde = fget(self)
        self.__dict__["_zuinig_attr_cache"] = (sleutel, beurt, nu, waarde)
        return waarde

    lees._zuinig_omhuld = True
    lees.__doc__ = fget.__doc__
    lees.__name__ = getattr(fget, "__name__", "extra_state_attributes")
    return lees


def _afgerond(waarde, diepte: int = 0):
    """Vingerafdruk-vorm: kommagetallen op 4 significante cijfers, dicts en
    lijsten recursief. Zo telt afrondingsruis niet als wijziging."""
    if isinstance(waarde, float):
        if waarde != waarde:  # NaN
            return "nan"
        return float(f"{waarde:.4g}")
    if diepte > 12:
        return repr(waarde)
    if isinstance(waarde, dict):
        return tuple(
            (str(k), _afgerond(v, diepte + 1)) for k, v in waarde.items()
        )
    if isinstance(waarde, (list, tuple)):
        return tuple(_afgerond(v, diepte + 1) for v in waarde)
    if isinstance(waarde, (str, int, bool)) or waarde is None:
        return waarde
    return str(waarde)


def vingerafdruk(attributen: dict | None, vluchtig: frozenset) -> tuple:
    """De attributen zonder vluchtige sleutels, afgerond."""
    if not attributen:
        return ()
    return tuple(
        (str(k), _afgerond(v))
        for k, v in attributen.items()
        if k not in vluchtig
    )


def leeg_naar_gevuld(vorige: tuple, nu: tuple) -> bool:
    """Is een attribuut van leeg (None, lege lijst/dict, "") naar gevuld
    gegaan, of nieuw verschenen? Dat is geen ruis maar de eerste echte
    inhoud, en mag niet op het attribuutinterval wachten (v5.178.1)."""
    oud = dict(vorige or ())
    for sleutel, waarde in nu or ():
        if waarde in _LEEG:
            continue
        if sleutel not in oud or oud[sleutel] in _LEEG:
            return True
    return False


def beslis(
    vorige: dict | None,
    nu: dict,
    sinds_s: float,
    attr_interval_s: float,
    hartslag_s: float,
    opwarmen: bool = False,
) -> bool:
    """Moet er geschreven worden? Los van Home Assistant, zodat het toetsbaar is.

    `vorige`/`nu`: {"kern": (beschikbaar, toestand, naam), "betekenis":
    vingerafdruk zonder vluchtig, "alles": vingerafdruk met vluchtig}.
    """
    if vorige is None or vorige["kern"] != nu["kern"]:
        return True
    if vorige["betekenis"] != nu["betekenis"]:
        if sinds_s >= attr_interval_s:
            return True
        # v5.178.1: opstarten of eerste echte inhoud - niet 5-10 min wachten.
        if opwarmen or leeg_naar_gevuld(vorige["betekenis"], nu["betekenis"]):
            return sinds_s >= min(ZUINIG_MIN_S, attr_interval_s)
        return False
    if vorige["alles"] != nu["alles"]:
        return sinds_s >= hartslag_s
    return False


class ZuinigSchrijven:
    """Mixin vóór SensorEntity in de basisklassen: `class X(ZuinigSchrijven, ...)`."""

    _attr_should_poll = False
    _zuinig_attr_interval_s: float = ZUINIG_ATTR_INTERVAL_S
    _zuinig_hartslag_s: float = ZUINIG_HARTSLAG_S
    _zuinig_vluchtig: frozenset = STANDAARD_VLUCHTIG

    _zuinig_vorige: dict | None = None
    _zuinig_geschreven: float = 0.0
    _zuinig_tik_af = None
    _zuinig_stop_af = None
    _zuinig_overgeslagen: int = 0
    _zuinig_eerste: float | None = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        eigen = cls.__dict__.get("extra_state_attributes")
        if isinstance(eigen, property) and eigen.fget is not None and not getattr(eigen.fget, "_zuinig_omhuld", False):
            cls.extra_state_attributes = property(_omhul_attributen(eigen.fget))

    def _zuinig_rondesleutel(self):
        """Wanneer de coordinator voor het laatst een ronde afrondde (v5.186.0)."""
        coordinator = getattr(self, "_coordinator", None) or getattr(self, "coordinator", None)
        sleutel = getattr(coordinator, "last_successful_update", None)
        return sleutel if isinstance(sleutel, datetime) else None

    def _zuinig_staat(self) -> dict:
        toestand = getattr(self, "state", None)
        if toestand is None and not hasattr(type(self), "state"):
            toestand = getattr(self, "native_value", None)
        attributen = getattr(self, "extra_state_attributes", None) or {}
        kern = (
            bool(getattr(self, "available", True)),
            None if toestand is None else str(toestand),
            str(getattr(self, "name", "") or ""),
        )
        return {
            "kern": kern,
            "betekenis": vingerafdruk(attributen, self._zuinig_vluchtig),
            "alles": vingerafdruk(attributen, frozenset()),
        }

    def async_write_ha_state(self) -> None:
        if getattr(self, "hass", None) is None:
            self._zuinig_schrijf()
            return
        self._zuinig_start_tik()
        # v5.186.0: één schrijfbeurt = één keer de attributen uitrekenen.
        self.__dict__["_zuinig_beurt"] = object()
        try:
            self._zuinig_beslis_en_schrijf()
        finally:
            self.__dict__["_zuinig_beurt"] = None

    def _zuinig_beslis_en_schrijf(self) -> None:
        try:
            staat = self._zuinig_staat()
        except Exception:  # noqa: BLE001 - laat Home Assistant de fout tonen
            self._zuinig_vorige = None
            self._zuinig_schrijf()
            return
        nu = time.monotonic()
        if self._zuinig_eerste is None:
            self._zuinig_eerste = nu
        if not beslis(
            self._zuinig_vorige,
            staat,
            nu - self._zuinig_geschreven,
            self._zuinig_attr_interval_s,
            self._zuinig_hartslag_s,
            opwarmen=nu - self._zuinig_eerste < ZUINIG_OPWARM_S,
        ):
            self._zuinig_overgeslagen += 1
            return
        self._zuinig_vorige = staat
        self._zuinig_geschreven = nu
        self._zuinig_schrijf()

    def _zuinig_schrijf(self) -> None:
        schrijf = getattr(super(), "async_write_ha_state", None)
        if schrijf is not None:
            schrijf()

    def _zuinig_start_tik(self) -> None:
        if self._zuinig_tik_af is not None:
            return
        self._zuinig_tik_af = async_track_time_interval(
            self.hass, self._zuinig_tik, timedelta(seconds=ZUINIG_TIK_S)
        )
        bus = getattr(self.hass, "bus", None)
        if bus is not None and hasattr(bus, "async_listen_once"):
            self._zuinig_stop_af = bus.async_listen_once(
                EVENT_HOMEASSISTANT_STOP, self._zuinig_bij_stop
            )
        aanmelden = getattr(self, "async_on_remove", None)
        if aanmelden is not None:
            aanmelden(self._zuinig_stop)

    @callback
    def _zuinig_bij_stop(self, _gebeurtenis=None) -> None:
        """Laatste stand in de toestandsmachine vóór Home Assistant de
        herstelgegevens wegschrijft."""
        self._zuinig_stop_af = None  # listen_once is al afgemeld
        if getattr(self, "hass", None) is None:
            return
        self._zuinig_vorige = None
        self._zuinig_geschreven = time.monotonic()
        self.__dict__.pop("_zuinig_attr_cache", None)  # v5.186.0: verse stand
        self._zuinig_schrijf()

    @callback
    def _zuinig_stop(self) -> None:
        """Bij verwijderen (ook bij hernoemen, waarna HA hetzelfde object
        opnieuw toevoegt) de tik stoppen en de vingerafdruk vergeten."""
        af, self._zuinig_tik_af = self._zuinig_tik_af, None
        stop_af, self._zuinig_stop_af = self._zuinig_stop_af, None
        self._zuinig_vorige = None
        self._zuinig_eerste = None
        for afmelden in (af, stop_af):
            if afmelden is not None:
                afmelden()

    @callback
    def _zuinig_tik(self, _nu=None) -> None:
        if getattr(self, "hass", None) is None:
            return
        self.__dict__["_zuinig_via_tik"] = True
        try:
            self.async_write_ha_state()
        finally:
            self.__dict__["_zuinig_via_tik"] = False
