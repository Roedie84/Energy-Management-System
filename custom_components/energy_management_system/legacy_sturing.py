"""Regelgebaseerde sturing van de coordinator: de terugvalroute (B4.5).

De sturing van voor het waardeplan, die nog draait als het waardeplan er
niet is: het goedkope blok, laden uit het net (laadregel, dipbesluit),
de reserves (dynamische reserve, verkoopreserve, secundaire laag), de
verkoopruimte (`may_sell_now` en zijn schaduw), en de takken voor een
lege accu en negatieve prijzen. Ongewijzigd verhuisd uit `coordinator.py`;
de coordinator erft deze mixin.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from homeassistant.util import dt as dt_util
from .const import (
    CHEAP_BLOCK_STABILITY_MARGIN_FRACTION,
    CHEAP_BLOCK_THRESHOLD_MARGIN_FRACTION,
    CONF_AVAILABLE_ENERGY_SENSOR,
    CONF_BATTERY_ROUND_TRIP_EFFICIENCY,
    CONF_MANUAL_CHARGE_POWER,
    CONF_MANUAL_DISCHARGE_POWER,
    CONF_NEGATIVE_PRICE_CHARGE_POWER,
    DEFAULT_BATTERY_ROUND_TRIP_EFFICIENCY_PERCENT,
    DEFAULT_MANUAL_CHARGE_POWER,
    DEFAULT_MANUAL_DISCHARGE_POWER,
    DEFAULT_NEGATIVE_PRICE_CHARGE_POWER,
    DIP_MARGE,
    DYNAMIC_DISCHARGE_RESERVE_MARGIN,
    EMERGENCY_LOW_BATTERY_EXIT_MARGIN_PERCENT,
    EXCESS_MARGIN_REDUCTION_PER_RECENT_DAY,
    EXTENDED_LOW_SOLAR_MARGIN_BONUS_PER_DAY,
    HEEL_LAGE_PRIJS_GRENS_MAX_EUR,
    LAADBLOK_HERLAAD_DREMPEL,
    LAADBLOK_HERLAAD_SOC_PROCENT,
    MARGE_TELT_NIET_MEE_SOORTEN,
    MIN_TOTAL_MARGIN_BONUS_PERCENT,
    NACHT_COMFORTABEL_SOC_PROCENT,
    NACHT_KRAP_NETIMPORT_KWH,
    NACHT_KRAP_SOC_PROCENT,
    NEGATIEVE_PRIJS_AAN_EUR,
    NEGATIEVE_PRIJS_MIN_MINUTEN,
    NEGATIEVE_PRIJS_UIT_EUR,
    PLAN_SHORTFALL_ALERT_MIN_QUARTERS,
    POST_SALDEREN_MIN_USEFUL_DISCHARGE_W,
    PRICE_SCALE_FACTOR,
    RESERVE_BODEM_FRACTIE,
    RESERVE_SPRONGEN_MAX,
    RESERVE_SPRONG_DREMPEL_KWH,
    RESERVE_SPRONG_HERSTART_S,
    RESERVE_SPRONG_VERKLAARD_KWH,
    SAFE_SELL_MIN_MOMENTEN,
    SAFE_SELL_SHADOW_LENGTE,
    SECONDARY_EXPENSIVE_PRICE_THRESHOLD_FRACTION,
    SELL_HYSTERESIS_KWH,
    SELL_REOPEN_MIN_MINUTES,
    SELL_RESERVE_DEEPEST_SAFETY_FACTOR,
    SELL_RESERVE_SAFETY_FACTOR,
    SHORTFALL_MARGIN_BONUS_PER_RECENT_DAY,
    SOLAR_POOR_DAY_KWH,
    TEKORTSOORT_ONBEKEND,
    TEKORT_LEEG_MARGE_PROCENT,
    UNPROTECTED_AFTERMATH_MARGIN_PERCENT,
    WAARDEPLAN_STUURT,
)
from .coordinator_hulp import PriceEntry

# Zelfde loggernaam als voorheen, zodat logger-instellingen in HA blijven werken.
_LOGGER = logging.getLogger(__name__.rsplit(".", 1)[0] + ".coordinator")


class LegacySturingMixin:
    """De regelgebaseerde (terugval)sturing van de coordinator."""

    def _get_secondary_expensive_price_threshold(
        self, entries: list[PriceEntry], now: datetime
    ) -> float | None:
        """A more lenient "worth selling if there's spare capacity"
        threshold for today - wider than the primary dynamic threshold
        (see `_get_expensive_price_threshold`), used only to fill
        headroom left unused after today's genuinely expensive (primary-
        tier) quarters are accounted for. Never applied on its own -
        always gated by `_get_spare_headroom_after_primary_tier_kwh`
        being > 0, so this can never eat into the reserve that protects
        tonight/tomorrow.
        """
        todays_entries = [entry for entry in entries if entry[0].date() == now.date()]
        return self._price_threshold_for_entries(
            todays_entries, fraction_override=SECONDARY_EXPENSIVE_PRICE_THRESHOLD_FRACTION
        )

    async def _laad_uit_het_net_als_nodig(
        self,
        now: datetime,
        entries,
        should_force_charge: bool,
        cheap_block_start: datetime | None,
        cheap_block_end: datetime | None,
    ) -> bool:
        """Laden uit het net, als dat nu moet of loont (v5.21).

        Eerst bij weinig zon (dat heeft voorrang, en zet `_grid_charged_today`
        zodat die noodlading later niet wordt terugverkocht). Daarna omdat het
        LOONT - bewust ZONDER die vlag: daar is de latere verkoop juist het
        doel, en met de vlag zou het EMS laden voor de avondverkoop en die
        vervolgens zelf verbieden.

        True als er is geladen; de beslissing is dan klaar.
        """
        # v5.26.1: ook bij weinig zon door de REKENREGEL. Gemeld via de
        # export van 30 september: bij weinig zon laadde het EMS het hele
        # blok vol, ongeacht de marge - tot 28,1 ct, terwijl een kWh voor de
        # avond 26,1 ct waard was; en het kwartierplan voorspelde voor de
        # nacht laden tegen 31,5 ct (waard: 26,3 ct). Bij een lege accu
        # draait het huis toch op het net; laden helpt alleen als het loont.
        # Bij weinig zon wordt het gat vanzelf groot - de zon vult weinig -
        # dus op donkere dagen laadt hij als het loont, en niet als het niet
        # loont. Het noemen blijft: "bijladen bij weinig zon".
        self.last_laadbesluit = self.laadbesluit_uit_het_net(
            now, cheap_block_start, cheap_block_end
        )
        if not self.last_laadbesluit.get("laden"):
            return False
        reden = (
            "grid_charging_low_solar"
            if should_force_charge and self.last_laadbesluit.get("soort") != "dip"
            else "grid_charging_profitable"
        )
        charge_power = self.instelling(CONF_MANUAL_CHARGE_POWER, DEFAULT_MANUAL_CHARGE_POWER)
        await self._async_apply_manual(charge_power)
        # Letterlijk toegewezen, zodat elke reden in de code terug te vinden
        # is (test_geen_reden_in_de_registry_die_niemand_zet).
        if reden == "grid_charging_low_solar":
            self.last_reason = "grid_charging_low_solar"
            self._grid_charged_today = True
        elif (self.last_laadbesluit or {}).get("soort") == "dip":
            self.last_reason = "grid_charging_dip"
        else:
            self.last_reason = "grid_charging_profitable"
        self.last_charge_power_applied = charge_power
        self._update_financial_tracking(now, entries, reden, None, charge_power)
        self._update_shortfall_detection(
            now, reden, self.last_available_kwh, self.last_needed_kwh_to_bridge
        )
        self._finish_decision_tick(now)
        return True

    def _verwacht_zonoverschot_kwh(
        self, start: datetime, end: datetime, veilig: bool = True
    ) -> float | None:
        """Hoeveel zon er naar verwachting de accu in gaat (v5.21).

        Op dezelfde inschatting als het tekort (`_segmenten_verbruik_zon`):
        per uur het deel van de zon dat boven het verbruik uitkomt.
        """
        segmenten = self._segmenten_verbruik_zon(start, end, veilig=veilig)
        if segmenten is None:
            return None
        return sum(max(0.0, zon - verbruik) for verbruik, zon in segmenten)

    def _zon_vol_om(
        self,
        start: datetime,
        beschikbaar: float,
        ruimte: float,
        eind: datetime,
    ) -> datetime | None:
        """Wanneer de zon de accu vanzelf vol heeft (v5.86, L-EMS-021).

        Gemeld op 11 oktober: "Waarom manueel laden vannacht? Is toch niet
        gezien de zonvoorspelling morgen?" Het plan laadde 02:30-04:30 van
        47 naar 100 % tegen 33 ct om om 08:00 te verkopen tegen 47 ct - maar
        de accu was om 11:30 toch vol van de zon, en het middagoverschot ging
        tegen 30-32 ct het net op. Elke kWh die na de ochtend nog in de accu
        zat, verdrong een kWh zon.

        Per uur hetzelfde verbruik en dezelfde zon als het tekort en het
        zonoverschot (`_segmenten_verbruik_zon`), zonder laden of verkopen:
        de vrije ruimte groeit met het verbruik en krimpt met de zon. Altijd
        de VOORZICHTIGE zon: een te vroeg vol-moment houdt laden tegen dat
        nodig was, een te laat moment laat hooguit wat oude winst liggen.
        None als de accu binnen de horizon niet vol raakt of het geleerde
        verbruik ontbreekt.
        """
        if eind <= start:
            return None
        segmenten = self._segmenten_verbruik_zon(start, eind, veilig=True)
        if not segmenten:
            return None
        capaciteit = max(0.0, beschikbaar) + max(0.0, ruimte)
        vrij = max(0.0, ruimte)
        cursor = start
        for verbruik, zon in segmenten:
            uur_eind = cursor.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            segment_eind = min(uur_eind, eind)
            netto = zon - verbruik
            if netto > 0 and vrij <= netto:
                deel = vrij / netto if netto else 0.0
                return cursor + (segment_eind - cursor) * deel
            vrij = min(capaciteit, max(0.0, vrij - netto))
            cursor = segment_eind
        return None

    def _goedkoopste_laadmomenten(
        self,
        now: datetime,
        prijs_nu: float,
        tot_iso: str | None,
        gat_kwh: float,
    ) -> bool:
        """Hoort NU bij de goedkoopste kwartieren om het gat te vullen? (v5.25.1)

        Tussen nu en het dure kwartier waarvoor geladen wordt: zoveel van de
        goedkoopste kwartieren als nodig zijn om het gat te vullen bij het
        laadvermogen. Alleen als het huidige kwartier daarbij hoort. Een
        gelijke prijs later telt niet als goedkoper, zodat het laden niet
        eindeloos wordt uitgesteld.
        """
        tot = dt_util.parse_datetime(tot_iso or "")
        if tot is None or tot <= now:
            return False
        laad_kw = abs(
            float(self.instelling(CONF_MANUAL_CHARGE_POWER, DEFAULT_MANUAL_CHARGE_POWER))
        ) / 1000
        per_kwartier = laad_kw * 0.25
        if per_kwartier <= 0:
            return False
        nodig = max(1, math.ceil(gat_kwh / per_kwartier))
        later = sorted(
            p / PRICE_SCALE_FACTOR
            for begin, _eind, p in (self._get_forecast_entries() or [])
            if now < begin < tot
        )
        # Het huidige kwartier telt mee; goedkoper zijn alleen de kwartieren
        # die ECHT minder kosten dan nu.
        goedkoper = [p for p in later if p < prijs_nu]
        return len(goedkoper) < nodig

    def _dipbesluit(self, now: datetime, blok: datetime | None) -> dict:
        """Laden in een prijsdip, BUITEN het goedkope blok (v5.25).

        Gevraagd: "en wanneer het kosten efficient genoeg is gaat hij bij
        laden van het net toch?" Tot nu toe: alleen in het goedkope blok.
        Een winderige nacht van 15 ct, met de ochtendpiek op 40 ct en het
        goedkope blok pas de volgende middag, liet winst liggen.

        Alleen als de accu het volgende blok NIET haalt - anders koop je nu
        wat het blok straks goedkoper levert. Het spaarplan weet welke
        kwartieren tot het blok gedekt worden; het duurste kwartier dat NIET
        gedekt wordt, bepaalt wat de volgende kWh waard is:

            waarde = duurste ongedekte kwartier x rendement - slijtage

        Dezelfde rekenregel als laden in het blok en verkopen. Nooit meer
        dan er tot het blok ontbreekt; naarmate er bijgeladen wordt, wordt
        dat duurste ongedekte kwartier goedkoper en stopt het vanzelf.

        Bij de prijzen van 29 september loont het niet: 40 x 83,7% - 11,4 =
        22,1 ct, tegen een nachtprijs van 25 ct. Dan spaart het EMS in
        plaats daarvan - dat verschuift zonder rendementsverlies.
        """
        uit: dict = {"laden": False, "soort": "dip"}
        # v5.96: met marge - zie DIP_MARGE.
        plan = self.spaarplan(now, self._get_forecast_entries() or [], blok, marge=DIP_MARGE)
        if not plan.get("actief"):
            uit["reden"] = "niet in het goedkope blok, en de accu haalt het blok"
            return uit
        prijs_nu = self.huidige_prijs_eur_per_kwh()
        ruimte = self._resterende_laadruimte_kwh()
        slijtage_ct = self._laadkosten_ct()  # v5.115.0: slijtage + datacorrectie
        duurste = plan.get("duurste_ongedekt_eur")
        rendement = self.learned_battery_efficiency_percent
        if rendement is None:
            rendement = float(
                self.instelling(
                    CONF_BATTERY_ROUND_TRIP_EFFICIENCY,
                    DEFAULT_BATTERY_ROUND_TRIP_EFFICIENCY_PERCENT,
                )
            )
        if None in (prijs_nu, ruimte, slijtage_ct, duurste):
            uit["reden"] = "prijs, laadruimte, slijtage of ongedekt kwartier onbekend"
            return uit
        # v5.168.0: beide kanten met de marginale prijs (zie `_marginale_prijs`).
        prijs_incl = prijs_nu
        prijs_nu = self._marginale_prijs(prijs_nu, now)
        duurste = self._marginale_prijs(duurste, dt_util.parse_datetime(str(plan.get("duurste_ongedekt_om") or "")) or now)
        waarde = duurste * rendement / 100 - slijtage_ct / 100
        gat = min(ruimte, plan["nodig_kwh"] - plan["beschikbaar_kwh"])
        # v5.25.1: niet op het EERSTE moment dat het loont, maar op de
        # GOEDKOOPSTE. Gemeld: "hij begint nu direct op een veel te duur
        # moment te laden". Om 20:45 tegen 31 ct loonde het voor een
        # ochtendpiek van 52 ct - terwijl om 02:00 de stroom 24 ct kostte.
        goedkoopst = self._goedkoopste_laadmomenten(
            now, prijs_incl, plan.get("duurste_ongedekt_om"), gat
        )
        laden = waarde > prijs_nu and gat > 0 and goedkoopst
        uit.update(
            {
                "laden": laden,
                "prijs_nu_eur": round(prijs_nu, 4),
                "latere_prijs_eur": round(duurste, 4),
                "rendement_procent": round(rendement, 1),
                "slijtage_ct": round(slijtage_ct, 2),
                "waarde_eur": round(waarde, 4),
                "marge_ct": round((waarde - prijs_nu) * 100, 1),
                "gat_kwh": round(gat, 2),
                "datacorrectie_ct": self.laadcorrectie_ct(),
                "blok": plan.get("blok"),
                "nu_bij_de_goedkoopste": goedkoopst,
                "reden": (
                    "prijsdip: straks meer waard dan hij nu kost"
                    if laden
                    else (
                        "er komt een goedkoper moment om te laden"
                        if waarde > prijs_nu and gat > 0
                        else "geen dip: straks minder waard dan hij nu kost"
                    )
                ),
            }
        )
        return uit

    def laadbesluit_uit_het_net(
        self,
        now: datetime,
        blok_start: datetime | None,
        blok_eind: datetime | None,
    ) -> dict:
        """Loont het om NU uit het net bij te laden? (v5.21)

        Gemeld: "werkt het bijladen echt goed? Gezien ik dit nu regelmatig
        handmatig doe." Het EMS laadde alleen van het net op dagen met
        weinig zon. Op andere dagen rekende het erop dat de zon de accu
        vulde - ook als dat niet genoeg was en het goedkope blok duidelijk
        winst opleverde. Beide handmatige laadbeurten van de gebruiker
        waren rendabel: 7,8 en 10,5 ct/kWh na rendement en slijtage.

        Twee voorwaarden, allebei op bestaande grootheden:

        1. HET GAT. Hoeveel ruimte blijft er over nadat de zon heeft gedaan
           wat hij vandaag nog doet?
               gat = laadruimte - verwacht zonoverschot
           Zolang de saldering loopt met de VOORZICHTIGE zonverwachting:
           te veel laden kost dan bijna niets (het middagoverschot gaat
           tegen ongeveer dezelfde middagprijs het net op), te weinig laden
           kost de marge. Na de saldering met de gewone verwachting.

        2. DE MARGE. Is de VOLGENDE kWh straks meer waard dan hij nu kost?
           Dezelfde rekenregel als de verkooptoets:
               waarde = latere prijs x rendement - slijtage
           De latere prijzen van hoog naar laag. Wat al in de accu zit gaat
           naar de duurste kwartieren; de volgende kWh komt in het
           eerstvolgende kwartier daarna terecht, en dat kwartier bepaalt
           zijn waarde.

        Wordt elke ronde opnieuw bekeken. Naarmate de accu vult schuift dat
        kwartier naar goedkopere momenten, en het laden stopt precies waar
        het niet meer loont - of eerder, als het gat dicht is.
        """
        uit: dict = {"laden": False}
        if (
            blok_start is None
            or blok_eind is None
            or not (blok_start <= now < blok_eind)
        ):
            # v5.25: buiten het blok alleen in een prijsdip - zie `_dipbesluit`.
            return self._dipbesluit(now, blok_start)
        prijs_nu = self.huidige_prijs_eur_per_kwh()
        ruimte = self._resterende_laadruimte_kwh()
        rendement = self.learned_battery_efficiency_percent
        if rendement is None:
            rendement = float(
                self.instelling(
                    CONF_BATTERY_ROUND_TRIP_EFFICIENCY,
                    DEFAULT_BATTERY_ROUND_TRIP_EFFICIENCY_PERCENT,
                )
            )
        slijtage_ct = self._laadkosten_ct()  # v5.115.0: slijtage + datacorrectie
        if prijs_nu is None or ruimte is None or slijtage_ct is None:
            uit["reden"] = "prijs, laadruimte of slijtage onbekend"
            return uit
        # v5.117.0: balanceerlading vóór de hysterese - die stopt bij 97 %,
        # en juist de laatste procenten zijn nodig om te balanceren.
        if (balans := self._balanceer_laadbesluit(now, blok_eind, prijs_nu, ruimte)) is not None:
            return balans
        # v5.128.0 (punt 15): bij een negatieve of heel lage prijs vervallen
        # beide grenzen hieronder - dan mag de accu bijladen tot 100 %. De
        # laadregel (loont het?) beslist daarna gewoon.
        heel_laag = self._heel_lage_prijs(prijs_nu, self._heel_lage_prijs_grens_eur())
        if heel_laag:
            uit["heel_lage_prijs"] = True
        # v5.95: hysterese - zie `_laadblok_hysterese`.
        if not heel_laag and self._laadblok_hysterese(
            self.beschikbare_energie_kwh() or 0.0,
            (self.beschikbare_energie_kwh() or 0.0) + ruimte,
            self._laadt_uit_het_net(),
        ):
            uit["reden"] = (
                f"accu al {LAADBLOK_HERLAAD_DREMPEL:.0%} of voller; niet opnieuw bijladen"
            )
            uit["hysterese"] = True
            return uit
        # v5.127.2: en op de accustand zelf - zie LAADBLOK_HERLAAD_SOC_PROCENT.
        soc_nu = self.accustand_procent()
        if not heel_laag and self._accu_te_vol_voor_netladen(soc_nu, self._laadt_uit_het_net()):
            uit["reden"] = (
                f"accu al {soc_nu:.0f}% (vanaf {LAADBLOK_HERLAAD_SOC_PROCENT:.0f}%); "
                "niet opnieuw bijladen uit het net"
            )
            uit["hysterese"] = True
            return uit
        horizon_eind = now + timedelta(hours=24)
        later = sorted(
            (
                (e[2] / PRICE_SCALE_FACTOR, e[0])
                for e in (self._get_forecast_entries() or [])
                if blok_eind <= e[0] < horizon_eind
            ),
            key=lambda paar: paar[0],
            reverse=True,
        )
        if not later:
            uit["reden"] = "geen prijzen na het blok"
            return uit
        ontlaad_kw = abs(
            float(
                self.instelling(
                    CONF_MANUAL_DISCHARGE_POWER, DEFAULT_MANUAL_DISCHARGE_POWER
                )
            )
        ) / 1000
        per_kwartier = max(ontlaad_kw * 0.25, 0.05)
        salderen = self._is_salderen_active(now)
        def zonoverschot_tot(moment: datetime) -> float | None:
            if moment <= now:
                return 0.0
            return self._verwacht_zonoverschot_kwh(now, moment, veilig=salderen)

        beschikbaar = self.beschikbare_energie_kwh() or 0.0
        # v5.168.0: de afweging met de marginale prijs (bij een verwacht
        # salderingsoverschot zonder belastingdeel); het kiezen van de
        # goedkoopste kwartieren blijft op de prijsreeks zelf.
        later = sorted(((self._marginale_prijs(p, t), t) for p, t in later), key=lambda paar: paar[0], reverse=True)
        uit["prijs_nu_incl_eur"] = round(prijs_nu, 4)
        uit.update(
            self._laadregel(
                prijs_nu=self._marginale_prijs(prijs_nu, now),
                beschikbaar=beschikbaar,
                ruimte=ruimte,
                later=later,
                rendement=rendement,
                slijtage_ct=slijtage_ct,
                per_kwartier=per_kwartier,
                zonoverschot=zonoverschot_tot,
                vol_om=self._zon_vol_om(now, beschikbaar, ruimte, horizon_eind),
            )
        )
        uit["voorzichtige_zon"] = salderen
        uit["datacorrectie_ct"] = self.laadcorrectie_ct()
        return self._laad_op_goedkoopste(now, uit)

    def _laadt_uit_het_net(self) -> bool:
        """Laadde de vorige ronde uit het net? (v5.95)"""
        return getattr(self, "last_reason", None) in (
            "grid_charging_profitable",
            "grid_charging_low_solar",
        )

    @staticmethod
    def _laadblok_hysterese(beschikbaar: float, bruikbaar: float, laadt_al: bool) -> bool:
        """Niet opnieuw laden in het blok als de accu al (bijna) vol is (v5.95).

        Gemeld 13-10: het plan zette 02:15-02:45 op "laden van net" tussen
        kwartieren "slim" - de accu zakte door het nachtverbruik naar 99% en
        werd weer bijgetopt. Dat levert niets op en geeft een onrustig plan.
        Een lading die al loopt mag gewoon doorladen tot vol; alleen een
        NIEUWE start vanaf ``LAADBLOK_HERLAAD_DREMPEL`` en hoger valt af.
        Dezelfde toets voor de beslissing en het kwartierplan.
        """
        if laadt_al or bruikbaar <= 0:
            return False
        return beschikbaar >= LAADBLOK_HERLAAD_DREMPEL * bruikbaar - 1e-9

    @staticmethod
    def _accu_te_vol_voor_netladen(soc_procent: float | None, laadt_al: bool) -> bool:
        """Geen NIEUWE netlading vanaf LAADBLOK_HERLAAD_SOC_PROCENT (v5.127.2).

        Gemeld 25-10 16:24: de accu zakte van 98 naar 97 %, en binnen een
        halve minuut stond hij op manual -2400 - 2,2 kW laden, terwijl het
        plan "slim, 0,5 kW ontladen" zei. De hysterese van v5.95 rekent met
        het bruikbare deel (boven de ondergrens); 97 % op de sensor is daar
        96,7 % en viel er net onder. Een volle accu bijtoppen levert hooguit
        een paar cent op en maakt de sturing onrustig. Een lading die al
        loopt, laadt wel door tot vol; onbekende stand = geen grens.
        """
        if laadt_al or soc_procent is None:
            return False
        return soc_procent >= LAADBLOK_HERLAAD_SOC_PROCENT - 1e-9

    def _heel_lage_prijs_grens_eur(self) -> float:
        """Tot welke all-in-prijs heet een prijs "heel laag"? (v5.128.0, punt 15)

        Er was geen bestaande drempel voor. Gekozen: de gemeten
        energiebelasting plus btw per kWh (`_gemeten_belastingdeel_eur_per_kwh`,
        bij deze aansluiting ~11,1 ct). Een all-in-prijs daaronder betekent
        een kale marktprijs van nul of lager: je betaalt alleen nog belasting.
        Zo'n kWh kost na rendement en slijtage ~18 ct uit de accu, en dat is
        goedkoper dan vrijwel elk ander kwartier. Begrensd op
        HEEL_LAGE_PRIJS_GRENS_MAX_EUR; zonder kale prijs (geen excl-veld) is
        de grens 0, dan geldt alleen een negatieve all-in-prijs.
        """
        ronde = getattr(self, "_forecast_cache_ronde", None)
        bewaard = getattr(self, "_heel_laag_grens_cache", None)
        if ronde is not None and bewaard is not None and bewaard[0] == ronde:
            return bewaard[1]
        # Het lezen van de kale reeks zet `prijsreeks_bevindingen` op die
        # reeks; de bevindingen horen bij de belaste reeks en blijven staan.
        bevindingen = getattr(self, "prijsreeks_bevindingen", None)
        try:
            grens = float(self._gemeten_belastingdeel_eur_per_kwh() or 0.0)
        except Exception:  # noqa: BLE001 - een grens mag de beslissing nooit breken
            grens = 0.0
        finally:
            if bevindingen is not None:
                self.prijsreeks_bevindingen = bevindingen
        grens = min(max(0.0, grens), HEEL_LAGE_PRIJS_GRENS_MAX_EUR)
        if ronde is not None:
            self._heel_laag_grens_cache = (ronde, grens)
        return grens

    @staticmethod
    def _heel_lage_prijs(prijs_eur: float | None, grens_eur: float) -> bool:
        """Negatief of heel laag: dan mag de accu bijladen tot 100 % (v5.128.0).

        Sinds v5.127.2 start er vanaf 95 % accustand (en sinds v5.95 vanaf
        97 % van het bruikbare deel) geen nieuwe netlading. Bij een negatieve
        all-in-prijs, of een prijs op of onder de grens van
        `_heel_lage_prijs_grens_eur`, geldt die rem niet.
        """
        if prijs_eur is None:
            return False
        return prijs_eur <= max(0.0, grens_eur) + 1e-9

    # v5.126.0 (L-EMS-034): het laatst gekozen goedkope blok (bewaard).
    _gekozen_blok_start: datetime | None = None

    def _lopend_blok(self, now: datetime, nieuw_start, nieuw_eind, entries=None) -> tuple:
        """Het lopende blok houden tot het eindigt (v5.28.5).

        Eerst uit het geheugen; anders uit de prijzen van vandaag: het blok
        van vandaag over de HELE dag bepaald (zoals het om middernacht al
        vaststond). Ligt nu daarin, dan is dat het lopende blok - ook direct
        na een herstart. Een laat duur kwartier wordt zo nooit per ongeluk
        een blok.
        """
        oud_start = getattr(self, "last_cheap_block_start", None)
        oud_eind = getattr(self, "last_cheap_block_end", None)
        if oud_start is not None and oud_eind is not None and oud_start <= now < oud_eind:
            return oud_start, oud_eind
        if nieuw_start is not None and nieuw_start <= now:
            return nieuw_start, nieuw_eind
        # v5.126.0 (L-EMS-034): lag vóór de herstart het blok van een LATERE
        # dag al vast, dan liep er geen blok van vandaag - dan komt dat ook
        # niet terug. Leerronde 24-10: op 23-10 kwam na een herstart een blok
        # van vandaag terug terwijl dat van morgen al gekozen was (≈ € 0,19,
        # en de accu werd er niet vol van).
        gekozen = getattr(self, "_gekozen_blok_start", None)
        if (
            isinstance(gekozen, datetime)
            and gekozen.tzinfo is not None
            and gekozen > now
            and gekozen.date() > now.date()
        ):
            return nieuw_start, nieuw_eind
        vandaag = [e for e in (entries or []) if e[0].date() == now.date()]
        if vandaag:
            dag_begin = now.replace(hour=0, minute=0, second=0, microsecond=0)
            start, eind = self._cheapest_block_range(vandaag, dag_begin)
            if start is not None and eind is not None and start <= now < eind:
                return start, eind
        return nieuw_start, nieuw_eind

    def _laad_op_goedkoopste(self, moment: datetime, regel: dict) -> dict:
        """Loont laden, laad dan alleen in de goedkoopste kwartieren (v5.28.5).

        Gemeld op 4 oktober: "Waarom straks bij duurdere goedkope uren wel
        manueel laden en nu niet??" Het plan laadde om 14:45 tegen 21,9 ct,
        terwijl er om 14:00 kwartieren van 18,5 ct waren: de laadregel laadde
        zodra het loonde. De dipregel kiest sinds v5.25.1 al de goedkoopste
        kwartieren; nu de laadregel in het blok ook - met dezelfde functie,
        voor de beslissing en het plan. Er wordt niet meer geladen, alleen
        goedkoper.
        """
        if not regel.get("laden"):
            return regel
        # v5.104.0: niet meer kwartieren zoeken dan er lading LOONT. Het gat
        # kan groter zijn dan wat lonend is; dan koos dit de goedkoopste
        # kwartieren voor het hele gat en laadde het ook in duurdere.
        nodig_kwh = regel.get("gat_kwh") or 0.0
        if regel.get("lonend_kwh") is not None:
            nodig_kwh = min(nodig_kwh, regel["lonend_kwh"])
        goedkoopst = self._goedkoopste_laadmomenten(
            moment, regel.get("prijs_nu_incl_eur", regel["prijs_nu_eur"]), regel.get("nodig_vanaf"), nodig_kwh
        )
        uit = {**regel, "nu_bij_de_goedkoopste": goedkoopst}
        if not goedkoopst:
            uit["laden"] = False
            uit["reden"] = "loont, maar er komen goedkopere kwartieren voordat de lading nodig is"
        return uit

    @staticmethod
    def _laadregel(
        *,
        prijs_nu: float,
        beschikbaar: float,
        ruimte: float,
        later: list,
        rendement: float,
        slijtage_ct: float,
        per_kwartier: float,
        zonoverschot,
        vol_om: datetime | None = None,
    ) -> dict:
        """De kern van het laadbesluit, zonder live gegevens (v5.22).

        Eén rekenregel voor de BESLISSING (met de gemeten stand) en het
        KWARTIERPLAN (met de gesimuleerde stand), zodat het plan precies
        voorspelt wat de beslissing straks doet - geen tweede definitie.

        `later` is een lijst (prijs, moment) van hoog naar laag;
        `zonoverschot(tot)` geeft het verwachte zonoverschot tot `tot`.
        """
        # v5.86 (L-EMS-021): na het moment dat de zon de accu vanzelf vol
        # heeft, levert de ZON die kwartieren. Lading van nu is alleen iets
        # waard in de kwartieren DAARVOOR; wat dan nog in de accu zit,
        # verdringt zon die het net op gaat. Zo'n kWh is precies de
        # exportprijs van dat moment waard (de zon-kWh die anders was
        # opgeslagen), zonder rendement of slijtage - die gelden voor
        # beide kWh's gelijk.
        if vol_om is not None:
            tot_vol = sorted(
                ((moment, p) for p, moment in later if moment <= vol_om),
                key=lambda paar: paar[0],
            )
            voor_vol = [(p, moment) for p, moment in later if moment < vol_om]
            k = int(max(beschikbaar, 0.0) // per_kwartier) + 1  # v5.161.2: negatief (accu onder de bodem) = 0
            if k > len(voor_vol):
                exportprijs = tot_vol[-1][1] if tot_vol else None
                uit = {
                    "laden": False,
                    "prijs_nu_eur": round(prijs_nu, 4),
                    "ruimte_kwh": round(ruimte, 2),
                    "zon_vol_om": vol_om.isoformat(),
                    "verdringt_zon": True,
                    "gat_kwh": round(ruimte, 2),
                    "nodig_vanaf": vol_om.isoformat(),
                }
                if exportprijs is None:
                    uit["reden"] = "de zon vult de accu vanzelf; laden verdringt alleen zon"
                    return uit
                uit.update(
                    {
                        "exportprijs_eur": round(exportprijs, 4),
                        "waarde_eur": round(exportprijs, 4),
                        "marge_ct": round((exportprijs - prijs_nu) * 100, 1),
                        "laden": exportprijs > prijs_nu,
                        "reden": (
                            "loont: goedkoper dan de zon die er straks door het net op gaat"
                            if exportprijs > prijs_nu
                            else f"de zon vult de accu om {vol_om:%H:%M}; laden verdringt alleen zon"
                        ),
                    }
                )
                return uit
            later = voor_vol
        # Het kwartier waarin de VOLGENDE kWh terechtkomt: na de kwartieren
        # die de lading van nu al vult.
        k = int(max(beschikbaar, 0.0) // per_kwartier) + 1  # v5.161.2: zie boven
        if k > len(later):
            return {"laden": False, "reden": "de lading van nu dekt alle latere kwartieren al"}
        zon_tot = min(moment for _p, moment in later[:k])
        overschot = zonoverschot(zon_tot)
        if overschot is None:
            return {"laden": False, "reden": "geen verbruiksinschatting"}
        gat = ruimte - overschot
        uit = {
            "prijs_nu_eur": round(prijs_nu, 4),
            "ruimte_kwh": round(ruimte, 2),
            "zonoverschot_kwh": round(overschot, 2),
            "gat_kwh": round(gat, 2),
            "laden": False,
            # v5.28.5: tot wanneer het laden mag wachten - het vroegste
            # kwartier waartegen de lading wordt gewaardeerd.
            "nodig_vanaf": zon_tot.isoformat(),
        }
        if gat <= 0:
            uit["reden"] = "de zon vult de accu vandaag vanzelf"
            return uit
        latere_prijs = later[k - 1][0]
        waarde = latere_prijs * rendement / 100 - slijtage_ct / 100
        # v5.104.0: hoeveel lading van nu nog loont. `later` loopt van duur
        # naar goedkoop; vanaf het k-de kwartier telt elk kwartier dat na
        # rendement en slijtage meer waard is dan de prijs nu. Gemeld 19-10:
        # het plan laadde om 12:45 tegen 33,7 ct omdat het GAT (ruim 5 kWh)
        # meer kwartieren vroeg dan er goedkopere waren - terwijl maar een
        # paar kWh loonde. Die paar kWh horen in de goedkoopste kwartieren.
        lonend = sum(
            1 for p, _m in later[k - 1:] if p * rendement / 100 - slijtage_ct / 100 > prijs_nu
        )
        uit.update(
            {
                "lonend_kwh": round(lonend * per_kwartier, 2),
                "latere_prijs_eur": round(latere_prijs, 4),
                "rendement_procent": round(rendement, 1),
                "slijtage_ct": round(slijtage_ct, 2),
                "waarde_eur": round(waarde, 4),
                "marge_ct": round((waarde - prijs_nu) * 100, 1),
                "laden": waarde > prijs_nu,
                "reden": (
                    "loont: straks meer waard dan hij nu kost"
                    if waarde > prijs_nu
                    else "loont niet: straks minder waard dan hij nu kost"
                ),
            }
        )
        return uit

    @staticmethod
    def _verschuiving_en_bodem_zin(u: dict) -> str:
        """De verschuiving en de bodem in gewone taal, voor de reservekaart (v5.23)."""
        delen = []
        if u.get("regelverschuiving_w"):
            delen.append(
                f"In het diepste tekort zit de verschuiving op de P1-meter: "
                f"{u['regelverschuiving_w']} W, de hele nacht."
            )
        if u.get("bodem_kwh") is not None:
            delen.append(
                f"Bodem: {u['bodem_kwh']:.2f} kWh".replace(".", ",")
                + " - daaronder wordt nooit verkocht, ook niet in de duurste piek."
                + (" De bodem is nu bindend." if u.get("bodem_bindend") else "")
            )
        return " ".join(delen)

    def get_reserve_margin_overview(self) -> dict:
        """Hoe de reservemarge is opgebouwd (v1.87.0).

        Gevraagd: "Waar zie ik die 40?" Nergens - hij stond alleen in de
        diagnostiek-export. Precies de reden waarom de lus van v1.86.0
        dagen kon doorlopen zonder dat iemand het zag: de marge liep op
        van 25 naar 40% wegens tekortdagen, terwijl de verkooptoets dat
        getal negeerde.

        Een zelfcorrigerend mechanisme dat zichzelf niet laat zien, is
        niet te controleren.
        """
        u = self.last_reserve_margin_breakdown or {}
        if not u:
            # v3.32.0: zeggen WAAROM er niets staat.
            #
            # Gevonden in de export van 12:28: "Nog geen reserve-
            # berekening gemaakt" terwijl de integratie al uren draaide.
            # De oorzaak was de kalibratiestand: die tak keert terug
            # vóór de reserve wordt berekend. Dat is geen storing, maar
            # de kaart suggereerde van wel.
            if self.kalibratie:
                return {
                    "beschikbaar": False,
                    "reden": (
                        "De kalibratiestand staat aan; de reserve wordt "
                        "niet berekend zolang de aansturing stilligt."
                    ),
                }
            if self.force_manual:
                return {
                    "beschikbaar": False,
                    "reden": (
                        "Handmatige overname staat aan; de reserve wordt "
                        "niet berekend."
                    ),
                }
            return {
                "beschikbaar": False,
                "reden": "Nog geen reserveberekening gemaakt.",
            }
        onderdelen = [
            ("Basis", u.get("base_percent", 0.0), "vast"),
            (
                f"Weinig zon ({u.get('consecutive_low_solar_days', 0)} dagen)",
                u.get("low_solar_bonus_percent", 0.0),
                "dynamisch",
            ),
            (
                f"Tekortdagen ({u.get('recent_shortfall_days', 0)} recent)",
                u.get("shortfall_bonus_percent", 0.0),
                "dynamisch",
            ),
            (
                f"Overschotdagen ({u.get('recent_excess_days', 0)} recent)",
                -u.get("excess_reduction_percent", 0.0),
                "dynamisch",
            ),
            (
                "Onbeschermde nacht na een duur kwartier",
                u.get("unprotected_aftermath_percent", 0.0),
                "vast",
            ),
            # v3.29.0: en de PV-onzekerheid, die hier ontbrak.
            #
            # Gevonden bij de doorlichting van 19 augustus: de kaart
            # toonde 40% totaal terwijl de onderdelen op 30 uitkwamen.
            # De ontbrekende 10 zat wel in de berekening en niet in de
            # opsomming - een verschil dat niemand kan naslaan is erger
            # dan geen opsomming.
            (
                "Onzekerheid in de zonvoorspelling",
                u.get("pv_onzekerheid_percent", 0.0),
                "dynamisch",
            ),
        ]
        opgeteld = round(sum(w for _n, w, _s in onderdelen), 1)
        totaal = u.get("total_percent")
        return {
            "beschikbaar": True,
            "totaal_procent": totaal,
            # v3.29.0: als de som ooit weer uiteenloopt met het totaal,
            # hoort dat op de kaart te staan en niet stilletjes.
            "onderdelen_opgeteld_procent": opgeteld,
            "sluit_aan": (
                totaal is None or abs(opgeteld - totaal) < 0.05
            ),
            "vast_procent": round(
                sum(w for _n, w, s in onderdelen if s == "vast"), 1
            ),
            "dynamisch_procent": round(
                sum(w for _n, w, s in onderdelen if s == "dynamisch"), 1
            ),
            "onderdelen": [
                {"naam": n, "procent": round(w, 1), "soort": s}
                for n, w, s in onderdelen
                if w
            ],
            "diepste_tekort_kwh": u.get("needed_kwh_before_margin"),
            # v5.56: hetzelfde tekort, rond het blok gesplitst.
            **self._diepste_tekort_gesplitst(u, u.get("needed_kwh_before_margin")),
            "reserve_kwh": u.get("reserve_kwh_after_margin"),
            # v5.23: voor de doorklik "waarom is de reserve zo hoog" - de
            # verschuiving op de P1-meter (v5.20) en de bodem (v3.92.1)
            # stonden wel in de berekening, maar niet in deze uitsplitsing.
            "regelverschuiving_w": u.get("regelverschuiving_w"),
            "bodem_kwh": u.get("bodem_kwh"),
            "bodem_bindend": u.get("bodem_bindend"),
            # De zin voor de kaart komt HIER vandaan, niet uit een sjabloon:
            # logica in een dashboardveld gaat stil kapot (v3.95.4).
            "verschuiving_en_bodem_zin": self._verschuiving_en_bodem_zin(u),
            "toelichting": (
                "De marge staat bovenop het diepste tekort onderweg. Elke "
                "tekortdag verhoogt hem met 5 procentpunt, elke dag met "
                "overschot verlaagt hem met 3. Sinds v1.86.0 hanteert de "
                "verkooptoets dezelfde marge als de ontlaadreserve."
            ),
        }

    def _reserve_margin_factor(self) -> float:
        """De marge die de ontlaadreserve op dit moment aanhoudt
        (v1.86.0).

        Gevraagd: "Maar dan worden toch simpelweg de manual
        ontlaadkwartieren tegen een hoge prijs gereduceerd om de nacht te
        halen?"

        Precies - en dat gebeurde niet, omdat er twee reserves in omloop
        waren. De ontlaadreserve is zelfcorrigerend (elke tekortdag
        verhoogt hem), de verkooptoets hield een vaste 1,15 aan. Die
        verkocht dus precies de buffer weg die de tekortbonus had
        opgebouwd.

        Deze functie geeft die ene marge terug, zodat beide kanten
        hetzelfde getal gebruiken. Terugval op de vaste factor zolang de
        uitsplitsing er nog niet is - dat is de stand vlak na een
        herstart.
        """
        uitsplitsing = self.last_reserve_margin_breakdown or {}
        totaal = uitsplitsing.get("total_percent")
        if totaal is None:
            return SELL_RESERVE_DEEPEST_SAFETY_FACTOR
        return 1.0 + totaal / 100

    def _reserve_plafond_kwh(self) -> float | None:
        """Het hoogste dat een reserve kan zijn (v5.81.1, akkoord Ruud 11-10).

        De reserve werd afgekapt op de TOTALE capaciteit (8,64 kWh), maar
        wordt vergeleken met de beschikbare energie, en die telt pas vanaf de
        minimum-laadstand en loopt tot de bovengrens: hooguit 7,78 kWh (8,64
        x 0,90). Bond het plafond - 10-10 19:30: (5,42 + 4,20) x 1,25 = 12,03
        -> 8,64 - dan zei de brug structureel "niet genoeg", ook met een
        volle accu. Nu: wat er tussen de grenzen past
        (`bruikbaar_tussen_grenzen_kwh`); zonder die waarde de capaciteit.
        """
        tussen = self.bruikbaar_tussen_grenzen_kwh()
        if tussen:
            return tussen
        return self.bruikbare_capaciteit_kwh()

    def _reserve_bodem_kwh(self) -> float:
        """De ondergrens onder elke reserve (v3.74.0, één plek v3.92.3).

        Geen voorspelling maar een vaste marge: een percentage van de
        bruikbare capaciteit. Bestaat omdat de reserve een marge
        VERMENIGVULDIGT met het diepste tekort, en dat tekort nul is
        zodra de voorspelling zegt dat de zon het huis morgen dekt.
        Vijfenvijftig procent van nul is nul.

        v3.92.3: op één plek, want het waren er vier.

        Het commentaar bij de bodem beweerde sinds v3.74.0 al dat hij "op
        ÉÉN plek staat zodat hij doorwerkt in het ontladen, de
        verkooptoets en de kwartierplanning tegelijk". Dat was de
        bedoeling; in de code stond hij alleen in de reserveberekening,
        en die gaf tot v3.92.1 de waarde van vóór de bodem terug.

        Gemeten op 31 augustus 10:11, met v3.92.2 al geïnstalleerd:

            reserve (bodem bindend)   1,296 kWh
            beschikbaar               0,69 kWh
            verkooptoets              alles vrij te verkopen

        Zonder capaciteit geen bodem: een grens uit het niets is erger
        dan geen grens.
        """
        return (self.bruikbare_capaciteit_kwh() or 0.0) * RESERVE_BODEM_FRACTIE

    def _get_dynamic_discharge_reserve_kwh(
        self,
        now: datetime,
        cheap_block_start: datetime | None,
        bewaar: bool = True,
    ) -> float | None:
        """De ene reserve, één keer per ronde per (moment, blok) (v5.42).

        Gemeld na de herstart op v5.41 (21:43): "Eén reserve: brug wijkt af
        van de sturing". Geen tweede formule, maar dezelfde functie op twee
        momenten in de ronde met andere invoer. De brug rekent vóór het
        staartstuk, de schemaprojectie erna - en daartussen zet
        `_meet_lange_reserve` het deel na het goedkope blok. Na een herstart
        staat dat op nul (niet bewaard): de brug rekende zonder de 1,87 kWh
        lange horizon, de projectie mét, en de projectie schreef de
        uitsplitsing. Hetzelfde kan bij het afsluiten van de nacht, als een
        nieuwe tekortdag de marge halverwege de ronde verandert.

        Nu is de eerste berekening in een ronde DE reserve van die ronde:
        brug, sturing, verkooptoets, projectie en Monte Carlo lezen
        hetzelfde getal en dezelfde uitsplitsing. Wat het staartstuk
        verandert, telt vanaf de volgende ronde - voor iedereen tegelijk.
        Zonder rondestempel (tests, opstarten) wordt er gewoon gerekend.
        """
        stempel = self._ronde_stempel()
        sleutel = (
            (stempel, now.isoformat(), cheap_block_start.isoformat())
            if stempel is not None and cheap_block_start is not None
            else None
        )
        cache = self._reserve_ronde_cache
        if sleutel is None or cache is None or cache[0] != stempel:
            cache = self._reserve_ronde_cache = (stempel, {})
        if sleutel is not None and sleutel in cache[1]:
            reserve_kwh, uitsplitsing = cache[1][sleutel]
        else:
            self._reserve_laatste_uitsplitsing = None
            # v5.186.0 (punt 33): een eigen correctiebudget, ook binnen een plan.
            with self._eigen_correctiebudget():
                reserve_kwh = self._bereken_dynamische_reserve_kwh(
                    now, cheap_block_start, bewaar
                )
            uitsplitsing = self._reserve_laatste_uitsplitsing
            if sleutel is not None and uitsplitsing is not None:
                cache[1][sleutel] = (reserve_kwh, uitsplitsing)
        # v5.70: de uitsplitsing bij DEZE aanvraag, voor de verkoopreserve.
        self._reserve_gevraagde_uitsplitsing = uitsplitsing
        if bewaar and uitsplitsing is not None:
            # v5.87 (L-EMS-020): een sprong in de reserve vastleggen met de
            # onderdelen ervoor en erna. Alleen meten; stuurt niets.
            self._noteer_reserve_sprong(
                now, cheap_block_start, self.last_reserve_margin_breakdown, uitsplitsing
            )
            self.last_reserve_margin_breakdown = uitsplitsing
            self._lange_horizon_extra_vandaag = max(
                self._lange_horizon_extra_vandaag,
                uitsplitsing.get("lange_horizon_extra_kwh") or 0.0,
            )
        return reserve_kwh

    # v5.87 (L-EMS-020): de onderdelen van de reserve die bij een sprong
    # worden vastgelegd.
    _RESERVE_SPRONG_VELDEN = (
        "reserve_kwh_after_margin",
        "needed_kwh_before_margin",
        "lange_horizon_extra_kwh",
        "regelverschuiving_w",
        "total_percent",
        "airco_ochtend_extra_kwh",
        "airco_gebruik_extra_kwh",
        "temperatuur_extra_kwh",
        "live_correctie_extra_kwh",
        "live_correctie_verhouding",
        "ongekapt_kwh",
        "bodem_bindend",
        "boven_capaciteit",
    )

    def _noteer_reserve_sprong(
        self,
        now: datetime,
        blok: datetime | None,
        oud: dict | None,
        nieuw: dict | None,
    ) -> None:
        """Een sprong in de reserve vastleggen, met de uitsplitsing ervoor
        en erna (v5.87, L-EMS-020; meetbaarheid, stuurt niets).

        Leerronde 11-10 19:40/23:40: de reserve en de behoefte tot het blok
        sprongen binnen minuten 0,6-1,9 kWh heen en weer zonder
        verbruiksstap (H-EMS-10). Om 19:56 stopte zo een geplande verkoop.
        De oorzaak was niet te achterhalen: de uitsplitsing staat alleen
        live in het geheugen en de P1-sensoren staan niet in de recorder.
        Nu: verandert de reserve of de behoefte zonder marge meer dan
        RESERVE_SPRONG_DREMPEL_KWH tussen twee rondes, dan een regel met
        tijd, blok, uren tot het blok en per onderdeel oud/nieuw. Begrensd
        tot de laatste RESERVE_SPRONGEN_MAX.
        """
        if not isinstance(oud, dict) or not isinstance(nieuw, dict) or not oud:
            return
        try:
            def _f(d: dict, k: str):
                v = d.get(k)
                return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None

            delta = 0.0
            for k in ("reserve_kwh_after_margin", "needed_kwh_before_margin"):
                a, b = _f(oud, k), _f(nieuw, k)
                if a is not None and b is not None:
                    delta = max(delta, abs(b - a))
            if delta <= RESERVE_SPRONG_DREMPEL_KWH:
                return
            regel: dict = {
                "tijd": now.isoformat(timespec="seconds"),
                "blok": blok.isoformat() if blok is not None else None,
                "uren_tot_blok": (
                    round((blok - now).total_seconds() / 3600, 2)
                    if blok is not None else None
                ),
                "ronde_oud": oud.get("ronde"),
                "ronde_nieuw": nieuw.get("ronde"),
            }
            # v5.98.1 (L-EMS-020-aanvulling): een sprong in de eerste
            # minuten na een herstart is opstarten (sensoren en geleerde
            # waarden komen binnen), geen gedrag van de reserve. Markeren en
            # niet meetellen in het aantal.
            gestart = self._started_at
            if gestart is not None:
                try:
                    na_start = (now - gestart).total_seconds()
                except TypeError:
                    na_start = None
                if na_start is not None and 0 <= na_start < RESERVE_SPRONG_HERSTART_S:
                    regel["na_herstart"] = True
            for k in self._RESERVE_SPRONG_VELDEN:
                regel[k] = [oud.get(k), nieuw.get(k)]
            # Het onderdeel met de grootste verandering (kWh-velden; de
            # regelverschuiving omgerekend over de uren tot het blok).
            bijdragen: dict = {}
            # v5.120.0 (H-EMS-14): ook de live verbruikscorrectie. Leerronde
            # 23-10: 17 sprongen "basisbehoefte" van ~1,5 kWh (20:11-23:00) =
            # precies de begrenzing van de live correctie die aan en uit ging.
            for k in (
                "lange_horizon_extra_kwh", "airco_ochtend_extra_kwh",
                "airco_gebruik_extra_kwh", "temperatuur_extra_kwh",
                "live_correctie_extra_kwh",
            ):
                a, b = _f(oud, k), _f(nieuw, k)
                if a is not None and b is not None:
                    bijdragen[k] = round(b - a, 3)
            a, b = _f(oud, "regelverschuiving_w"), _f(nieuw, "regelverschuiving_w")
            if a is not None and b is not None and regel["uren_tot_blok"] is not None:
                bijdragen["regelverschuiving_x_uren_kwh"] = round(
                    (b - a) / 1000 * max(0.0, regel["uren_tot_blok"]), 3
                )
            regel["bijdragen_kwh"] = bijdragen
            if bijdragen:
                regel["grootste_onderdeel"] = max(
                    bijdragen, key=lambda k: abs(bijdragen[k])
                )
            # v5.115.1 (L-EMS-027): op 21-10 telden 29 "sprongen" terwijl de
            # reserve gelijk bleef (afgekapt, 10,37 kWh) en alle bijdragen 0
            # waren; `grootste_onderdeel` noemde dan de eerste sleutel
            # (lange_horizon_extra_kwh). Verklaren de onderdelen niets, dan
            # zat het in de basisbehoefte. Verandert alleen de behoefte en
            # niet de reserve zelf, dan apart tellen (geen reservesprong).
            if not bijdragen or max(abs(v) for v in bijdragen.values()) < RESERVE_SPRONG_VERKLAARD_KWH:
                regel["grootste_onderdeel"] = "basisbehoefte"
            a, b = _f(oud, "reserve_kwh_after_margin"), _f(nieuw, "reserve_kwh_after_margin")
            if a is not None and b is not None and abs(b - a) <= RESERVE_SPRONG_DREMPEL_KWH:
                regel["alleen_behoefte"] = True
            sprongen = self.reserve_sprongen
            sprongen.append(regel)
            del sprongen[:-RESERVE_SPRONGEN_MAX]
        except Exception:  # noqa: BLE001 - meten mag de sturing nooit raken
            _LOGGER.debug("Reservesprong niet vastgelegd", exc_info=True)

    # v5.125.0 (L-EMS-033): de reservesprongen gaan mee in de opslag.
    # Leerronde 23-10: twee keer per dag na een herstart leeg, en de
    # attributen staan niet in de recorder - de sprong van 12:33 was alleen
    # nog uit de state-string te halen. None tot de eerste sprong (de
    # property maakt per coördinator een eigen lijst).
    _reserve_sprongen: list | None = None

    @property
    def reserve_sprongen(self) -> list:
        """De laatste reservesprongen (v5.87, L-EMS-020)."""
        lijst = self.__dict__.get("_reserve_sprongen")
        if not isinstance(lijst, list):
            # Ook een onleesbare opslag (v5.125.0): opnieuw beginnen.
            lijst = self.__dict__["_reserve_sprongen"] = []
        elif not all(isinstance(r, dict) for r in lijst):
            lijst[:] = [r for r in lijst if isinstance(r, dict)]
        return lijst

    # v5.42: zie `_get_dynamic_discharge_reserve_kwh`.
    _reserve_ronde_cache: tuple | None = None
    _reserve_laatste_uitsplitsing: dict | None = None
    _reserve_gevraagde_uitsplitsing: dict | None = None

    def marge_tekortnachten(self) -> int:
        """Tekortnachten die de marge verhogen (v5.70, L-EMS-013).

        Elke tekortnacht telde: ook een economische, waarin de accu bewust
        niet vol was omdat bijladen uit het net niet loonde. Dat is geen te
        krappe reserve, en de opslag van 5% hield de accu daarna een week
        's avonds voller dan nodig. Een nacht zonder soort telt als
        onbekend en telt mee (huis gaat voor).

        v5.72 (akkoord Ruud 10-10): onbekend telt ook niet meer mee. Een
        nacht die niet na te gaan is, bewijst geen te krappe reserve; hij
        wordt wel vastgelegd en gemeld, maar verhoogt de marge niet blind.
        Zie `MARGE_TELT_NIET_MEE_SOORTEN`.
        """
        return sum(
            1
            for r in self.reserve_daily_records or []
            if isinstance(r, dict)
            and r.get("shortfall")
            and (r.get("tekort_soort") or TEKORTSOORT_ONBEKEND)
            not in MARGE_TELT_NIET_MEE_SOORTEN
        )

    def _voorspelde_buitentemp_c(self, van: datetime, tot: datetime) -> float | None:
        """Gemiddelde voorspelde buitentemperatuur over een venster, met de
        geleerde bias (v5.68). None zonder voorspelling."""
        bias = self.climate_forecast_learned_bias_c or 0.0
        waarden = [
            t + bias for moment, t in (self._climate_cached_forecast or [])
            if van - timedelta(hours=1) < moment < tot
        ]
        return sum(waarden) / len(waarden) if waarden else None

    def _temperatuur_extra_kwh(
        self, now: datetime, tot: datetime | None, al_erbij_kwh: float = 0.0
    ) -> dict:
        """Het temperatuurmodel in de reserve (v5.68, akkoord Ruud).

        Het EMS leert het nachtverbruik per buitentemperatuur
        (`_predict_temp_consumption_kw`), maar de reserve rekende alleen met
        het uurprofiel van de laatste dagen. Op de eerste koude nacht na een
        zachte week ligt dat profiel te laag. Nu: zegt het model bij de
        voorspelde temperatuur meer dan het profiel, dan komt het verschil
        erbij. Nooit minder - het profiel wordt niet verlaagd.

        Het model doet alleen mee als het zichzelf bruikbaar vindt (genoeg
        metingen over een breed genoeg temperatuurbereik, geen positieve
        helling onder het gemeten bereik).

        `al_erbij_kwh`: wat er al bovenop het profiel kwam (de geplande
        ochtendverwarming) - het model ziet de hele nacht, dus dat telt
        het niet nog eens.
        """
        leeg = {"extra_kwh": 0.0, "model_kw": None}
        if tot is None or tot <= now:
            return leeg
        buiten = self._voorspelde_buitentemp_c(now, tot)
        model_kw = self._predict_temp_consumption_kw(buiten) if buiten is not None else None
        profiel = self._estimate_consumption_kwh_for_period(now, tot)
        if model_kw is None or model_kw <= 0 or profiel is None:
            return leeg
        uren = (tot - now).total_seconds() / 3600
        return {
            "extra_kwh": round(max(model_kw * uren - profiel - al_erbij_kwh, 0.0), 3),
            "model_kw": round(model_kw, 3),
        }

    def _bereken_dynamische_reserve_kwh(
        self,
        now: datetime,
        cheap_block_start: datetime | None,
        bewaar: bool = True,
    ) -> float | None:
        """How much energy (kWh) actually needs to stay in the battery
        right now: the estimated baseline household consumption until the
        cheap block, minus expected PV production over that period, plus
        a safety margin - instead of a flat SoC percentage.

        This deliberately does NOT also add a reservation for other
        upcoming expensive quarters today (unlike the energy bridge
        check's needed_kwh) - that reservation governs whether to
        postpone *charging*, whereas this governs how far we can safely
        *discharge* right now without dipping below what's needed for the
        rest of the bridge. Each expensive quarter checks this
        independently as it arrives.

        Returns None if there isn't enough information to compute this
        (no cheap block found, or no consumption estimate available) -
        callers should fall back to the flat SoC percentage in that case.
        """
        if cheap_block_start is None or now >= cheap_block_start:
            # v4.9: geen reserve, dus ook geen uitsplitsing. Die bleef
            # staan op de waarde van vóór het goedkope blok, en dan
            # toont het dashboard een reserve die niet meer geldt en
            # meldt de zelfcontrole een tweede definitie die er niet is.
            if bewaar:
                self.last_reserve_margin_breakdown = {}
            return None

        hours_until_cheap = max((cheap_block_start - now).total_seconds() / 3600, 0)
        if hours_until_cheap <= 0:
            return None

        # v5.120.0 (H-EMS-14): de live correctie van DEZE wandeling (zie
        # `_segmenten_verbruik_zon`); leeg als de wandeling niet liep.
        self._laatste_live_correctie = None
        needed_kwh = self._estimate_worst_case_deficit_kwh(now, cheap_block_start)
        live_correctie = (
            getattr(self, "_laatste_live_correctie", None) if needed_kwh is not None else None
        ) or {}
        # v3.99.18: de lange horizon stuurt. De proefstandkandidaat van
        # v3.11.0 mat twee weken lang wat de reserve zou zijn tot het
        # EIND van de bekende prijzen in plaats van tot het eerstvolgende
        # goedkope blok: mediaan 1,48 kWh meer, en op die momenten was
        # extra laden in het blok goedkoper dan later van het net kopen.
        # De enige kandidaat die ja zei. Het verklaart de vier ochtenden
        # onder de bodem: een goedkoop blok om twaalf uur, een bewolkte
        # dag, en om vijf uur is er niets meer voor de nacht daarna.
        #
        # `_lange_reserve_extra_kwh` wordt elke ronde door de meting
        # zelf gezet, zodat de kandidaat het tegenfeitelijke blijft meten.
        lange_horizon_extra = 0.0
        if needed_kwh is not None and self.lange_horizon_actief:
            lange_horizon_extra = max(0.0, float(self._lange_reserve_extra_kwh or 0.0))
            needed_kwh += lange_horizon_extra
            # v5.42: `_lange_horizon_extra_vandaag` zet de omhulling.
        if needed_kwh is None:
            needed_kwh = self._estimate_consumption_kwh_for_period(
                now, cheap_block_start
            )
            if needed_kwh is None:
                learned_kw = self.learned_night_consumption_kw
                if learned_kw is not None:
                    power_kw = learned_kw
                else:
                    power_w = self._read_corrected_consumption_power()
                    power_kw = power_w / 1000 if power_w is not None else None
                if power_kw is None:
                    return None
                needed_kwh = power_kw * hours_until_cheap

            expected_pv_kwh = self._get_efficiency_discounted_pv_offset(
                now, cheap_block_start
            )
            needed_kwh = max(0.0, needed_kwh - expected_pv_kwh)

        # Scale up the margin if an extended low-solar stretch is ahead -
        # less confidence the battery gets refilled quickly, so keep more
        # in reserve. consecutive_low_solar_days=0 -> base margin only;
        # each additional day adds a bonus. No separate artificial cap -
        # this is naturally bounded by how many extended-day forecast
        # sensors are actually configured (real data availability).
        consecutive_low_solar_days = self._count_consecutive_upcoming_low_solar_days()
        low_solar_bonus_percent = (
            consecutive_low_solar_days * EXTENDED_LOW_SOLAR_MARGIN_BONUS_PER_DAY
        )

        # Also learn from recent reality: if unexpected grid import kept
        # happening during periods we believed were self-sufficient, the
        # reserve has been running too tight - add a bonus proportional to
        # how often that's happened in the last LEARNING_HISTORY_DAYS.
        # v5.67: de geplande ochtendverwarming, voor zover het profiel die
        # nog niet meeneemt - zie `_airco_ochtend_extra_kwh`.
        airco_ochtend = self._airco_ochtend_extra_kwh(now, cheap_block_start)
        needed_kwh += airco_ochtend["extra_kwh"]
        # v5.83: en het airco-gebruik buiten die ochtend (de avond als jullie
        # hem zelf aanzetten) - zie `airco_ritme.gebruik_kwh`. Eigen verbruik
        # gaat voor verkoop.
        airco_gebruik = self._airco_gebruik_extra_kwh(now, cheap_block_start)
        needed_kwh += airco_gebruik["extra_kwh"]
        # v5.68: het temperatuurmodel op koude nachten - zie `_temperatuur_extra_kwh`.
        temperatuur = self._temperatuur_extra_kwh(
            now, cheap_block_start, airco_ochtend["extra_kwh"] + airco_gebruik["extra_kwh"]
        )
        needed_kwh += temperatuur["extra_kwh"]
        # v5.70 (L-EMS-013): economische tekortnachten tellen niet mee.
        recent_shortfalls = self.marge_tekortnachten()
        shortfall_bonus_percent = (
            recent_shortfalls * SHORTFALL_MARGIN_BONUS_PER_RECENT_DAY
        )

        # And the counterbalance: if the reserve has been running way
        # more conservative than needed (excess energy left over while
        # still postponing charging), reduce the margin - otherwise it
        # could only ever ratchet upward and get stuck too cautious,
        # missing out on legitimate selling opportunities.
        recent_excess_days = sum(1 for v in self.reserve_excess_history if v)
        excess_reduction_percent = (
            recent_excess_days * EXCESS_MARGIN_REDUCTION_PER_RECENT_DAY
        )

        # Structural extra buffer: once an expensive-quarter discharge
        # ends, control passes to 'smart' mode, where the Zendure's own
        # logic decides how much more to discharge for household use -
        # completely outside our reserve protection. We can sell down to
        # the reserve floor safely *during* the expensive quarter itself,
        # but can't stop the battery being drawn further below that floor
        # afterwards. This extra margin compensates for that structural
        # blind spot (found after a real incident: ~6.5 kWh was correctly
        # sold to the reserve floor, then the unprotected night finished
        # the job and ran the battery to empty).
        # v2.4.0: een onzekere zondag telt mee in DEZELFDE marge.
        pv_onzeker_percent = self._pv_onzekerheidsmarge_procent()

        margin_bonus_percent = max(
            MIN_TOTAL_MARGIN_BONUS_PERCENT,
            pv_onzeker_percent
            + low_solar_bonus_percent
            + shortfall_bonus_percent
            - excess_reduction_percent
            + UNPROTECTED_AFTERMATH_MARGIN_PERCENT,
        )
        margin = DYNAMIC_DISCHARGE_RESERVE_MARGIN + margin_bonus_percent / 100
        # v4.1: de vloer die de verkooptoets apart aanhield (v1.88.0,
        # SELL_RESERVE_DEEPEST_SAFETY_FACTOR) geldt nu in de ene reserve:
        # de zelfcorrigerende marge mag na overschotdagen zakken, maar
        # niet onder de oude vaste factor.
        margin = max(margin, SELL_RESERVE_DEEPEST_SAFETY_FACTOR)
        reserve_kwh = needed_kwh * margin

        # v3.74.0: een ondergrens die NIET van de voorspelling afhangt.
        #
        # Gemeld: "De accu was weer leeg, dat moet opgelost worden."
        # Drie ochtenden op rij, en gemeten in de export van 30 augustus:
        #
        #     diepste tekort onderweg   0,001 kWh
        #     marge                    55 %
        #     reserve                   0,001 kWh
        #
        # Daar zit de weeffout. De marge wordt VERMENIGVULDIGD met het
        # diepste tekort, en dat tekort is nul zodra de voorspelling zegt
        # dat de zon het huis morgen dekt. Vijfenvijftig procent van nul
        # is nul.
        #
        # De reserve houdt dus structureel niets achter op precies de
        # dagen dat de voorspelling optimistisch is - en dan is er 's
        # nachts niets meer. Op 29 augustus ging 2,24 van de 5,92
        # ontladen kilowattuur naar het NET; had de accu die gehouden,
        # dan was hij 's ochtends op 40% gebleven in plaats van 13%.
        #
        # Deze bodem is geen voorspelling maar een vaste marge, en hij
        # staat op ÉÉN plek zodat hij doorwerkt in het ontladen, de
        # verkooptoets en de kwartierplanning tegelijk. Dat is het
        # verschil met de bodem die in v3.71.0 is gebouwd en weer
        # verwijderd: die zat alleen in de verkooptoets.
        capaciteit = self.bruikbare_capaciteit_kwh() or 0.0
        bodem_kwh = self._reserve_bodem_kwh()
        bodem_bindend = bodem_kwh > reserve_kwh
        reserve_kwh = max(reserve_kwh, bodem_kwh)

        # v3.99.2: en niet boven de accu.
        #
        # Op 2 september 13:37 stond de reserve op 16,8 kWh in een accu
        # van 8,64. Dat is geen reserve: de accu kan de periode dan per
        # definitie niet overbruggen, hoeveel er ook in zit. Alles wat
        # daarop volgde - "haalt de nacht niet", bijladen - vergeleek een
        # voorraad met een getal dat nooit gehaald kan worden.
        ongekapt_kwh = reserve_kwh
        # v5.81.1: het plafond is wat er tussen de grenzen past, niet de
        # totale accu - zie `_reserve_plafond_kwh`.
        capaciteit = self._reserve_plafond_kwh() or capaciteit
        boven_capaciteit = bool(capaciteit) and reserve_kwh > capaciteit
        if boven_capaciteit:
            reserve_kwh = capaciteit

        uitsplitsing = {
            # v5.6: het stempel van de ronde waarin dit is gerekend. Zonder
            # dit is niet te zien of twee getallen bij elkaar horen, en dat
            # was de hele oorzaak van de valse "tweede reserve"-melding.
            # v5.6: veilig uitlezen - dit veld wordt pas bij de eerste
            # ronde gezet.
            "ronde": self._ronde_stempel(),
            "base_percent": round((DYNAMIC_DISCHARGE_RESERVE_MARGIN - 1) * 100, 1),
            "low_solar_bonus_percent": round(low_solar_bonus_percent, 1),
            "consecutive_low_solar_days": consecutive_low_solar_days,
            "shortfall_bonus_percent": round(shortfall_bonus_percent, 1),
            "recent_shortfall_days": recent_shortfalls,
            "excess_reduction_percent": round(excess_reduction_percent, 1),
            "recent_excess_days": recent_excess_days,
            "pv_onzekerheid_percent": round(pv_onzeker_percent, 1),
            "unprotected_aftermath_percent": round(
                UNPROTECTED_AFTERMATH_MARGIN_PERCENT, 1
            ),
            "total_percent": round((margin - 1) * 100, 1),
            "needed_kwh_before_margin": round(needed_kwh, 3),
            # v5.20: de verschuiving op de P1-meter die in needed_kwh zit -
            # zodat in de export na te kijken is waar de reserve op rust.
            "regelverschuiving_w": round(self.regelverschuiving_kw() * 1000),
            "lange_horizon_extra_kwh": round(lange_horizon_extra, 3),
            "airco_ochtend_extra_kwh": airco_ochtend["extra_kwh"],
            "airco_gebruik_extra_kwh": airco_gebruik["extra_kwh"],
            "airco_gebruik_uren": airco_gebruik.get("uren", []),
            "temperatuur_extra_kwh": temperatuur["extra_kwh"],
            "temperatuur_model_kw": temperatuur["model_kw"],
            # v5.120.0 (H-EMS-14): de live verbruikscorrectie die in de
            # behoefte zit (begrensd op CONSUMPTION_CORRECTION_MAX_EXTRA_KWH)
            # en de verhouding live/profiel die hem gaf. Alleen meten.
            "live_correctie_extra_kwh": live_correctie.get("extra_kwh"),
            "live_correctie_verhouding": live_correctie.get("verhouding"),
            "reserve_kwh_after_margin": round(reserve_kwh, 3),
            # v3.74.0: en of die bodem het is die bindt.
            "bodem_kwh": round(bodem_kwh, 3),
            "bodem_bindend": bodem_bindend,
            "boven_capaciteit": boven_capaciteit,
            "ongekapt_kwh": round(ongekapt_kwh, 3),
            "bodem_procent": round(RESERVE_BODEM_FRACTIE * 100, 1),
        }
        # v4.1: alleen de sturing schrijft de uitsplitsing. De brug, de
        # verkooptoets en de planning lezen dezelfde reserve, maar een
        # planningskwartier van morgen mag de uitsplitsing van nu niet
        # overschrijven.
        # v5.42: de omhulling bewaart (en onthoudt per ronde).
        self._reserve_laatste_uitsplitsing = uitsplitsing

        if margin_bonus_percent != 0:
            _LOGGER.debug(
                "Discharge reserve margin: base %.0f%% + %.0f%% (low-solar, "
                "%d day(s)) + %.0f%% (%d shortfall day(s)) - %.0f%% "
                "(%d excess day(s)) = %.0f%%",
                (DYNAMIC_DISCHARGE_RESERVE_MARGIN - 1) * 100,
                low_solar_bonus_percent,
                consecutive_low_solar_days,
                shortfall_bonus_percent,
                recent_shortfalls,
                excess_reduction_percent,
                recent_excess_days,
                (margin - 1) * 100,
            )

        # v3.92.1: en teruggeven wat er berekend IS.
        #
        # Hier stond `return needed_kwh * margin` - de waarde van vóór de
        # bodem. De bodem werd uitgerekend, in de uitsplitsing gezet en
        # daarna weggegooid. Gemeten bij een diepste tekort van 0,001 kWh
        # en 7,78 kWh bruikbaar:
        #
        #     gemeld aan het dashboard    1,167 kWh   bodem bindend: true
        #     teruggegeven aan de sturing 0,00125 kWh
        #
        # De hele bodem van v3.74.0 heeft dus nooit gewerkt. Wat op het
        # dashboard stond klopte, alleen rekende er niets mee.
        return reserve_kwh

    def _planning_reserve_kwh(
        self, moment: datetime, cache: dict[str, float], entries=None
    ) -> float:
        """De reserve waar de kwartierplanning mee simuleert (v3.92.1).

        Stond als binnenfunctie in `get_quarter_plan`. Daar uit gehaald
        omdat die functie op de ratel van v3.35.0 staat: er iets aan
        toevoegen betekent er eerst iets uit halen.

        Per uur berekend en onthouden - de wandeling is niet gratis en
        binnen een uur verandert het dieptepunt nauwelijks.

        v3.92.1: de bodem geldt hier ook, en hij heeft het goedkope blok
        niet nodig.

        Hier stond `return 0.0` zodra dat blok onbekend was of al
        begonnen. Vanaf dat moment plande de simulatie verkoop tot de
        accu leeg was - en dat is het gat waar de nacht van 30 op 31
        augustus doorheen viel: 's avonds 3,65 kWh naar het net, 's
        ochtends 17% in plaats van de voorspelde 52%.

        De bodem is geen voorspelling maar een vaste marge, dus hij hoort
        te gelden op elk kwartier van de planning.
        """
        bodem = self._reserve_bodem_kwh()
        blok = self.last_cheap_block_start
        # v5.33: is het blok van nu voorbij op dit kwartier, dan het blok dat
        # de sturing OP DAT MOMENT zou kennen - niet de bodem. Gemeten over
        # 30 dagen: het plan van 08:00 verkocht 's avonds tot de bodem (laagste
        # stand 10-17%), want het blok van vanochtend lag dan achter het
        # kwartier. De sturing kent om 18:30 het blok van morgen en houdt de
        # reserve tot dan vast. Verkocht: mediaan 68% minder dan gepland,
        # 5 van de 30 dagen binnen de marge.
        # Binnen het lopende blok blijft het de bodem, net als de sturing
        # (`_lopend_blok`, v5.28.5).
        blok_eind = self.last_cheap_block_end
        in_blok = blok is not None and blok <= moment and (
            blok_eind is None or moment < blok_eind
        )
        if blok is not None and blok <= moment and not in_blok and entries:
            blok = self._volgend_blok_voor(entries, moment)
        if blok is None or blok <= moment:
            return bodem

        sleutel = f'{moment.strftime("%Y-%m-%d %H")}|{blok.isoformat()}'
        if sleutel not in cache:
            # v4.1: de ene reserve. Hier stond een eigen berekening -
            # diepste x max(margefactor, 1,25) - de vierde definitie van
            # hetzelfde getal. De toelichting van v1.88.0 die hier stond,
            # beschreef precies dit gevaar en loste het toen half op.
            reserve = self._get_dynamic_discharge_reserve_kwh(
                moment, blok, bewaar=False
            )
            cache[sleutel] = max(bodem, reserve or 0.0)
            # v5.70: voor de verkoopreserve in het plan.
            cache[sleutel + "|u"] = (
                (self._reserve_gevraagde_uitsplitsing, blok)
                if reserve is not None
                else (None, blok)
            )
        return cache[sleutel]

    def _planning_verkoopreserve_kwh(
        self, moment: datetime, cache: dict, entries, prijs: float
    ) -> float:
        """De verkoopreserve voor een plankwartier (v5.70).

        Dezelfde regel als de beslissing (`_verkoopreserve_uit`), zodat het
        plan voorspelt wat de verkooptoets straks doet.
        """
        reserve = self._planning_reserve_kwh(moment, cache, entries)
        sleutels = [k for k in cache if k.startswith(moment.strftime("%Y-%m-%d %H") + "|") and k.endswith("|u")]
        if not sleutels:
            return reserve
        u, blok = cache[sleutels[-1]]
        if u is None:
            return reserve
        blok_eind = (
            self.last_cheap_block_end if blok == self.last_cheap_block_start else None
        )
        info = self._verkoopreserve_uit(reserve, u, blok, blok_eind, prijs, entries)
        return info["reserve_kwh"] if info.get("reserve_kwh") is not None else reserve

    def _volgend_blok_voor(self, entries, moment: datetime) -> datetime | None:
        """Het goedkope blok dat de sturing op `moment` zou kiezen (v5.33).

        Dezelfde dalzoeker als de sturing, zonder de hysterese van nu. Ligt
        het gevonden dal tegen het eind van de bekende prijzen, dan is het
        echte volgende blok nog onbekend (de prijzen van morgen komen pas
        rond 13:00); dan geldt het blok van vandaag een etmaal later. Dat
        is wat de sturing 's avonds ook ziet: het middagdal van morgen.
        """
        if not entries:
            return None
        start, eind = self._cheapest_block_range(entries, moment, stabiel=False)
        laatste = max(e[1] for e in entries)
        if start is not None and eind is not None and eind < laatste:
            return start
        basis = self.last_cheap_block_start
        if basis is None:
            return start
        while basis <= moment:
            basis += timedelta(days=1)
        return basis

    @staticmethod
    def _zonvelden(
        hele_dag: float | None,
        opgewekt: float | None,
        nog_te_komen: float,
    ) -> dict:
        """De zon van vandaag, gesplitst (v3.94.2).

        Zonder splitsing is niet te zien of het getal een voorspelling
        was of een meting - en 's avonds is het bijna helemaal meting.
        """
        if hele_dag is None:
            return {}
        return {
            "zon_hele_dag_kwh": round(hele_dag, 1),
            "zon_opgewekt_kwh": (
                round(opgewekt, 1) if opgewekt is not None else None
            ),
            "zon_nog_te_komen_kwh": round(nog_te_komen, 1),
        }

    def _schaduw_na_de_verkooptoets(
        self, now: datetime, beschikbaar: float, veilig: float
    ) -> None:
        """Noteert de schaduwmeting als het terugvalpad is gebruikt
        (v4.22).

        Een eigen functie omdat `may_sell_now` op de groottescan staat
        en die had meteen gelijk toen ik dit erin zette.
        """
        nodig_veilig = self._safe_sell_nodig_veilig
        if nodig_veilig is None:
            return
        self._safe_sell_nodig_veilig = None
        self.noteer_safe_sell_shadow(
            now,
            verkocht_kwh=max(0.0, beschikbaar - veilig),
            nodig_verwacht=veilig,
            nodig_veilig=nodig_veilig,
        )

    def noteer_safe_sell_shadow(
        self,
        nu: datetime,
        verkocht_kwh: float,
        nodig_verwacht: float,
        nodig_veilig: float,
    ) -> None:
        """Wat zou de verkooptoets met de VEILIGE zon hebben besloten?
        (v4.22)

        Twee signalen wijzen dezelfde kant op. Gemeten over acht dagen:
        `expensive_quarter` week met een mediaan van -0,408 kWh af van
        het optimum - steeds richting "meer vasthouden". En in
        `may_sell_now` staat een terugvalpad dat met de VERWACHTE zon
        rekent terwijl de reserve met de VEILIGE positie in de
        Solcast-band rekent (p10 + 0,29 x de breedte, geleerd over 31
        dagen). Bij een bandbreedte van 59% is dat 30 tot 40% verschil.

        Dat pad geldt precies 's avonds en 's nachts, als er geen
        goedkoop blok in zicht is - dus wanneer verkopen aan de orde is
        en de nacht nog moet worden gehaald. Hetzelfde beslispad rekent
        daar voorzichtig voor de reserve en optimistisch voor de verkoop.

        Dit MEET en stuurt niets. Dat `expensive_quarter` te veel
        verkoopt, is niet bewezen; alleen dat de afwijking negatief is,
        relatief groot, en dat er een codepad bestaat dat optimistischer
        rekent dan de rest.
        """
        beschikbaar = self.last_available_kwh
        if beschikbaar is None:
            return
        ruimte_veilig = max(0.0, beschikbaar - nodig_veilig)
        if nodig_veilig <= nodig_verwacht + 0.05:
            uitkomst, verschil = "zelfde beslissing", 0.0
        elif ruimte_veilig <= 0.05:
            uitkomst, verschil = "geen verkoop", verkocht_kwh
        elif ruimte_veilig < verkocht_kwh:
            uitkomst, verschil = "minder verkoop", verkocht_kwh - ruimte_veilig
        else:
            uitkomst, verschil = "zelfde beslissing", 0.0
        self.safe_sell_shadow.append(
            {
                "moment": nu.isoformat(),
                "reden": self.last_reason,
                "verkocht_kwh": round(verkocht_kwh, 3),
                "nodig_verwacht_kwh": round(nodig_verwacht, 3),
                "nodig_veilig_kwh": round(nodig_veilig, 3),
                "beschikbaar_kwh": round(beschikbaar, 3),
                "uitkomst": uitkomst,
                "verschil_kwh": round(verschil, 3),
                "prijs_ct": (
                    round(p * 100, 1)
                    if (p := self.huidige_prijs_eur_per_kwh(nu)) is not None
                    else None
                ),
            }
        )
        self.safe_sell_shadow = self.safe_sell_shadow[-SAFE_SELL_SHADOW_LENGTE:]
        self.noteer_meting_gevuld("safe_sell_shadow")
        self.schedule_persisted_state_save()

    def _safe_sell_oordeel(
        self,
        momenten: list,
        anders: int,
        verschil_kwh: float,
        verschil_eur: float,
        banden: dict,
        netimport_n: int,
        onbekend: int,
    ) -> str:
        """De richting, maar alleen met genoeg uitkomsten (v4.24).

        De veilige positie is bewust pessimistisch, dus "minder verkoop"
        is te verwachten. Wat het zegt, hangt af van de nachten erna:
        comfortabele nachten betekenen dat die energie niet nodig was en
        de veilige positie winst had gekost; krappe nachten betekenen dat
        de verkooptoets te optimistisch is.
        """
        kop = (
            f"{anders} van {len(momenten)} verkoopmomenten zouden anders zijn "
            f"gegaan met de veilige zon: {verschil_kwh:.2f} kWh minder verkocht, "
            f"grofweg {verschil_eur:.2f} euro. "
        )
        met_uitkomst = sum(banden.values())
        if met_uitkomst < SAFE_SELL_MIN_MOMENTEN:
            return (
                kop
                + f"Van {met_uitkomst} daarvan is de nacht erna bekend"
                + (f" ({onbekend} nog niet)" if onbekend else "")
                + f"; minstens {SAFE_SELL_MIN_MOMENTEN} nodig voordat hier een "
                "richting uit te lezen is."
                if met_uitkomst
                else kop
                + "Nog geen uitkomst bekend: de nacht erna moet eerst voorbij zijn."
            )
        deel = (
            f"Van de {met_uitkomst} waarvan de nacht bekend is: "
            f"{banden['comfortabel']} comfortabel, {banden['normaal']} normaal, "
            f"{banden['krap']} krap, {netimport_n} met netimport. "
        )
        if banden["comfortabel"] >= 2 * (banden["krap"] + banden["normaal"]):
            return (
                kop + deel + "Die energie was 's nachts dus meestal niet nodig - "
                "de veilige positie zou hier vooral winst hebben gekost."
            )
        if banden["krap"] + netimport_n >= met_uitkomst / 2:
            return (
                kop + deel + "Die energie had 's nachts dus waarde - dit is een "
                "aanwijzing dat de verkooptoets te optimistisch rekent."
            )
        return (
            kop + deel + "Geen duidelijke richting: de nachten lopen door elkaar."
        )

    def _nacht_na_de_schaduw(self, moment: str) -> dict | None:
        """De nacht die volgde op een schaduwmoment (v4.23).

        De schaduw zegt hoeveel er zou VERANDEREN, niet of het BETER zou
        zijn. De veilige positie van 0,29 is geijkt als de waarde die in
        20% van de dagen werd gehaald - bewust pessimistisch - dus in de
        verkooptoets zal die vrijwel altijd "minder verkoop" zeggen. Dat
        is dan een eigenschap van de ijking en geen bevinding.

        Of minder verkopen beter was, hangt af van hoe de nacht erna
        liep. Dat staat al in de dagrecords sinds v4.7: de laagste
        laadstand in de ochtend en de netimport 's nachts. Gemeten:
        18% met 0,01 kWh en 37% met 0,11 kWh waren ruim, 10% met 1,05
        kWh was krap.
        """
        begin = dt_util.parse_datetime(moment)
        if begin is None:
            return None
        dag_erna = (begin + timedelta(days=1)).date().isoformat()
        for r in reversed(self.reserve_daily_records or []):
            if r.get("date") != dag_erna:
                continue
            stand = r.get("laagste_soc_ochtend")
            netimport = r.get("netimport_nacht_kwh")
            if stand is None and netimport is None:
                return None
            # v4.24: drie banden in plaats van één grens - zie
            # NACHT_COMFORTABEL_SOC_PROCENT. De vraag is niet of de nacht
            # krap was maar of de energie waarde had.
            if stand is None:
                band = "onbekend"
            elif stand > NACHT_COMFORTABEL_SOC_PROCENT:
                band = "comfortabel"
            elif stand >= NACHT_KRAP_SOC_PROCENT:
                band = "normaal"
            else:
                band = "krap"
            krap = band == "krap" or bool(
                netimport is not None and netimport >= NACHT_KRAP_NETIMPORT_KWH
            )
            return {
                "datum": dag_erna,
                "laagste_soc_ochtend": stand,
                "netimport_nacht_kwh": netimport,
                "band": band,
                "krap": krap,
                "netimport": bool(
                    netimport is not None
                    and netimport >= NACHT_KRAP_NETIMPORT_KWH
                ),
                "tekort": bool(r.get("shortfall")),
            }
        return None

    def get_safe_sell_shadow_overzicht(self) -> dict:
        """Wat de schaduwmeting tot nu toe zegt (v4.22). Stuurt niets."""
        momenten = self.safe_sell_shadow or []
        if not momenten:
            return {
                "momenten": 0,
                "oordeel": (
                    "Nog geen verkoopmoment gemeten. Er komt een regel bij zodra "
                    "de accu aan het net levert."
                ),
            }
        tellers = {"zelfde beslissing": 0, "minder verkoop": 0, "geen verkoop": 0}
        # v4.23: de nacht erna erbij - anders meet de schaduw een
        # verandering en niet een verbetering.
        banden = {"comfortabel": 0, "normaal": 0, "krap": 0}
        netimport_n = tekort_n = onbekend = 0
        verrijkt = []
        for m in momenten:
            tellers[m["uitkomst"]] = tellers.get(m["uitkomst"], 0) + 1
            nacht = self._nacht_na_de_schaduw(m["moment"])
            verrijkt.append({**m, "nacht_erna": nacht})
            if m["uitkomst"] == "zelfde beslissing":
                continue
            if nacht is None:
                onbekend += 1
                continue
            banden[nacht["band"]] = banden.get(nacht["band"], 0) + 1
            if nacht["netimport"]:
                netimport_n += 1
            if nacht["tekort"]:
                tekort_n += 1
        momenten = verrijkt
        krap = banden["krap"]
        verschil_kwh = sum(m["verschil_kwh"] for m in momenten)
        verschil_eur = sum(
            m["verschil_kwh"] * (m["prijs_ct"] or 0) / 100 for m in momenten
        )
        anders = tellers["minder verkoop"] + tellers["geen verkoop"]
        return {
            "momenten": len(momenten),
            "zelfde_beslissing": tellers["zelfde beslissing"],
            "minder_verkoop": tellers["minder verkoop"],
            "geen_verkoop": tellers["geen verkoop"],
            "verschil_kwh_totaal": round(verschil_kwh, 2),
            "daarvan_krappe_nacht": krap,
            "nacht_comfortabel": banden["comfortabel"],
            "nacht_normaal": banden["normaal"],
            "nacht_krap": banden["krap"],
            "nacht_met_netimport": netimport_n,
            "nacht_met_tekort": tekort_n,
            "nacht_nog_onbekend": onbekend,
            "verschil_eur_totaal": round(verschil_eur, 2),
            "laatste": momenten[-1],
            "oordeel": (
                self._safe_sell_oordeel(
                    momenten, anders, verschil_kwh, verschil_eur, banden,
                    netimport_n, onbekend,
                )
                if anders
                else f"{len(momenten)} verkoopmomenten, allemaal dezelfde beslissing. "
                "De band maakt hier geen verschil."
            ),
            "toelichting": (
                "Wat de verkooptoets zou hebben besloten met de veilige positie in "
                "de Solcast-band in plaats van de verwachting. Dit meet en stuurt "
                "niets. Blijft dit dezelfde kant op wijzen als de kWh-afwijking per "
                "reden, dan is dat de eerste ingreep die op twee onafhankelijke "
                "metingen rust.\n\n"
                "De veilige positie is bewust pessimistisch (geijkt op 20% van de "
                "dagen), dus \"minder verkoop\" is te verwachten en zegt alleen dat "
                "er iets zou VERANDEREN. Of het BETER was, staat in de nacht erna: "
                "liep die krap, dan was minder verkopen goed; liep die ruim, dan "
                "zou de veilige positie geld hebben gekost."
            ),
        }

    def _verkoopruimte_met_piek(
        self,
        now: datetime,
        entries,
        blok: datetime | None,
        beschikbaar: float | None,
    ) -> dict:
        """Mag er verkocht worden? (v5.28.4: het huis gaat voor.)

        Gemeld op 4 oktober: "Weer een lege batterij vanmorgen, huis dient
        altijd voor te gaan." Sinds v5.26.3 passeerde de piekregel de
        huisgrens: als de prijs nu hoger was dan elk kwartier tot het
        bijvullen, mocht er verkocht worden tot de bodem. Op 3 oktober verkocht
        hij zo 19:45-22:00 onder de reserve (5,5-6,7 kWh) tot 25%; het huis
        haalde daarna 2,9 kWh van het net tegen 35 ct - netto zo'n 15 cent
        winst, voor een lege accu.

        Nu geldt de huisgrens altijd: alleen `may_sell_now` beslist. De naam
        blijft voor de aanroepers.
        """
        return self.may_sell_now(now, beschikbaar)

    def may_sell_now(
        self, now: datetime, beschikbaar: float | None = None
    ) -> dict:
        """Mag de accu nu verkopen, of is dat nodig voor de woning?
        (v1.23.0)

        Gevraagd: "Hij moet actief kijken of verkoop van energie
        mogelijk is (dus is er nog genoeg voor mijn woning)." En over de
        winter: "dan alleen laden en indien nodig bijladen, en de eigen
        woning voeden, punt."

        De bestaande reserve toetste PASSIEF: blijft er genoeg over?
        Maar verkopen gaat op 1600 W terwijl het huis 300 W trekt - ruim
        vijf keer zo snel. Binnen een uur stond de accu op de bodem, en
        daar bleef hij: het huis hing daarna drie uur aan het net tegen
        25 tot 33 ct.

        Deze toets is actief en kent twee remmen:

        1. Is er die dag te weinig zon te verwachten, dan wordt er niet
           verkocht. Wat er is, is voor de woning; wat ontbreekt wordt in
           het goedkope blok bijgeladen.
        2. Anders moet er ná de verkoop nog genoeg overblijven om de
           woning te voeden tot het volgende goedkope blok, met marge.
        """
        # v1.23.0: de accustand kan als argument worden meegegeven,
        # omdat de aanroeper hem in de beslistick al berekend heeft
        # voordat `last_available_kwh` is bijgewerkt.
        if beschikbaar is None:
            beschikbaar = self.beschikbare_energie_kwh()
        if beschikbaar is None and self.config.get(CONF_AVAILABLE_ENERGY_SENSOR):
            # v5.26.6: ONBEKEND = NIET VERKOPEN - als de sensor WEL is
            # ingesteld maar (nog) geen waarde geeft. In de eerste ronde na
            # een herstart ging er zo een verkoopcommando van 1600 W uit,
            # terwijl de regels bewaren zeiden (30 september 20:34). Zonder
            # ingestelde sensor blijft het oude gedrag hieronder.
            return {
                "mag_verkopen": False,
                "reden": (
                    "De accustand is (nog) niet gemeten; niet verkopen tot die "
                    "er is. De accu dekt de woning intussen in de stand slim."
                ),
            }
        if beschikbaar is None:
            # Zonder accumeting valt niet te toetsen of er genoeg voor de
            # woning overblijft. Dan NIET blokkeren: het beproefde gedrag
            # met de bestaande reserve blijft dan gelden, en die is er
            # ook zonder deze toets. Blokkeren zou een installatie zonder
            # accusensor stilzetten.
            # v1.24.1: "Ja. Accustand onbekend" las tegenstrijdig op het
            # dashboard - het klonk als een fout terwijl het een bewuste
            # terugval is. Nu zegt de tekst wat er gebeurt.
            return {
                "mag_verkopen": True,
                "reden": (
                    "Nog geen accustand gemeten; de bestaande reserve "
                    "bewaakt de woning zoals hij dat altijd al deed."
                ),
            }

        # Rem 1: zonarme dag.
        # Alleen remmen als er ECHT een voorspelling is. Zonder
        # Solcast-sensor geeft deze functie 0,0 terug, en dat zou elke
        # dag als zonarm bestempelen - dan zou er nooit meer verkocht
        # worden voor wie die sensor niet heeft.
        verwacht_vandaag, al_opgewekt, nog_te_komen = self._zon_vandaag_totaal(now)
        if verwacht_vandaag is not None and verwacht_vandaag < SOLAR_POOR_DAY_KWH:
            return {
                "mag_verkopen": False,
                **self._zonvelden(verwacht_vandaag, al_opgewekt, nog_te_komen),
                "reden": (
                    f"Zonarme dag ({verwacht_vandaag:.1f} kWh over de hele dag, "
                    f"onder "
                    f"{SOLAR_POOR_DAY_KWH:.0f}). Wat er is, is voor de woning; "
                    "wat ontbreekt komt van het net, of wordt in het goedkope "
                    "blok bijgeladen als dat loont."
                ),
            }

        # Rem 4 (v3.43.0): de planning zegt zelf dat de accu tekortkomt.
        #
        # Gemeld: "Als ik een melding krijg dat de accu de nacht niet
        # haalt, moet hij toch eigenlijk ook het manual terugleveren
        # stoppen?"
        #
        # Ja. Gemeten op 20 augustus 20:06 en 20:43: de planning meldde
        # kritiek "vier kwartieren waarin de accu niets meer kan leveren,
        # morgen 06:30-07:30", en tegelijk stond er acht kwartieren
        # verkopen gepland tussen 20:45 en 23:00 - van 69% naar 35%.
        #
        # Beide kloppen op zichzelf. `may_sell_now` kijkt tot het
        # volgende goedkope blok; de tekortmelding kijkt de hele
        # planning door. Maar het is één accu, en dan is dit één hand die
        # geeft en één die het weer wegneemt.
        #
        # Dezelfde drempel als de melding: onder de drie kwartieren is
        # het een planning die precies uitkomt, en die reden staat
        # uitgeschreven bij `PLAN_SHORTFALL_ALERT_MIN_QUARTERS`.
        # De LAATST berekende stand, niet hier opnieuw uitrekenen.
        #
        # De eerste versie riep `get_quarter_plan_summary` aan vanuit
        # deze toets. Dat bouwt honderdtien kwartieren opnieuw op bij
        # elke ronde, en een fout daarin breekt dan de aansturing - de
        # volledige tick-toets viel er meteen over om.
        #
        # De planning wordt elke ronde toch al doorgerekend voor de
        # tekortmelding. Eén ronde vertraging is hier onschadelijk: een
        # tekort dat over acht uur valt, verschuift niet binnen een
        # minuut.
        tekorten = self.last_plan_shortfall.get("kwartieren") or 0
        if tekorten >= PLAN_SHORTFALL_ALERT_MIN_QUARTERS:
            perioden = self.last_plan_shortfall.get("perioden") or []
            wanneer = (
                ", ".join(str(p) for p in perioden[:2])
                if perioden
                else "onbekend wanneer"
            )
            return {
                "mag_verkopen": False,
                "methode": "planning voorziet een tekort",
                "tekort_kwartieren": tekorten,
                "reden": (
                    f"Niet verkopen: de planning voorziet {tekorten} "
                    f"kwartier(en) waarin de accu niets meer kan leveren "
                    f"({wanneer}). Wat er nu weggaat, moet dan van het net "
                    "komen."
                ),
            }

        # Rem 3 (v3.42.0): loont verkopen na de saldering nog wel?
        #
        # Zolang salderen geldt wordt een teruggeleverde kWh weggestreept
        # tegen inkoop, dus verkopen levert exact de inkoopprijs op en is
        # het om het even. Vanaf 1 januari 2027 niet meer: dan krijg je
        # het kale tarief terwijl inkoop belast blijft.
        #
        # De machinerie daarvoor lag er al sinds v1.1.0 -
        # `_export_value_eur_per_kwh` rekent beide werelden uit - maar de
        # verkoopcheck gebruikte hem niet. Die vroeg alleen "houdt de
        # woning het?", en ging er stilzwijgend van uit dat verkopen
        # verder gratis geld is. Dat is de aanname die op 1 januari
        # omklapt.
        #
        # Wat een vastgehouden kWh straks waard is: de duurste prijs die
        # nog komt, min wat het kost om hem door de accu te halen -
        # rendementsverlies en slijtage. Is dat meer dan wat verkopen nu
        # opbrengt, dan is verkopen verlies.
        rem = self._verkoop_loont_na_saldering(now)
        if rem is not None:
            return rem

        # Rem 2: houdt de woning het tot het goedkope blok?
        blok_start = self.last_cheap_block_start
        methode = "diepste tekort onderweg"
        # v4.1: de ene reserve. Hier stond een eigen berekening - diepste
        # tekort maal de margefactor, met een terugval op de nettosom -
        # en die gaf op 7 september 16:37 een ander getal dan de brug
        # een minuut later (17,96 tegen 13,44). De verkooptoets leest nu
        # dezelfde reserve als de sturing en de planning; wat hij eraan
        # toevoegt is de dode zone en de zonvelden.
        verkoopinfo: dict = {}
        if blok_start is None or blok_start <= now:
            nodig = 0.0
            veilig = 0.0
        else:
            # v5.70: de verkoopreserve - het deel na het blok dat het blok
            # zelf goedkoper teruglaadt, hoeft niet vast te blijven.
            verkoopinfo = self.verkoopreserve(now, blok_start)
            reserve = verkoopinfo.get("reserve_kwh")
            if reserve is None:
                nodig = (
                    self._estimate_consumption_kwh_for_period(now, blok_start) or 0.0
                )
                zon = self._estimate_pv_kwh_for_period(now, blok_start) or 0.0
                # v4.22: schaduwmeting - wat zou hier zijn uitgekomen met
                # de VEILIGE positie in de band? Dit pad rekent met de
                # verwachting terwijl de reserve met de veilige positie
                # rekent; die inconsistentie wordt nu gemeten, niet
                # gerepareerd. Zie `noteer_safe_sell_shadow`.
                zon_veilig = (
                    self._estimate_pv_kwh_for_period(now, blok_start, veilig=True)
                    or 0.0
                )
                self._safe_sell_nodig_veilig = max(0.0, nodig - zon_veilig)
                nodig = max(0.0, nodig - zon)
                veilig = nodig * SELL_RESERVE_SAFETY_FACTOR
                methode = "nettosom (geen volledig uurprofiel)"
            else:
                nodig = (self.last_reserve_margin_breakdown or {}).get(
                    "needed_kwh_before_margin", reserve
                )
                veilig = reserve
        veilig = max(veilig, self._reserve_bodem_kwh())
        # v3.99.15: en niet boven de accu. 7 september 16:37: "17,96 kWh
        # nodig" in een accu van 8,64. v3.99.2 kapte de reserve, maar deze
        # toets rekent `veilig` zelf uit - de vierde berekening uit
        # v3.92.3, en de enige die de kap miste.
        # v5.81.1: het plafond tussen de grenzen (`_reserve_plafond_kwh`).
        # Bindt het plafond, dan heeft de woning méér nodig dan er in de
        # accu past: dan is er niets vrij te verkopen, hoe vol hij ook is.
        capaciteit = self._reserve_plafond_kwh()
        ongekapt = verkoopinfo.get("ongekapt_kwh")
        plafond_bindt = bool(capaciteit) and (
            veilig > capaciteit + 0.001
            or (ongekapt is not None and float(ongekapt) > capaciteit + 0.001)
        )
        if capaciteit:
            veilig = min(veilig, capaciteit)

        # v3.99.4: dode zone. Eenmaal dicht door de reserve, pas weer open
        # als er SELL_HYSTERESIS_KWH bovenop staat. Anders: verkopen kost
        # 0,03 kWh per minuut, de reserve zakt met de klok, en de twee
        # kruisen elkaar elke paar minuten - 68 wissels op een dag.
        drempel = veilig
        if self._verkoop_geblokkeerd_door_reserve:
            drempel = veilig + SELL_HYSTERESIS_KWH
        # v3.99.7: en minstens een kwartier dicht. De reserve springt
        # zelf tussen rondes; een dode zone op de voorraad helpt niet
        # tegen een drempel die beweegt.
        te_snel = (
            self._verkoop_geblokkeerd_door_reserve
            and self._verkoop_dicht_sinds is not None
            and (now - self._verkoop_dicht_sinds).total_seconds() / 60
            < SELL_REOPEN_MIN_MINUTES
        )
        self._schaduw_na_de_verkooptoets(now, beschikbaar, veilig)
        if beschikbaar <= drempel or te_snel or plafond_bindt:
            if not self._verkoop_geblokkeerd_door_reserve:
                self._verkoop_dicht_sinds = now
            self._verkoop_geblokkeerd_door_reserve = True
            return {
                "mag_verkopen": False,
                "nodig_voor_woning_kwh": round(veilig, 2),
                "beschikbaar_kwh": round(beschikbaar, 2),
                "methode": methode,
                **self._tot_en_na_blok_velden(),
                **self._verkoopreserve_velden(verkoopinfo),
                "reden": (
                    f"De woning heeft {veilig:.2f} kWh nodig tot het goedkope "
                    f"blok en er is {beschikbaar:.2f} kWh - verkopen zou het "
                    "huis aan het net leggen."
                    # v5.56: tot en na het blok apart (alleen tekst).
                    + (
                        self._tot_en_na_blok_zin()
                        if methode == "diepste tekort onderweg"
                        else ""
                    )
                    + (
                        f" Pas weer verkopen met {SELL_HYSTERESIS_KWH:.2f} kWh "
                        "ruimte erbovenop (dode zone tegen het schakelen)."
                        if beschikbaar > veilig
                        else ""
                    )
                ),
            }

        self._verkoop_geblokkeerd_door_reserve = False
        return {
            "mag_verkopen": True,
            "nodig_voor_woning_kwh": round(veilig, 2),
            "beschikbaar_kwh": round(beschikbaar, 2),
            "vrij_te_verkopen_kwh": round(beschikbaar - veilig, 2),
            "methode": methode,
            **self._tot_en_na_blok_velden(),
            **self._zonvelden(verwacht_vandaag, al_opgewekt, nog_te_komen),
            **self._verkoopreserve_velden(verkoopinfo),
            "reden": (
                f"{beschikbaar - veilig:.2f} kWh vrij te verkopen: de woning "
                f"houdt {veilig:.2f} kWh over tot het goedkope blok."
                + self._verkoopreserve_zin(verkoopinfo)
            ),
        }

    # v5.79: de laatste begrenzing van het ontlaadvermogen, voor de export.
    last_ontlaadgrens: dict | None = None

    def _begrens_tot_verkoopruimte(
        self, now: datetime, vermogen_w: float | None
    ) -> float | None:
        """Ontladen = het huis dekken; terugleveren alleen uit de vrije ruimte
        (v5.79, akkoord Ruud 10-10).

        Gezien op 10-10 18:45-19:00: stand expensive_quarter, de Zendure
        ontlaadde ~2,4 kW, de P1-meter stond op -1,8 tot -1,9 kW (~0,47 kWh
        teruggeleverd), en de beschikbare energie zakte van 6,91 naar 6,22
        kWh tegen een reserve tot het blok van 6,78 kWh (5,42 x marge). De
        oorzaak zat in het VERMOGEN, niet in de poort: de poort
        (`may_sell_now`) keek per ronde of er nog iets boven de reserve zat,
        maar het vermogen werd niet op die ruimte afgestemd. De ruimte werd
        omgerekend over vijf minuten (`UPDATE_INTERVAL_MINUTES`) en minstens
        het huis plus wat er vrij was - en zolang salderen geldt, begrensde
        niets daarna het vermogen (`cap_discharge_to_own_consumption` gaf het
        ongewijzigd terug). Met 2,4 kW vast vermogen schiet één ronde dan ver
        door de reserve heen.

        Nu: het vermogen is hooguit het huisverbruik plus wat er vrij te
        verkopen is, verdeeld over de rest van het kwartier (minstens één
        ronde, zodat één ronde nooit meer kan verkopen dan er vrij is). Vrij
        is het kleinste van (a) wat de verkooptoets vrij gaf, en (b) de
        beschikbare energie min de reserve TOT HET BLOK (nodig tot het blok x
        marge, minstens de bodem). Zei de verkooptoets nee, dan nul: alleen
        het huis. Zonder verkooptoets in deze ronde (los aangeroepen) blijft
        het vermogen zoals het was.
        """
        toets = self.last_sell_check
        if vermogen_w is None or not isinstance(toets, dict) or "mag_verkopen" not in toets:
            return vermogen_w
        beschikbaar = toets.get("beschikbaar_kwh")
        if beschikbaar is None:
            beschikbaar = self.beschikbare_energie_kwh()
        if beschikbaar is None and toets.get("mag_verkopen"):
            # Zonder accumeting bewaakt de bestaande reserve het (zie
            # `may_sell_now`): dan niets extra begrenzen.
            return vermogen_w
        vrij = 0.0
        if toets.get("mag_verkopen") and beschikbaar is not None:
            vrij = float(toets.get("vrij_te_verkopen_kwh") or 0.0)
            u = self.last_reserve_margin_breakdown or {}
            tot, _na = self._nodig_tot_en_na_blok_kwh()
            marge = 1 + float(u.get("total_percent") or 0.0) / 100
            grens = max(self._reserve_bodem_kwh(), (tot or 0.0) * marge)
            vrij = max(0.0, min(vrij, float(beschikbaar) - grens))
        huis_w = self._read_corrected_consumption_power()
        volgend = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0) + timedelta(minutes=15)
        rest_h = max(
            (volgend - now).total_seconds() / 3600,
            float(self.update_interval_seconds) / 3600,
        )
        export_w = vrij / rest_h * 1000 if rest_h > 0 else 0.0
        maximum_w = max(0.0, huis_w or 0.0) + export_w
        self.last_ontlaadgrens = {
            "moment": now.isoformat(),
            "gevraagd_w": round(vermogen_w, 1),
            "huis_w": round(huis_w, 1) if huis_w is not None else None,
            "vrij_te_verkopen_kwh": round(vrij, 3),
            "export_max_w": round(export_w, 1),
            "maximum_w": round(maximum_w, 1),
            "mag_verkopen": bool(toets.get("mag_verkopen")),
        }
        if maximum_w < POST_SALDEREN_MIN_USEFUL_DISCHARGE_W:
            # Niets te dekken en niets te verkopen: de accu in zijn eigen
            # slimme stand, die het huis volgt.
            return None
        return round(min(vermogen_w, maximum_w), 1)

    _negatieve_prijs_sinds: datetime | None = None

    _netladen_blok_start: datetime | None = None

    def _moet_uit_het_net_laden(
        self,
        now: datetime,
        cheap_block_start: datetime | None,
        cheap_block_end: datetime | None,
    ) -> bool:
        """Laden uit het net binnen het goedkope blok, met een poort
        (v4.10).

        Hier stond `in_cheap_block and is_low_solar`, en `is_low_solar`
        hangt aan de zonvoorspelling én aan een geleerde drempel die met
        de spreiding meebeweegt. Binnen een blok van acht uur kan die
        kantelen: dan stopt het laden op 2000 W halverwege en begint het
        later weer. Een besluit dat een half uur geldt, is geen besluit.

        Eenmaal begonnen blijft het laden tot het blok voorbij is. Een
        NIEUW blok beslist opnieuw - de zonverwachting is dan ook nieuw.
        """
        in_blok = (
            cheap_block_start is not None
            and cheap_block_end is not None
            and cheap_block_start <= now < cheap_block_end
        )
        if not in_blok:
            self._netladen_blok_start = None
            return False
        if self._netladen_blok_start == cheap_block_start:
            return True
        if self._is_low_solar_expected():
            self._netladen_blok_start = cheap_block_start
            return True
        return False

    def _is_negatieve_prijs(self, prijs_eur: float | None, now: datetime) -> bool:
        """Is de prijs negatief genoeg om 2 kW voor aan te zetten? (v4.10)

        Hier stond `prijs < 0`: een kale grens. Bij een prijs die rond
        nul hangt - het begin en het eind van een negatieve periode -
        klapte de accu tussen laden op vol vermogen en de gewone
        sturing, zonder marge en zonder minimumtijd. Bij elke omslag
        wordt bovendien de zonhelling opnieuw gestart.

        Dezelfde vorm als de verkooptoets (v3.99.4): een dode zone rond
        de grens, en minstens een kwartier aan voordat hij weer uit mag.
        """
        if prijs_eur is None:
            self._negatieve_prijs_sinds = None
            return False
        if self._negatieve_prijs_sinds is not None:
            minuten = (now - self._negatieve_prijs_sinds).total_seconds() / 60
            if minuten < NEGATIEVE_PRIJS_MIN_MINUTEN:
                return True
            if prijs_eur < NEGATIEVE_PRIJS_UIT_EUR:
                return True
            self._negatieve_prijs_sinds = None
            return False
        if prijs_eur < NEGATIEVE_PRIJS_AAN_EUR:
            self._negatieve_prijs_sinds = now
            return True
        return False

    def _is_emergency_low_battery(self) -> bool:
        """Is the battery critically low right now, AND is little solar
        expected to refill it soon? Deliberately scoped to the winter
        scenario: in summer, a critically low battery refills quickly from
        solar the next morning anyway (better handled by discharging less
        in the first place - see the live-consumption correction in
        `_estimate_consumption_kwh_for_period`), so an emergency grid
        top-up isn't needed or desirable there. In winter, with little
        solar in the outlook, a critically low battery risks running the
        household on grid power for an extended stretch, so a safety-net
        top-up makes sense.

        Prefers the SoC sensor (compared against the same configured
        minimum used elsewhere); falls back to a small absolute kWh
        buffer on the available-energy sensor if no SoC sensor is set.
        """
        if not self._is_low_solar_expected():
            return False
        # v5.25.1: ECONOMISCH getoetst. Gemeld: "hij begint nu direct op een
        # veel te duur moment te laden" - en dat was deze noodlading (v0.28.1):
        # accu op 8%, dus laden tot 15%, ongeacht de prijs.
        #
        # Bij een lege accu komt de stroom hoe dan ook van het net. Eerst in
        # de accu laden en hem er later weer uithalen vermijdt geen
        # netstroom; het voegt alleen rendementsverlies en slijtage toe.
        # Het helpt alleen als die kWh straks meer oplevert dan hij nu kost
        # en er geen goedkoper moment meer komt - en dat is precies de
        # dipregel. Noodzakelijk is het niet: de Zendure beschermt zijn
        # cellen zelf op zijn ondergrens. Het oorspronkelijke probleem - leeg
        # om 04:00 met een dure ochtend - lost het spaarplan (v5.25) op.
        #
        # Gevraagd: "het beste doen wat noodzakelijk en economisch het beste
        # is."
        if not self._dipbesluit(dt_util.now(), self.last_cheap_block_start).get("laden"):
            self._noodlading_actief = False
            return False

        # v3.99.4: dode zone. Aan als de accu leeg is, pas uit als hij
        # EMERGENCY_LOW_BATTERY_EXIT_MARGIN_PERCENT boven die grens staat.
        # Anders: laden tot een procent erboven, stoppen, het huis trekt hem
        # eronder, weer laden - op het moment in de winter dat het er het
        # meest toe doet.
        # v5.177.0 (A7): leeg volgens de ene definitie (`accu_leeg`: de
        # gecorrigeerde inhoud boven de effectieve ondergrens), niet meer de
        # laadstand tegen de min-SoC of 0,3 kWh op de ruwe sensor.
        # De noodregel begint op de ondergrens zelf (geen marge van 3 %):
        # zelfde maat, zelfde gedrag als voorheen.
        op_de_grens = -TEKORT_LEEG_MARGE_PROCENT
        if self._noodlading_actief:
            self._noodlading_actief = self.accu_leeg(
                extra_procent=op_de_grens + EMERGENCY_LOW_BATTERY_EXIT_MARGIN_PERCENT
            )
        else:
            self._noodlading_actief = self.accu_leeg(extra_procent=op_de_grens)
        return self._noodlading_actief

    def _get_spare_headroom_after_primary_tier_kwh(
        self,
        entries: list[PriceEntry],
        now: datetime,
        headroom_kwh: float,
        discharge_power_w: float,
    ) -> float:
        """How much of the current headroom is left over after reserving
        enough for today's remaining genuinely-expensive (primary-tier)
        quarters still ahead of 'now'. Used to size the secondary,
        more-lenient tier - so it can never eat into what the real price
        peak still needs.
        """
        primary_threshold = self._get_expensive_price_threshold(entries, now)
        if primary_threshold is None:
            return 0.0

        todays_entries = [e for e in entries if e[0].date() == now.date()]
        remaining_primary = [
            e for e in todays_entries if e[2] >= primary_threshold and e[1] > now
        ]
        energy_per_quarter_kwh = (discharge_power_w / 1000) * 0.25
        primary_needed_kwh = len(remaining_primary) * energy_per_quarter_kwh
        return max(0.0, headroom_kwh - primary_needed_kwh)

    def _secundaire_laag_toegestaan(self) -> bool:
        """Mag de secundaire prijslaag verkopen? Alleen als de verkooptoets
        niet door de reserve dicht staat (v3.99.9).

        v5.43: en alleen als de verkooptoets van deze ronde niet NEE zei. De
        reservevlag hierboven wordt alleen gezet als de reserve-toets zelf
        sluit. Zei `may_sell_now` nee om een andere reden - een zonarme dag,
        een tekort dat de planning voorziet, verkopen dat na de saldering
        niet loont, een onbekende accustand - dan rekende deze laag zijn
        eigen ruimte uit en kon hij alsnog verkopen. Een voorzien tekort
        betekent juist dat de werkelijke nachtbehoefte boven de reserve ligt.
        Eén poort voor de vraag "mag er verkocht worden".
        """
        if self._verkoop_geblokkeerd_door_reserve:
            return False
        toets = self.last_sell_check
        return not (isinstance(toets, dict) and toets.get("mag_verkopen") is False)

    def _is_worth_discharging_at_secondary_tier(
        self,
        entries: list[PriceEntry],
        now: datetime,
        headroom_kwh: float,
        discharge_power_w: float,
    ) -> bool:
        """Is 'now' worth discharging at the wider, secondary price tier
        (see `_get_secondary_expensive_price_threshold`), using only
        *spare* headroom left over after today's remaining primary-tier
        (genuinely expensive) quarters are accounted for?

        Without this, headroom that's clearly more than today's real
        price peak needs goes unused on quarters that don't quite clear
        the strict threshold but are still meaningfully above the day's
        cheap baseline - "leaving money on the table" on days with
        abundant battery capacity (found via a live report: 8kWh
        available, only a single 15-minute quarter sold, while
        surrounding quarters at a only slightly lower price went
        untouched).

        Same price-priority principle as `_is_worth_discharging_now`,
        just applied to the secondary tier's candidates and spare
        headroom specifically, ranked purely by price so the best of the
        "not quite primary-tier" quarters win first.
        """
        secondary_threshold = self._get_secondary_expensive_price_threshold(
            entries, now
        )
        if secondary_threshold is None:
            return False

        # Find 'now's raw price directly (same scale as the thresholds
        # above, both derived from raw entry prices) - not
        # _get_current_price_per_kwh, which converts to €/kWh and would
        # silently compare mismatched units against the raw threshold.
        now_price_raw = next(
            (e[2] for e in entries if e[0] <= now < e[1]), None
        )
        if now_price_raw is None or now_price_raw < secondary_threshold:
            return False

        spare_headroom_kwh = self._get_spare_headroom_after_primary_tier_kwh(
            entries, now, headroom_kwh, discharge_power_w
        )
        if spare_headroom_kwh <= 0:
            return False

        primary_threshold = self._get_expensive_price_threshold(entries, now)
        todays_entries = [e for e in entries if e[0].date() == now.date()]
        secondary_candidates = [
            e
            for e in todays_entries
            if e[2] >= secondary_threshold
            and (primary_threshold is None or e[2] < primary_threshold)
            and e[1] > now
        ]
        if not secondary_candidates:
            return False

        secondary_candidates.sort(key=lambda e: e[2], reverse=True)

        energy_per_quarter_kwh = (discharge_power_w / 1000) * 0.25
        if energy_per_quarter_kwh <= 0:
            return False
        quarters_affordable = max(
            1, int(spare_headroom_kwh / energy_per_quarter_kwh)
        )

        top_slots = secondary_candidates[:quarters_affordable]
        return any(e[0] <= now < e[1] for e in top_slots)

    def _is_worth_discharging_now(
        self,
        entries: list[PriceEntry],
        now: datetime,
        headroom_kwh: float,
        discharge_power_w: float,
    ) -> bool:
        """Is 'now' worth spending discharge headroom on, given the other
        remaining expensive quarters today?

        Without this, headroom gets consumed chronologically - the first
        expensive quarters encountered "win", even if later quarters
        today are priced higher. This ranks all of today's remaining
        expensive quarters by price and only spends headroom on however
        many of the *priciest* ones it can actually sustain, holding back
        otherwise - so a long elevated-price evening with a genuine peak
        later on sells at the peak, not just whichever quarter happened
        to come first.
        """
        todays_entries = [e for e in entries if e[0].date() == now.date()]
        threshold = self._get_expensive_price_threshold(entries, now)
        if threshold is None:
            return True  # no meaningful ranking possible, don't block

        remaining_expensive = [
            e for e in todays_entries if e[2] >= threshold and e[1] > now
        ]
        if not remaining_expensive:
            return True

        remaining_expensive.sort(key=lambda e: e[2], reverse=True)

        energy_per_quarter_kwh = (discharge_power_w / 1000) * 0.25
        if energy_per_quarter_kwh <= 0:
            return True
        quarters_affordable = max(1, int(headroom_kwh / energy_per_quarter_kwh))

        top_slots = remaining_expensive[:quarters_affordable]
        return any(e[0] <= now < e[1] for e in top_slots)

    def _verkoopreserve_uit(
        self,
        reserve: float | None,
        u: dict | None,
        blok_start: datetime | None,
        blok_eind: datetime | None,
        prijs: float | None,
        entries,
    ) -> dict:
        """De reserve bij VERKOPEN: zonder wat het volgende blok terugláádt (v5.70).

        Gevraagd: "economisch moet het winstgevend zijn maar het huis mag
        nooit te kort komen." De reserve is sinds v3.99.18 het diepste tekort
        tot het goedkope blok PLUS de lange horizon: wat er NA het blok nog
        nodig is. Voor het laden klopt dat. Maar bij verkopen hield hij zo
        ook de energie vast die het blok zelf weer goedkoper bijlaadt.
        Gemeten in de eigen plantoetsing (30 dagen): mediaan 70% minder
        verkocht dan gepland, 's ochtends nog 40-58% in de accu op zonnige
        dagen (04-08 oktober).

        Hier: het deel tot het blok blijft volledig beschermd, met de hele
        marge en de bodem - het huis gaat voor. Van het deel na het blok
        mag verkocht worden wat het blok kan terugladen (laadvermogen x
        blokduur x rendement), en alleen als verkopen nu minstens
        `VERKOOP_NA_BLOK_MIN_WINST_EUR` meer oplevert dan terugladen kost
        (goedkoopste blokprijs / rendement + slijtage). Anders de gewone
        reserve, zoals voorheen.
        """
        uit = {"reserve_kwh": reserve, "vrij_na_blok_kwh": 0.0, "toegepast": False}
        # v5.81.1: de reserve vóór het plafond, zodat de verkooptoets ziet of
        # de woning meer nodig heeft dan er in de accu past.
        uit["ongekapt_kwh"] = (u or {}).get("ongekapt_kwh")
        if reserve is None or not u or blok_start is None:
            uit["reden"] = "geen reserve of blok"
            return uit
        lang = max(0.0, float(u.get("lange_horizon_extra_kwh") or 0.0))
        if lang <= 0.01:
            uit["reden"] = "niets na het blok"
            return uit
        if blok_eind is None or blok_eind <= blok_start:
            a, b = self.last_cheap_block_start, self.last_cheap_block_end
            if a is None or b is None or b <= a:
                uit["reden"] = "blokduur onbekend"
                return uit
            blok_eind = blok_start + (b - a)
        blokprijzen = [
            p / PRICE_SCALE_FACTOR
            for begin, _e, p in (entries or [])
            if blok_start <= begin < blok_eind
        ]
        rendement = self.learned_battery_efficiency_percent
        slijtage_ct = (self.get_wear_cost_overview() or {}).get("slijtage_ct_per_kwh")
        if not blokprijzen or not rendement or slijtage_ct is None or prijs is None:
            uit["reden"] = "blokprijs, rendement of slijtage onbekend"
            return uit
        terugladen = min(blokprijzen) / (rendement / 100) + slijtage_ct / 100
        uit["terugladen_eur"] = round(terugladen, 4)
        uit["prijs_eur"] = round(prijs, 4)
        uit["min_winst_eur"] = self._verkoop_min_winst_eur()
        if prijs < terugladen + uit["min_winst_eur"]:
            uit["reden"] = "terugladen in het blok kost te veel"
            return uit
        laad_kw = abs(self.instelling(CONF_MANUAL_CHARGE_POWER, DEFAULT_MANUAL_CHARGE_POWER) or 0) / 1000
        duur_h = (blok_eind - blok_start).total_seconds() / 3600
        laadbaar = laad_kw * duur_h * rendement / 100
        vrij = min(lang, laadbaar)
        if vrij <= 0.01:
            uit["reden"] = "het blok kan niets terugladen"
            return uit
        marge = 1 + float(u.get("total_percent") or 0.0) / 100
        ongekapt = float(u.get("ongekapt_kwh") or reserve)
        bodem = float(u.get("bodem_kwh") or self._reserve_bodem_kwh())
        verkoop = max(bodem, ongekapt - vrij * marge)
        uit["ongekapt_kwh"] = round(verkoop, 3)
        # v5.81.1: het plafond tussen de grenzen (`_reserve_plafond_kwh`).
        capaciteit = self._reserve_plafond_kwh()
        if capaciteit:
            verkoop = min(verkoop, capaciteit)
        verkoop = min(verkoop, reserve)
        uit.update(
            {
                "reserve_kwh": round(verkoop, 3),
                "vrij_na_blok_kwh": round(max(0.0, reserve - verkoop), 3),
                "laadbaar_in_blok_kwh": round(laadbaar, 2),
                "toegepast": verkoop < reserve - 0.001,
                "reden": "het blok laadt het deel na het blok goedkoper terug",
            }
        )
        return uit

    @staticmethod
    def _verkoopreserve_velden(info: dict | None) -> dict:
        """De verkoopreserve als attributen bij de verkooptoets (v5.70)."""
        info = info or {}
        if not info:
            return {}
        return {
            "verkoop_na_blok_vrij_kwh": info.get("vrij_na_blok_kwh"),
            "verkoop_na_blok_toegepast": bool(info.get("toegepast")),
            "verkoop_na_blok_reden": info.get("reden"),
            "terugladen_in_blok_eur": info.get("terugladen_eur"),
        }

    @staticmethod
    def _verkoopreserve_zin(info: dict | None) -> str:
        """Eén zin als het deel na het blok verkocht mag worden (v5.70)."""
        info = info or {}
        if not info.get("toegepast"):
            return ""
        return (
            f" De {info['vrij_na_blok_kwh']:.2f} kWh die pas na het blok nodig "
            "is, blijft niet vast: het blok laadt die terug voor "
            f"{info['terugladen_eur'] * 100:.1f} ct, verkopen levert "
            f"{info['prijs_eur'] * 100:.1f} ct."
        )

    def verkoopreserve(
        self, now: datetime, blok_start: datetime | None, entries=None
    ) -> dict:
        """De verkoopreserve van nu (v5.70) - zie `_verkoopreserve_uit`."""
        if blok_start is None or blok_start <= now:
            return {"reserve_kwh": None, "vrij_na_blok_kwh": 0.0, "toegepast": False}
        reserve = self._get_dynamic_discharge_reserve_kwh(now, blok_start, bewaar=False)
        u = self._reserve_gevraagde_uitsplitsing
        if entries is None:
            entries = self._get_forecast_entries()
        info = self._verkoopreserve_uit(
            reserve, u, blok_start, self.last_cheap_block_end,
            self.huidige_prijs_eur_per_kwh(now), entries,
        )
        self.last_verkoopreserve = {**info, "moment": now.isoformat()}
        return info

    last_verkoopreserve: dict | None = None

    def _piekverkoop(
        self,
        now: datetime,
        entries,
        cheap_block_start: datetime | None,
        beschikbaar_kwh: float | None,
    ) -> dict:
        """Loont het om nu ONDER de reserve te verkopen? (v5.22)

        Gevraagd: "het systeem moet zo slim mogelijk en kosten effectief
        zijn". Het laden rekent sinds v5.21 per kWh; het verkopen stopte
        tot nu toe op de reserve, ongeacht wat de rest van de nacht kost.

        De kWh zit al in de accu. Rendement en slijtage zijn gelijk of hij
        nu verkocht wordt of later het huis dekt. Dus telt alleen: wat is
        duurder, nu verkopen of later inkopen? Het tekort dat de verkoop
        veroorzaakt, wordt ergens tussen nu en het volgende goedkope blok
        ingekocht - hoogstens tegen het duurste kwartier dat nog komt. Ligt
        de prijs NU daarboven, dan levert verkopen altijd meer op dan het
        inkopen kost.
        """
        prijs_nu = self._get_current_price_per_kwh(entries or [], now)
        if prijs_nu is None or not beschikbaar_kwh or beschikbaar_kwh <= 0:
            return {"verkopen": False, "reden": "prijs of lading onbekend"}
        tot = (
            cheap_block_start
            if cheap_block_start is not None and cheap_block_start > now
            else now + timedelta(hours=24)
        )
        reeks = [(b, p / PRICE_SCALE_FACTOR) for b, _e, p in (entries or [])]
        blok = cheap_block_start if cheap_block_start is not None and cheap_block_start > now else None
        duurste_later = self._duurste_later(
            now, reeks, blok, self._piek_vervangprijs(entries, blok)
        )
        if duurste_later == float("-inf"):
            return {"verkopen": False, "reden": "geen prijzen tot het blok"}
        return {
            "verkopen": prijs_nu > duurste_later,
            "prijs_nu_eur": round(prijs_nu, 4),
            "duurste_later_eur": round(duurste_later, 4),
            "winst_ct_per_kwh": round((prijs_nu - duurste_later) * 100, 1),
            "tot": tot.isoformat(),
            "reden": (
                "nu duurder dan elk kwartier dat nog komt"
                if prijs_nu > duurste_later
                else "er komt nog een duurder kwartier"
            ),
        }

    def _geen_ruimte_boven_reserve(
        self,
        now: datetime,
        entries,
        cheap_block_start: datetime | None,
        available_kwh: float | None,
        reserve_kwh: float | None,
        base_power: float,
        interval_hours: float,
    ) -> float | None:
        """Geen ruimte boven de reserve: dan wordt er niet verkocht.

        v5.28.4: HET HUIS GAAT VOOR. Hier verkocht de piekregel onder de
        reserve tot de bodem. De energie onder de reserve is voor de woning
        tot het volgende bijvullen - die wordt niet meer verkocht.
        """
        self.last_piekverkoop = {
            "verkopen": False,
            "reden": "het huis gaat voor: onder de reserve wordt niet verkocht",
        }
        self.last_discharge_power_applied = None
        _LOGGER.debug(
            "Geen ruimte boven de reserve: beschikbaar %.2f kWh, reserve %.2f kWh - niet verkopen",
            available_kwh or 0.0,
            reserve_kwh or 0.0,
        )
        return None

    def _cheapest_block_range(
        self, entries: list[PriceEntry], now: datetime, stabiel: bool = True
    ) -> tuple[datetime | None, datetime | None]:
        """Find the natural cheap price valley around the cheapest upcoming
        interval, instead of searching for a fixed-duration window.

        Starts at the single cheapest upcoming interval, then expands
        outward (backward and forward) while contiguous neighbouring
        intervals stay within CHEAP_BLOCK_THRESHOLD_MARGIN_FRACTION of the
        price range above the minimum. This makes the block's width adapt
        to how wide the actual daily price dip is, instead of assuming a
        fixed number of hours.

        Includes hysteresis: if the previously selected cheap block is
        still upcoming and its price is within
        CHEAP_BLOCK_STABILITY_MARGIN_FRACTION of the newly found
        candidate, keeps the previous choice instead of switching. Found
        after a real incident: as time passes and which quarters count as
        "still upcoming" shifts, two near-tied candidates elsewhere in
        the day could otherwise flip which one "wins" from one tick to
        the next - each requiring a wildly different reserve (hours until
        a cheap block a few minutes away vs. one many hours away).
        """
        if not entries:
            return None, None

        upcoming = [entry for entry in entries if entry[1] > now]
        if not upcoming:
            return None, None

        prices = [entry[2] for entry in upcoming]
        min_price = min(prices)
        max_price = max(prices)
        price_range = max_price - min_price

        cheapest_idx = min(range(len(upcoming)), key=lambda i: upcoming[i][2])

        # v5.33: `stabiel=False` voor de planning, die het blok voor een
        # LATER moment zoekt; de hysterese hoort bij de sturing van nu.
        if (
            stabiel
            and self.last_cheap_block_start is not None
            and price_range > 0
        ):
            previous_idx = next(
                (
                    i
                    for i, entry in enumerate(upcoming)
                    if entry[0] == self.last_cheap_block_start
                ),
                None,
            )
            if previous_idx is not None:
                previous_price = upcoming[previous_idx][2]
                new_price = upcoming[cheapest_idx][2]
                stability_margin = price_range * CHEAP_BLOCK_STABILITY_MARGIN_FRACTION
                if previous_price <= new_price + stability_margin:
                    cheapest_idx = previous_idx

        if price_range <= 0:
            # Flat prices: no meaningful valley, just use the single
            # cheapest (first) interval.
            return upcoming[cheapest_idx][0], upcoming[cheapest_idx][1]

        threshold = min_price + price_range * CHEAP_BLOCK_THRESHOLD_MARGIN_FRACTION

        start_idx = cheapest_idx
        while (
            start_idx > 0
            and upcoming[start_idx - 1][1] == upcoming[start_idx][0]
            and upcoming[start_idx - 1][2] <= threshold
        ):
            start_idx -= 1

        end_idx = cheapest_idx
        while (
            end_idx < len(upcoming) - 1
            and upcoming[end_idx + 1][0] == upcoming[end_idx][1]
            and upcoming[end_idx + 1][2] <= threshold
        ):
            end_idx += 1

        return upcoming[start_idx][0], upcoming[end_idx][1]

    def _verwachte_verkoopreserve(self, sturing: float) -> float:
        """Wat de verkooptoets bij deze sturingsreserve hoort te lezen
        (v5.81.1): de verkoopreserve van deze ronde (`last_verkoopreserve`,
        v5.70) of anders de sturingsreserve, minstens de bodem en hooguit het
        plafond - precies zoals `may_sell_now` hem afrondt."""
        info = self.last_verkoopreserve or {}
        reserve = info.get("reserve_kwh")
        verwacht = float(reserve) if reserve is not None else float(sturing)
        verwacht = max(verwacht, self._reserve_bodem_kwh())
        plafond = self._reserve_plafond_kwh()
        return min(verwacht, plafond) if plafond else verwacht

    async def _negatieve_prijs_ronde(self, now: datetime, entries) -> None:
        """De ronde bij een negatieve prijs (uit `_async_update_locked`, v5.177.0).

        De panelen gaan omlaag zoals altijd. v5.177.0 (A15): de accu volgt het
        waardeplan - dat rekent met de negatieve inkoopprijs en laadt dan zelf
        uit het net. Alleen zonder plan (of bij celbescherming) de vaste
        handmatige lading zoals voorheen.
        """
        # v5.186.0 (B19): ook opnieuw als de ramp naar 0 % (nog) niet liep -
        # in de leermodus of opstartfase wordt hij overgeslagen - en de
        # vorige ronde nakijken.
        if not self._is_negative_price_active or self._paneelgrens_doel != 0.0:
            self._is_negative_price_active = True
            self._start_solar_ramp(0.0)
        else:
            self._bewaak_stap("paneelgrens_controle", self._controleer_paneelgrens)
        if WAARDEPLAN_STUURT and not (self.celbeschermingsbesluit(now) or {}).get("actie"):
            if await self._waardeplan_als_nodig(now, entries):
                return
        charge_power = self.instelling(CONF_NEGATIVE_PRICE_CHARGE_POWER, DEFAULT_NEGATIVE_PRICE_CHARGE_POWER)
        await self._async_apply_manual(charge_power)
        self.last_reason = "negative_price"
        self.last_charge_power_applied = charge_power
        self._update_financial_tracking(
            now, entries, self.last_reason, None, charge_power
        )
        self._finish_decision_tick(now)

    def _secundaire_laag(self, now: datetime, entries, cheap_block_start) -> bool:
        """Mag er in de secundaire laag verkocht worden? (uit `_async_update_locked`,
        v5.177.0). Zie de toelichting daar. v5.177.0 (A15): stuurt het
        waardeplan deze ronde, dan alleen de drempel (weergave) en verder niets:
        de reserves en de waardetoets worden dan door niets gebruikt."""
        secondary_threshold_raw = self._get_secondary_expensive_price_threshold(
            entries, now
        )
        self.last_secondary_price_threshold = (
            secondary_threshold_raw / PRICE_SCALE_FACTOR
            if secondary_threshold_raw is not None
            else None
        )
        if self._waardeplan_gaat_sturen(now, entries):
            return False
        secondary_available_entity = self.config.get(CONF_AVAILABLE_ENERGY_SENSOR)
        # v5.81.1: met de modulesprong (L-EMS-014), net als elke andere
        # lezer van de beschikbare energie.
        secondary_available_kwh = self._na_module_leeg(
            self._read_sensor_float(secondary_available_entity)
            if secondary_available_entity
            else None
        )
        if secondary_available_kwh is not None and secondary_available_kwh > 0:
            secondary_reserve_kwh = self._get_dynamic_discharge_reserve_kwh(
                now, cheap_block_start
            )
            # v5.70: verkopen - de verkoopreserve.
            if secondary_reserve_kwh is not None:
                _verkoop = self.verkoopreserve(
                    now, cheap_block_start, entries
                ).get("reserve_kwh")
                if _verkoop is not None:
                    secondary_reserve_kwh = _verkoop
            if secondary_reserve_kwh is not None:
                secondary_headroom_kwh = max(
                    0.0, secondary_available_kwh - secondary_reserve_kwh
                )
                secondary_discharge_power = self.instelling(CONF_MANUAL_DISCHARGE_POWER, DEFAULT_MANUAL_DISCHARGE_POWER)
                # v3.99.9: en alleen als de verkooptoets niet dicht
                # staat. Elke minuut om op 3 september, 23:35-23:38:
                # de dode zones zitten in `may_sell_now`, maar zegt
                # die nee, dan viel de code hier door en rekende deze
                # laag zijn eigen ruimte uit - zonder rem. Twee
                # poorten voor dezelfde vraag, waarvan er een geremd
                # was.
                if self._secundaire_laag_toegestaan() and (
                    self._is_worth_discharging_at_secondary_tier(
                        entries, now, secondary_headroom_kwh, secondary_discharge_power
                    )
                ):
                    return True

        return False
