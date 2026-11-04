"""Uitleg van de coordinator: waarom de accu doet wat hij doet (B4.4).

De "waarom nu"-regels, de uitlegtekst van de beslissing
(`_build_explanation`) en de redenzinnen. De waardeplan- en
celbeschermingsuitleg staan bij hun eigen mixin. Ongewijzigd verhuisd uit
`coordinator.py`; de coordinator erft deze mixin.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from homeassistant.util import dt as dt_util
from .const import (
    DECISION_REASON_LABELS,
    MIN_BATTERY_POWER_IDLE_W,
    REASON_REGISTRY,
    SOLAR_CAPTURE_FULL_MARGIN_KWH,
    SOLAR_CAPTURE_HYSTERESIS_W,
    WHY_MAX_REASONS,
    WHY_QUESTIONS,
)
from .tijdtekst import tijd_met_dag
from . import standweergave


class UitlegMixin:
    """De uitleg-methodes van de coordinator."""

    def get_why_now(self, now: datetime | None = None) -> dict:
        """Waarom doet de aansturing dit, in drie regels (v1.60.0).

        Gevraagd: "Kun je in de integratie nog een eigen AI maken, die
        zaken als 'Waarom laad je nu? -> Omdat tussen 16:00 en 19:00 de
        prijs 31 cent hoger ligt, er slechts 4,2 kWh zon wordt verwacht,
        en de kans op een tekort vannacht 27% bedraagt' kan toelichten?"

        Geen taalmodel. Het besluit is deterministisch - er is een
        exacte regel die zei wat er moest gebeuren - dus een gegenereerde
        verklaring kan er náást zitten zonder dat iemand het merkt. Elke
        regel hieronder komt uit een waarde die de beslissing
        daadwerkelijk nam, en kan dus niets anders zeggen dan wat er
        gebeurde.

        Het live verhaal bevatte al alle getallen, maar als één lange lap
        tekst met tabellen en klimaatprojectie ertussen - geen antwoord
        op "waarom nu".
        """
        nu = now or dt_util.now()
        reden = self.last_reason
        if not reden:
            return {"beschikbaar": False, "reden": "Nog geen beslissing genomen."}

        regels = [r for r in self._waarom_regels(nu, reden) if r]
        return {
            "beschikbaar": True,
            "vraag": WHY_QUESTIONS.get(reden, "Waarom doet de accu dit nu?"),
            "code": reden,
            "kort": DECISION_REASON_LABELS.get(reden, reden),
            # v5.112.1: de kop in de cockpit. "standaard slim laden" stond er
            # terwijl de accu 374 W aan het huis leverde (gemeld 20-10 20:40).
            "kop": self._waarom_kop(reden),
            "redenen": regels[:WHY_MAX_REASONS],
        }

    def _accu_doet_nu(self) -> tuple[str | None, float | None]:
        """(stand, watt): wat de accu nu doet volgens de meting."""
        try:
            vermogen = self._read_corrected_battery_power()
        except Exception:  # noqa: BLE001 - uitleg mag nooit breken
            return None, None
        if vermogen is None:
            return None, None
        if abs(vermogen) < MIN_BATTERY_POWER_IDLE_W:
            return "STANDBY", vermogen
        return ("ONTLADEN" if vermogen > 0 else "LADEN"), vermogen

    # v5.181.1 (punt 9): redenen in een slimme stand, waar de zon de accu mag
    # vullen of de accu het huis voedt; de kop zegt wat er werkelijk gebeurt.
    _KOP_UIT_WEERGAVE = frozenset({
        "waardeplan_houden", "waardeplan_huis", "waardeplan_leeg",
        "battery_saved_for_peak", "sparen_in_blok", "celbescherming_houden",
    })

    def stand_weergave(self, reden: str | None = None) -> dict:
        """Wat de accu nu doet, voor tegel, kopchip, tijdlijn en uitleg (v5.181.1, punt 9).

        Eén functie (`standweergave.weergave`): de planrij van nu (handmatig
        laden, verkopen, terugleveren) en anders het gemeten vermogen, met
        de reden als toelichting.
        """
        reden = reden if reden is not None else self.last_reason
        _stand, vermogen = self._accu_doet_nu()
        nu = (getattr(self, "last_waardeplan", None) or {}).get("nu") or {}
        modi = getattr(self, "_WAARDEPLAN_MODUS", {}) or {}
        plan_modus = modi.get(nu.get("actie")) if str(reden or "").startswith("waardeplan_") else None
        return standweergave.weergave(reden, plan_modus, vermogen)

    def _waarom_kop(self, reden: str) -> str:
        """De titel uit het register; in de slimme stand met wat de accu nu doet."""
        titel = (REASON_REGISTRY.get(reden) or {}).get("titel") or DECISION_REASON_LABELS.get(reden, reden)
        if reden in self._KOP_UIT_WEERGAVE:
            return self.stand_weergave(reden)["label"]
        if reden != "default_smart":
            return titel
        stand, _w = self._accu_doet_nu()
        return {
            "ONTLADEN": f"{titel}: accu voedt het huis",
            "LADEN": f"{titel}: accu laadt op zon",
            "STANDBY": f"{titel}: accu in rust",
        }.get(stand, titel)

    def _waarom_regels(self, now: datetime, reden: str) -> list[str]:
        """De onderbouwing per beslisreden (v1.60.0)."""

        prijs = self.huidige_prijs_eur_per_kwh()
        drempel = self.last_expensive_price_threshold
        stand = self.accustand_procent()
        beschikbaar = self.beschikbare_energie_kwh()
        nodig = self.last_needed_kwh_to_bridge
        blok = self.last_cheap_block_start
        uitstel = self.last_solar_defer_plan or {}
        verkoop = self.last_sell_check or {}
        vs_net = self.last_battery_vs_grid or {}
        # De samenvatting live opvragen; er is geen bewaard veld voor.
        #
        # v1.63.0, gemeld met een screenshot van Solcast ernaast: "De
        # verwachtte kw zonneenergie kan niet kloppen." De regel zei "er
        # wordt vandaag nog 28,5 kWh zon verwacht" terwijl Solcast 6,63
        # meldde.
        #
        # 28,5 = 6,6 vandaag plus ruim 22 van morgen. De planning loopt
        # zover als er prijzen zijn - de kaart meldde het zelf: "over 32
        # uur" - en de samenvatting telt alles bij elkaar op. Daar plakte
        # deze regel het woord "vandaag" op.
        #
        # Derde keer dat deze horizon een maat betekenisloos maakte, na
        # de tekortkwartieren (v1.42.0) en de plantoetsing (v1.48.0).
        # Vandaar hier expliciet de grens meegeven in plaats van erop te
        # vertrouwen dat de planning bij middernacht ophoudt.
        middernacht = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        try:
            samenvatting = self.get_quarter_plan_summary(now, tot=middernacht) or {}
        except Exception:  # noqa: BLE001
            samenvatting = {}

        def _prijs(waarde) -> str | None:
            return None if waarde is None else f"{waarde * 100:.1f} ct"

        def _blok_tekst() -> str | None:
            if blok is None:
                return None
            uren = (blok - now).total_seconds() / 3600
            if uren <= 0:
                return "het goedkope blok is al begonnen"
            return (
                f"het goedkope blok begint om {blok.strftime('%H:%M')}, over "
                f"{uren:.1f} uur"
            )

        gemeenschappelijk = []
        if prijs is not None:
            regel = f"de prijs is nu {_prijs(prijs)}"
            if drempel is not None:
                regel += f", de drempel voor 'duur' ligt op {_prijs(drempel)}"
            gemeenschappelijk.append(regel)
        if stand is not None and beschikbaar is not None:
            gemeenschappelijk.append(
                f"de accu staat op {stand:.0f}% ({beschikbaar:.1f} kWh bruikbaar)"
            )

        if reden in ("expensive_quarter", "expensive_quarter_no_own_load"):
            regels = list(gemeenschappelijk)
            if nodig is not None:
                regels.append(
                    f"er is {nodig:.1f} kWh nodig om de nacht te overbruggen, "
                    "en dat blijft gereserveerd"
                    + self._tot_en_na_blok_zin().rstrip(".").replace(
                        " Opgesplitst", "; opgesplitst"
                    )
                )
            if verkoop.get("vrij_te_verkopen_kwh") is not None:
                regels.append(
                    f"{verkoop['vrij_te_verkopen_kwh']:.1f} kWh is vrij om te "
                    "verkopen"
                )
            return regels

        if reden == "expensive_quarter_soc_protected":
            regels = list(gemeenschappelijk)
            regels.append(
                "het kwartier is duur genoeg, maar de accu zit op de reserve "
                "die voor vannacht nodig is"
            )
            if nodig is not None:
                regels.append(f"die reserve is {nodig:.1f} kWh")
            return regels

        if reden == "solar_capture_deferred":
            regels = []
            if uitstel.get("omslag_uur") is not None:
                regels.append(
                    f"opvangen kan wachten tot {uitstel['omslag_uur']}:00"
                )
            if uitstel.get("prijsverschil_ct") is not None:
                regels.append(
                    f"het overschot is nu {uitstel['prijsverschil_ct']:.1f} ct "
                    "meer waard op het net dan straks"
                )
            if uitstel.get("geschatte_winst_eur") is not None:
                regels.append(
                    f"dat scheelt naar schatting € "
                    f"{uitstel['geschatte_winst_eur']:.2f}"
                )
            return regels + gemeenschappelijk[1:]

        if reden == "grid_cheaper_than_battery":
            regels = []
            if vs_net.get("accu_eur_per_kwh") is not None:
                regels.append(
                    f"een kWh uit de accu kost {vs_net['accu_eur_per_kwh']*100:.1f} ct "
                    f"(kostprijs {vs_net.get('kostprijs_eur_per_kwh', 0)*100:.1f} ct, "
                    f"rendement {vs_net.get('rendement_procent', 0):.0f}%, slijtage "
                    f"{vs_net.get('slijtage_ct_per_kwh', 0):.1f} ct)"
                )
            if vs_net.get("net_eur_per_kwh") is not None:
                regels.append(
                    f"van het net kost hij nu {vs_net['net_eur_per_kwh']*100:.1f} ct"
                )
            regels.append("de accu blijft dus vol voor een duurder moment")
            return regels

        if reden in (
            "grid_charging_low_solar",
            "grid_charging_low_solar_extra_dip",
            "grid_charging_profitable",
            "grid_charging_dip",
            "expensive_quarter_peak",
            "battery_saved_for_peak",
            "sparen_in_blok",
        ):
            return self._waarom_bij_laden(reden, gemeenschappelijk, _blok_tekst())

        if reden == "discharging_window":
            regels = list(gemeenschappelijk)
            if _blok_tekst():
                regels.append(_blok_tekst())
            regels.append(
                "tot dan voedt de accu het huis in plaats van bij te laden"
            )
            return regels

        if reden in ("celbescherming_laden", "celbescherming_houden"):
            # v5.157.0
            return self._waarom_celbescherming(reden)

        if reden in (
            "waardeplan_laden", "waardeplan_verkopen", "waardeplan_huis", "waardeplan_houden",
            "waardeplan_leeg", "waardeplan_terugleveren",
        ):
            # v5.158.0
            return self._waarom_waardeplan()

        if reden == "emergency_low_battery":
            return gemeenschappelijk + [
                "de accu is te ver gezakt; laden gaat nu voor alles"
            ]

        if reden == "negative_price":
            return [
                f"de prijs is negatief ({_prijs(prijs)}): teruglevering kost geld",
                "de accu laadt hard en de panelen worden teruggeregeld",
            ]

        if reden in ("arbitrage_solar_capture", "post_salderen_solar_capture"):
            # v1.66.0, gemeld: "Zonoverschot gaat de accu in? Kan niet
            # want die is vol :)"
            #
            # Klopt. Deze regel stond er onvoorwaardelijk, ook bij een
            # accu op 100%. Dan gaat het overschot het net op - en dat is
            # een heel ander verhaal dan "de accu vangt het op".
            ruimte = self._resterende_laadruimte_kwh()
            if ruimte is not None and ruimte <= SOLAR_CAPTURE_FULL_MARGIN_KWH:
                regels = [
                    "de accu is vol; het zonoverschot gaat het net op"
                ]
            else:
                regels = ["er is zonoverschot en dat gaat de accu in"]
                if ruimte is not None:
                    regels[0] += f" (nog {ruimte:.1f} kWh ruimte)"
            if samenvatting.get("zon_kwh") is not None:
                regels.append(
                    f"er wordt vandaag nog {samenvatting['zon_kwh']:.1f} kWh zon "
                    "verwacht"
                )
            return regels + gemeenschappelijk[1:]

        if reden == "kalibratie":
            # v3.27.3, gemeld met een schermafdruk: "Tekst is in
            # kalibratie mode niet geheel correct." De kop klopte wel -
            # "Waarom doet de aansturing niets?" - maar eronder stond
            # het gewone verhaal over prijsdrempels, want `kalibratie`
            # viel hier door naar de terugval van `default_smart`.
            #
            # Twee plekken bouwen een uitleg: `_build_explanation` had
            # zijn tak al, deze niet.
            regels = [
                "de kalibratiestand staat aan: de accu wordt met de hand "
                "geladen en de aansturing schrijft niets"
            ]
            if stand is not None:
                regels.append(
                    f"de accu staat op {stand:.0f}% - de melding komt bij 99%"
                )
            regels.append(
                "koeling loopt door; netlading, piek, tekortdetectie en "
                "verbruiksleer tellen deze periode niet mee"
            )
            return regels

        if reden == "force_manual":
            return ["handmatig overschreven; de aansturing laat de accu met rust"]

        if reden == "no_forecast_data":
            return [
                "er zijn geen prijzen beschikbaar, dus valt er niets te plannen"
            ]

        # default_smart en al het overige
        regels = list(gemeenschappelijk)
        regels.append(f"geen bijzondere reden om iets anders te doen: {self._slim_nu_tekst()}")
        return regels

    def _slim_nu_tekst(self) -> str:
        """v5.112.1: wat de accu NU doet, niet wat hij in deze stand kan."""
        stand, watt = self._accu_doet_nu()
        if stand == "ONTLADEN":
            return f"de accu levert nu {abs(watt):.0f} W aan het huis"
        if stand == "LADEN":
            return f"de accu laadt nu {abs(watt):.0f} W met zonne-overschot"
        if stand == "STANDBY":
            return "de accu staat stil: geen overschot en het huis vraagt (bijna) niets"
        return "de accu vangt zon op en voedt het huis"

    def _waarom_bij_laden(
        self, reden: str, gemeenschappelijk: list, blok_tekst: str | None
    ) -> list[str]:
        """De waarom-regels bij laden uit het net (v5.21).

        Bij laden omdat het loont: de getallen van het laadbesluit ZELF -
        dezelfde die de beslissing namen, niet achteraf opnieuw berekend.
        """
        if reden == "sparen_in_blok":
            # v5.73: de afweging zelf.
            a = self.last_sparen_in_blok or {}
            if a.get("grond") == "netladen_in_blok" and a.get("besluit"):
                # v5.75
                return [
                    f"netladen volgt in dit blok ({a.get('netladen_om', '')[11:16]})",
                    f"stroom kost nu {a['prijs_nu_ct']:.1f} ct",
                    f"terugladen kost {a['rondtrip_ct']:.1f} ct (blokprijs / rendement + slijtage)",
                ]
            if a.get("prijs_nu_eur") is None or a.get("waarde_na_blok_eur") is None:
                return list(gemeenschappelijk)
            return [
                f"het blok laadt niet uit het net; stroom kost nu {a['prijs_nu_eur'] * 100:.1f} ct",
                f"een kWh in de accu is na het blok {a['waarde_na_blok_eur'] * 100:.1f} ct waard",
                f"de zon brengt nog {a['zon_naar_accu_kwh']:.1f} kWh in de accu; hij raakt vandaag niet vol",
            ]
        if reden == "battery_saved_for_peak":
            plan = self.last_spaarplan or {}
            if plan.get("nodig_kwh") is None:
                return list(gemeenschappelijk)
            regels = [
                f"er zit {plan['beschikbaar_kwh']:.1f} kWh in de accu, er is "
                + self._spaarplan_nodig_tekst(plan, lambda w: f"{w:.1f}"),
            ]
            if plan.get("prijs_nu_eur") is not None and plan.get("grensprijs_eur"):
                regels.append(
                    f"dit kwartier kost {plan['prijs_nu_eur'] * 100:.1f} ct, de "
                    f"accu dekt alleen kwartieren vanaf {plan['grensprijs_eur'] * 100:.1f} ct"
                )
            if plan.get("gedekt"):
                regels.append("gedekt: " + ", ".join(plan["gedekt"]))
            return regels
        if reden == "expensive_quarter_peak":
            piek = self.last_piekverkoop or {}
            if piek.get("prijs_nu_eur") is None:
                return list(gemeenschappelijk)
            return [
                f"de prijs is nu {piek['prijs_nu_eur'] * 100:.1f} ct",
                f"het duurste kwartier tot het volgende goedkope blok kost "
                f"{piek['duurste_later_eur'] * 100:.1f} ct",
                f"nu verkopen en later inkopen levert minstens "
                f"{piek['winst_ct_per_kwh']:.1f} ct per kWh op, ook onder de reserve",
            ]
        if reden == "grid_charging_dip":
            besluit = self.last_laadbesluit or {}
            if besluit.get("waarde_eur") is None:
                return list(gemeenschappelijk)
            blok = dt_util.parse_datetime(besluit.get("blok") or "")
            return [
                f"stroom kost nu {besluit['prijs_nu_eur'] * 100:.1f} ct",
                (
                    f"de accu haalt het goedkope blok van {tijd_met_dag(blok)} niet: er "
                    f"ontbreekt {besluit['gat_kwh']:.1f} kWh"
                    if blok
                    else f"er ontbreekt {besluit['gat_kwh']:.1f} kWh tot het goedkope blok"
                ),
                f"die kWh is straks {besluit['waarde_eur'] * 100:.1f} ct waard "
                f"({besluit['latere_prijs_eur'] * 100:.1f} ct x "
                f"{besluit['rendement_procent']:.0f}% - {besluit['slijtage_ct']:.1f} ct slijtage)",
            ]
        if reden != "grid_charging_profitable":
            regels = list(gemeenschappelijk)
            regels.append("morgen wordt weinig zon verwacht, en bijladen uit het net loont nu")
            if blok_tekst:
                regels.append(blok_tekst)
            return regels
        besluit = self.last_laadbesluit or {}
        if besluit.get("soort") == "balanceren":
            # v5.117.0
            bal = besluit.get("balanceren") or {}
            return [
                f"stroom kost nu {besluit['prijs_nu_eur'] * 100:.1f} ct, een van de goedkoopste kwartieren van het blok",
                f"de accu is {bal.get('dagen_niet_vol', '?')} dagen niet vol geweest",
                "vol laden laat het accubeheer de cellen gelijk trekken",
            ]
        if besluit.get("verdringt_zon") and besluit.get("exportprijs_eur") is not None:
            # v5.86 (L-EMS-021)
            vol = dt_util.parse_datetime(besluit.get("zon_vol_om") or "")
            return [
                f"stroom kost nu {besluit['prijs_nu_eur'] * 100:.1f} ct",
                (f"de zon heeft de accu om {vol:%H:%M} vol" if vol else "de zon vult de accu vanzelf")
                + f"; die zon gaat dan voor {besluit['exportprijs_eur'] * 100:.1f} ct het net op",
                "nu laden en straks die zon terugleveren loont",
            ]
        regels = []
        if besluit.get("prijs_nu_eur") is not None:
            incl = besluit.get("prijs_nu_incl_eur")
            regels.append(
                f"stroom kost nu {incl * 100:.1f} ct (zonder belastingdeel {besluit['prijs_nu_eur'] * 100:.1f} ct)"
                if incl is not None and abs(incl - besluit["prijs_nu_eur"]) > 1e-6
                else f"stroom kost nu {besluit['prijs_nu_eur'] * 100:.1f} ct"
            )
        if besluit.get("waarde_eur") is not None:
            regels.append(
                f"een kWh in de accu is straks {besluit['waarde_eur'] * 100:.1f} ct "
                f"waard ({besluit['latere_prijs_eur'] * 100:.1f} ct x "
                f"{besluit['rendement_procent']:.0f}% - "
                f"{besluit['slijtage_ct']:.1f} ct slijtage)"
            )
        if besluit.get("gat_kwh") is not None:
            regels.append(
                f"de zon vult nog {besluit['zonoverschot_kwh']:.1f} kWh, "
                f"er blijft {besluit['gat_kwh']:.1f} kWh over om bij te laden"
            )
        # v5.168.0: de prijzen hierboven zijn dan zonder belastingdeel.
        if zin := self._saldering_uitlegzin():
            regels.append(zin)
        return regels

    def _uitleg_soc_protected(self) -> str:
        """De uitleg bij `expensive_quarter_soc_protected` (v5.127.4: uit
        `_build_explanation` gehaald, die op de ratel staat)."""
        parts: list[str] = []
        onbekend = getattr(self, "last_verkoopreserve_onbekend", None)
        if onbekend == "in_blok":
            parts.append(
                "Dit kwartier is duur, maar het valt in het goedkope "
                "blok: daar wordt de accu geladen en niet verkocht. "
                "Daarom blijft de Zendure op 'smart' staan."
            )
        elif onbekend == "onbekend":
            parts.append(
                "Dit zou een duur kwartier zijn om te ontladen, maar de "
                "reserve voor het huis is nu niet te berekenen. Niet "
                "weten is niet verkopen: de Zendure blijft op 'smart' "
                "staan."
            )
        elif self.last_price_priority_held_off:
            parts.append(
                "Dit kwartier is duur genoeg, maar de beperkte "
                "beschikbare energie wordt bewust bewaard voor een nog "
                "duurder kwartier later vandaag (prijs-prioriteit) - "
                "dus blijft de Zendure voor nu op 'smart' staan in "
                "plaats van al te verkopen."
            )
        elif self.last_used_soc_taper_fallback:
            soc_txt = (
                f"{self.accustand_procent():.0f}%"
                if self.accustand_procent() is not None
                else "onbekend"
            )
            parts.append(
                f"Dit zou een duur kwartier zijn om te ontladen, maar de "
                f"accu-SoC ({soc_txt}) is te laag om dat te "
                f"rechtvaardigen. Daarom blijft de Zendure op 'smart' "
                f"staan in plaats van geforceerd te ontladen."
            )
        else:
            available_txt = (
                f"{self.last_available_kwh:.2f} kWh"
                if self.last_available_kwh is not None
                else "onbekend"
            )
            parts.append(
                f"Dit zou een duur kwartier zijn om te ontladen, maar de "
                f"nachtreserve-berekening laat geen ruimte over: alle "
                f"beschikbare energie ({available_txt}) is al nodig om "
                f"de rest van de nacht te overbruggen. Daarom blijft de "
                f"Zendure op 'smart' staan (die regelt zelf verder, "
                f"zonder onze reserve te verkleinen) in plaats van "
                f"geforceerd te ontladen."
            )
        return " ".join(parts)

    def _build_explanation(self) -> str:
        """Build a plain-language (Dutch) explanation of the current
        decision, so you can read in the dashboard what the integration
        is doing and why - without having to piece together raw sensor
        values yourself.
        """
        if getattr(self, "kalibratie", False) or self.last_reason == "kalibratie":
            return (
                "De kalibratiestand staat aan: de accu wordt met de hand "
                "geladen en de integratie stuurt niets. De koeling loopt "
                "wél door - bij 2000 W is dat bescherming. Netlading, "
                "piekmeting, tekortdetectie en verbruiksleer tellen deze "
                "periode niet mee."
            )

        if self.force_manual:
            return (
                "De 'Force manual'-schakelaar staat aan: de integratie doet nu "
                "niets en laat de Zendure ongemoeid - jij hebt zelf de controle."
            )

        reason = self.last_reason
        parts: list[str] = []

        if reason == "no_forecast_data":
            parts.append(
                "Er kon geen bruikbare prijsvoorspelling gevonden worden op de "
                "geconfigureerde prijssensor. Controleer of die sensor bestaat "
                "en een geldig 'forecast'-attribuut heeft."
            )

        elif reason == "expensive_quarter":
            power = self.last_discharge_power_applied
            power_txt = f"{power:.0f}W" if power else "het ingestelde vermogen"
            tier_txt = (
                "de ruimere secundaire laag (top 45% van de dagprijsrange, "
                "alleen omdat er toch nog vrije ruimte over was)"
                if self.last_expensive_tier == "secondary"
                else "de strikte primaire drempel (top 20% van de "
                "dagprijsrange)"
            )
            parts.append(
                f"Dit kwartier haalt {tier_txt}, dus de accu ontlaadt nu "
                f"actief op {power_txt} om van de hoge prijs te profiteren."
            )
            if self.last_household_load_w is not None and self.last_discharge_floor_applied:
                parts.append(
                    f"Let op: het vermogen is opgehoogd tot minstens je "
                    f"huidige huisverbruik ({self.last_household_load_w:.0f}W), "
                    f"zodat er niet alsnog tegen de piekprijs wordt "
                    f"geïmporteerd."
                )
            # v3.48.0: via de helper, want het veld zelf loopt achter.
            # Als toewijzing in de voorwaarde, zodat `_build_explanation`
            # niet groeit - die staat op de ratel van v3.35.0.
            if (stand := self.accustand_procent()) is not None:
                parts.append(f"Huidige accu-SoC: {stand:.0f}%.")

        elif reason == "post_salderen_solar_capture":
            parts.append(
                "Dit kwartier is duur, maar er is op dit moment "
                "zonoverschot. Nu de saldering is beëindigd levert "
                "terugleveren alleen nog het lage teruglevertarief op, "
                "terwijl diezelfde zon opgeslagen later de volle "
                "inkoopprijs bespaart. De Zendure staat daarom op 'smart' "
                "om het overschot op te vangen in plaats van te verkopen."
            )

        elif reason == "expensive_quarter_no_own_load":
            parts.append(
                "Dit kwartier is duur genoeg om te ontladen, maar er is nu "
                "te weinig eigen verbruik om dat zinvol te doen. Nu de "
                "saldering is beëindigd zou het overschot tegen het lage "
                "teruglevertarief het net op gaan, terwijl diezelfde "
                "energie in de accu later de volle inkoopprijs kan "
                "besparen - dus blijft de accu gespaard."
            )

        elif reason == "expensive_quarter_soc_protected":
            parts.append(self._uitleg_soc_protected())

        elif reason == "grid_charging_low_solar":
            parts.append(
                "Er wordt weinig zon verwacht, dus tijdens dit goedkoopste "
                "moment van de dag wordt er actief bijgeladen vanaf het net "
                "(manual, negatief vermogen) in plaats van te wachten op zon."
            )

        elif reason == "grid_charging_low_solar_extra_dip":
            margin_txt = (
                f"{self.last_extra_dip_margin_eur_per_kwh:.3f} €/kWh"
                if self.last_extra_dip_margin_eur_per_kwh is not None
                else "onbekend"
            )
            parts.append(
                "Er wordt weinig zon verwacht vandaag, en dit is een aparte, "
                "losse prijsdip buiten het hoofd-goedkope blok - maar "
                "aantoonbaar voordeliger dan wachten tot het duurste "
                f"resterende moment vandaag (marge, na rendementsverlies: "
                f"{margin_txt}). Daarom wordt er nu ook actief bijgeladen "
                "vanaf het net. Deze energie wordt vandaag niet meer "
                "verkocht (winter-guard)."
            )

        elif reason == "emergency_low_battery":
            soc_txt = (
                f"{self.accustand_procent():.0f}%"
                if self.accustand_procent() is not None
                else "kritiek laag"
            )
            parts.append(
                f"NOODLADEN: de accu staat op {soc_txt}, te kritiek om te "
                f"wachten tot het goedkoopste blok. De integratie laadt nu "
                f"actief bij vanaf het net, ook al is dit niet het "
                f"goedkoopste moment - beter een klein beetje duurder laden "
                f"dan de accu helemaal leeg laten lopen."
            )

        elif reason == "negative_price":
            power_txt = (
                f"{abs(self.last_charge_power_applied):.0f}W"
                if self.last_charge_power_applied is not None
                else "het ingestelde vermogen"
            )
            parts.append(
                f"De energieprijs is nu negatief: de accu laadt actief op "
                f"{power_txt} (je wordt betaald om te verbruiken), en de "
                f"zonnepanelen worden geleidelijk afgeregeld om niet tegen "
                f"een negatieve prijs terug te leveren."
            )

        elif reason == "arbitrage_solar_capture":
            solar_txt = (
                f"{self.last_arbitrage_solar_surplus_w:.0f}W"
                if self.last_arbitrage_solar_surplus_w is not None
                else "onbekend"
            )
            parts.append(
                f"Er is nu een verwacht zonoverschot van {solar_txt} - "
                f"zonder ingrijpen zou 'laden uitstellen' "
                f"(smart_discharging) dat overschot laten liggen, want "
                f"die modus dekt alleen het huishoudverbruik en laadt "
                f"niet bij vanuit zon. De accu staat daarom nu gewoon in "
                f"smart-modus, die het zonoverschot vanzelf opvangt via "
                f"P1-volgend laden. Wordt nooit actief van het net "
                f"bijgekocht - alleen zon die er al is, wordt "
                f"vastgelegd."
            )

        elif reason == "discharging_window":
            if self.last_has_enough_energy is not None and self.last_available_kwh is not None:
                needed_txt = (
                    f"{self.last_needed_kwh_to_bridge:.2f}"
                    if self.last_needed_kwh_to_bridge is not None
                    else "onbekend"
                )
                parts.append(
                    f"De accu heeft nu {self.last_available_kwh:.2f} kWh "
                    f"beschikbaar - genoeg om de resterende tijd tot het "
                    f"goedkoopste blok te overbruggen (geschat nodig: "
                    f"{needed_txt} kWh). Daarom wordt laden uitgesteld: de "
                    f"accu dekt alleen het huishoudverbruik (0 op de meter) en "
                    f"slaat geen zon op (smart_discharging); boven {SOLAR_CAPTURE_HYSTERESIS_W:.0f} W overschot naar slim."
                    + self._tot_en_na_blok_zin()
                )
            else:
                parts.append(
                    "Het is nog vóór het goedkoopste blok, dus laden wordt "
                    "uitgesteld: de accu dekt alleen het huishoudverbruik (0 "
                    "op de meter), verkoopt niet en slaat geen zon op "
                    "(smart_discharging)."
                )

        elif reason == "default_smart":
            if self.last_has_enough_energy is False:
                needed_txt = (
                    f"{self.last_needed_kwh_to_bridge:.2f}"
                    if self.last_needed_kwh_to_bridge is not None
                    else "onbekend"
                )
                avail_txt = (
                    f"{self.last_available_kwh:.2f}"
                    if self.last_available_kwh is not None
                    else "onbekend"
                )
                parts.append(
                    # v5.81.1: het getal is de reserve tot het goedkope
                    # blok PLUS de lange horizon (wat er na het blok nog
                    # nodig is), met marge - niet "de dure kwartieren van
                    # vandaag".
                    f"De accu heeft niet genoeg beschikbare energie "
                    f"({avail_txt} kWh) voor de reserve tot het goedkope "
                    f"blok en de uren daarna tot de prijzen ophouden, met "
                    f"marge (geschat nodig: {needed_txt} kWh). Daarom wordt er "
                    f"niet verkocht en regelt de Zendure het zelf "
                    f"(smart-modus: laden bij zonoverschot, ontladen voor "
                    f"het huis)."
                    + self._tot_en_na_blok_zin()
                )
            else:
                price_txt = (
                    f"€{prijs:.3f}/kWh"
                    if (prijs := self.huidige_prijs_eur_per_kwh()) is not None
                    else "onbekend"
                )
                if self.last_expensive_price_threshold is not None:
                    threshold_txt = f"€{self.last_expensive_price_threshold:.3f}/kWh"
                    low_solar_txt = (
                        " (vandaag extra streng, want er wordt weinig zon "
                        "verwacht)"
                        if self.last_low_solar_narrowed_threshold
                        else ""
                    )
                    parts.append(
                        f"Er is nu geen speciale reden om in te grijpen: de "
                        f"huidige prijs ({price_txt}) haalt de drempel voor "
                        f"'duur' vandaag ({threshold_txt}{low_solar_txt}) "
                        f"niet, en het goedkoopste blok is al gaande of "
                        f"voorbij. De Zendure regelt dit zelf (smart-modus)."
                    )
                    if self.last_secondary_price_threshold is not None:
                        parts.append(
                            f"Ook de ruimere secundaire drempel "
                            f"(€{self.last_secondary_price_threshold:.3f}/kWh, "
                            f"top 45%) wordt niet gehaald."
                        )
                else:
                    parts.append(
                        "Er is nu geen speciale reden om in te grijpen: de "
                        "prijs is niet bijzonder hoog, en het goedkoopste "
                        "blok is al gaande of voorbij. De Zendure regelt dit "
                        "zelf (smart-modus)."
                    )

        else:
            # v4.19: eerst de tabel, dan pas opgeven. `REDEN_UITLEG`
            # bevat de redenen waarvan de uitleg geen getallen nodig
            # heeft - een nieuwe reden toevoegen is daar één regel, in
            # plaats van een tak in deze functie. Dat is de eerste steen
            # van één bron voor beslissing en uitleg.
            #
            # De aanleiding: "Onbekende reden: solar_capture_deferred"
            # stond in de export van 17 september. Die reden zat in
            # REASON_TO_MODE en in de woordenlijst, maar niet hier.
            # v4.20: de uitleg komt uit REASON_REGISTRY - de enige bron
            # voor wat een reden betekent. Hier stond eerst een eigen
            # tabel `REDEN_UITLEG`, en dat was een vijfde kopie van
            # hetzelfde begrip.
            # v5.73: met getallen waar die er zijn (`_reden_uitleg`).
            parts.append(self._reden_uitleg(reason))

        # v0.63.22: shown for every reason where it's meaningful context
        # (reported: only visible for discharging_window before this -
        # the underlying data was already fresh every tick regardless of
        # reason, `_should_postpone_charging` runs early and
        # unconditionally, this was purely a text-building gap). Not
        # shown for no_forecast_data (nothing to compute a reserve
        # against) or when the breakdown itself is empty.
        if reason not in ("no_forecast_data",) and self.last_needed_kwh_breakdown:
            parts.append(
                "Diepste-tekort-berekening (het echte dieptepunt onderweg, "
                "niet zomaar het eindsaldo):\n\n"
                + self._build_needed_kwh_breakdown_table()
                + "\n\n"
            )

        recent_shortfalls = sum(1 for v in self.reserve_shortfall_history if v)
        if recent_shortfalls > 0:
            parts.append(self._let_op_tekortnachten_tekst(recent_shortfalls))

        if self.learning_only:
            parts.append(
                "Let op: 'Learning only' staat aan - dit wordt alleen berekend "
                "en gesimuleerd, er wordt niets echt naar de Zendure gestuurd."
            )

        return " ".join(parts)

    def _reden_uitleg(self, reden: str | None) -> str:
        """De uitleg uit REASON_REGISTRY, met getallen waar die er zijn (v5.73)."""
        if reden == "sparen_in_blok":
            return self._sparen_in_blok_zin()
        uitleg = (REASON_REGISTRY.get(reden) or {}).get("uitleg") or f"Onbekende reden: {reden}."
        # v5.165.0: bij het waardeplan de volgende netlading uit het plan.
        if str(reden or "").startswith("waardeplan_") and (zin := self._waardeplan_lading_zin()):
            uitleg += " " + zin[0].upper() + zin[1:] + "."
        # v5.181.1 (punt 1): rekent het EMS wel maar stuurt het niet, dan staat
        # dat bij het besluit (04-11: "terugleveren" terwijl de accu op
        # smart_charging bleef door de handmatige stand).
        niet = (getattr(self, "last_waardeplan", None) or {}).get("niet_gestuurd")
        if str(reden or "").startswith("waardeplan_") and niet:
            uitleg += f" Niet naar de accu gestuurd: {niet}."
        return uitleg
