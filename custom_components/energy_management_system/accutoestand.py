"""Accutoestand van de coordinator: laadstand, modules, ondergrens en celbescherming (B4.3).

De accustand en bruikbare energie, de SoC-demper, de effectieve ondergrens,
module-leeg en modulesprongen, de modulegezondheid (CUSUM, drift,
kalibratie), het balanceren en de celbescherming. Ongewijzigd verhuisd uit
`coordinator.py`; de coordinator erft deze mixin.
"""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta
from homeassistant.util import dt as dt_util
from .const import (
    BALANCEER_VOL_PERCENT,
    BATTERY_MODULE_CELL_DELTA_MATERIEEL_V,
    BATTERY_MODULE_TEMPERATURE_MATERIEEL_C,
    BATTERY_MODULE_CUSUM_SLACK_C,
    BATTERY_MODULE_CUSUM_SLACK_PERCENT,
    BATTERY_MODULE_CUSUM_SLACK_V,
    BATTERY_MODULE_CUSUM_THRESHOLD_C,
    BATTERY_MODULE_CUSUM_THRESHOLD_PERCENT,
    BATTERY_MODULE_CUSUM_THRESHOLD_V,
    BATTERY_MODULE_FLAT_SOC_MAX_PERCENT,
    BATTERY_MODULE_FLAT_SOC_MIN_PERCENT,
    BATTERY_MODULE_HISTORY_DAYS,
    BATTERY_MODULE_MIN_SAMPLES_PER_DAY,
    BATTERY_MODULE_SOC_BUCKET_SIZE_PERCENT,
    BATTERY_MODULE_TEMPERATURE_ATTENTION_C,
    CAPACITY_TREND_HISTORY_DAYS,
    CELBESCHERMING_AAN,
    CELBESCHERMING_BUFFER_KWH,
    CELBESCHERMING_START_V,
    CELBESCHERMING_VRIJ_KWH,
    CELSPANNING_AANDACHT_V,
    CELSPANNING_DAGEN_VOOR_PATROON,
    CELSPANNING_KRITIEK_V,
    CELSPANNING_VENSTER_UREN,
    CONF_APPLIANCE_NOTIFY_SERVICE,
    CONF_AVAILABLE_ENERGY_SENSOR,
    CONF_BATTERY_MIN_SOC_NUMBER,
    CONF_BATTERY_MODULE_CELL_VOLTAGE_MAX_SENSORS,
    CONF_BATTERY_MODULE_CELL_VOLTAGE_MIN_SENSORS,
    CONF_BATTERY_MODULE_POWER_SENSORS,
    CONF_BATTERY_MODULE_SOC_SENSORS,
    CONF_BATTERY_MODULE_TEMPERATURE_SENSORS,
    CONF_BATTERY_POWER_SENSOR,
    CONF_BATTERY_TOTAL_CAPACITY_SENSOR,
    CONF_CONSUMPTION_POWER_SENSOR,
    CONF_MANUAL_CHARGE_POWER,
    CONF_MIN_SOC_PERCENT,
    CONF_SOC_SENSOR,
    CUSUM_MIN_HISTORY_FOR_REFERENCE,
    CUSUM_REFERENCE_EXCLUDE_RECENT_DAYS,
    DEFAULT_MANUAL_CHARGE_POWER,
    DEFAULT_MIN_SOC_PERCENT,
    KALIBRATIE_MIN_SCHAALDEEL,
    KALIBRATIE_VOL_PERCENT,
    KALIBRATIE_HOUD_MIN,
    MODULE_LEEG_CEL_V,
    MODULE_LEEG_HERSTEL_PROCENT,
    MODULE_LEEG_HERSTEL_V,
    MODULE_LEEG_SOC_PROCENT,
    MODULE_LEEG_SPRONGEN_BEWAARD,
    MODULE_LEEG_SPRONG_KWH,
    MODULE_LEEG_SPRONG_MAX_KWH,
    MODULE_LEEG_SPRONG_MIN_PROCENT,
    NILM_CUSUM_RESET_STREAK_DAYS,
    ONDERGRENS_AFNAME_W,
    ONDERGRENS_GELDIG_DAGEN,
    ONDERGRENS_LEVER_W,
    ONDERGRENS_MAX_BOVEN,
    ONDERGRENS_MIN_BOVEN,
    ONDERGRENS_STIL_MINUTEN,
    ONDERGRENS_STIL_W,
    ONDERGRENS_WAARNEMINGEN_BEWAARD,
    OPTION_SMART,
    OPTION_SMART_CHARGING,
    OPTION_SMART_DISCHARGING,
    PRICE_SCALE_FACTOR,
    SOC_DEMPER_MAX_STAP_KWH,
    SOC_DEMPER_MINUTEN,
    SOC_DEMPER_STIL_W,
)
from .coordinator_hulp import demp_soc_stap, effectieve_ondergrens


class AccuToestandMixin:
    """De accutoestand-methodes van de coordinator."""

    def _module_temperature_spread_at_rest(self) -> float | None:
        """Het temperatuurverschil tussen modules in rust (v1.16.4).

        Externe warmte - een omvormer erboven - werkt dag en nacht door;
        eigen verlies alleen onder belasting. Blijft het verschil in rust
        even groot, dan komt het van buiten.

        Gebruikt de dagelijkse geschiedenis, die op rustige momenten
        wordt vastgelegd.
        """
        laatste: list[float] = []
        for staat in (self.battery_module_health or {}).values():
            reeks = (staat.get("geschiedenis") or {}).get("temperatuur_c") or []
            if reeks and reeks[-1] is not None:
                laatste.append(reeks[-1])
        if len(laatste) < 2:
            return None
        return max(laatste) - min(laatste)

    def accustand_procent(self) -> float | None:
        """De accustand, rechtstreeks van de sensor (v1.31.1).

        Gevonden in de export van 11 augustus 08:36: `last_soc_percent`
        stond op **None** terwijl de accu gewoon 22% aangaf en alle drie
        de modules netjes rapporteerden.

        De oorzaak is dezelfde vorm als bij `beschikbare_energie_kwh` in
        v1.24.1: dat veld wordt alléén gezet in de berekening van het
        ontlaadvermogen, en die tak wordt niet bereikt zodra de tick
        eerder eindigt - bijvoorbeeld bij `solar_capture_deferred`, wat
        juist elke ochtend gebeurt die met uitstellen begint.

        Zo'n veld is een bijproduct van een berekening, geen accustand.
        Wie de stand nodig heeft, hoort de sensor te lezen.
        """
        gemeten = self._read_sensor_float(self.config.get(CONF_SOC_SENSOR))
        if gemeten is not None:
            return gemeten

        # v3.50.0: dezelfde regel als bij de beschikbare energie - een
        # verse waarde mag, een oude niet.
        if self._meting_is_vers("last_soc_percent"):
            return self.last_soc_percent

        # v3.48.0: `last_soc_percent` is GEEN blinde terugval meer.
        #
        # Gemeld in de export van 27 augustus 08:09. Het veld stond op
        # 38% terwijl elk ander getal in dezelfde export "leeg" zei:
        #
        #     kwartierplan begint     10 %
        #     modules                 2, 8, 7 %
        #     grafiek van de sensor    6 %
        #     kalman gefilterd         0,0 kWh
        #
        # De sensor liep gewoon door - die 38% kwam ergens uit de nacht,
        # toen een tak die het veld zet voor het laatst werd bereikt.
        #
        # Dat is precies de vorm waarvoor deze helper in v1.31.1 is
        # gemaakt: een bijproduct van een berekening is geen accustand.
        # Toen ging het om None in plaats van 22%; het veld bleef als
        # terugval staan en levert nu een getal dat er twintig uur naast
        # zit. Een oude waarde is gevaarlijker dan geen waarde, want er
        # wordt zonder aarzeling mee gerekend.
        #
        # Zegt de sensor niets, dan liever afleiden uit de beschikbare
        # energie - dat is een VERSE meting - en anders niets.
        # Laatste terugval: afleiden uit de beschikbare energie.
        # v3.5.0: de GEMETEN capaciteit zodra die er is.
        beschikbaar = self.beschikbare_energie_kwh()
        capaciteit = self.bruikbare_capaciteit_kwh()
        if beschikbaar is None or not capaciteit:
            return None
        min_soc = self.effective_min_soc_percent()
        bruikbaar = capaciteit * (100 - min_soc) / 100
        if bruikbaar <= 0:
            return None
        return min_soc + (100 - min_soc) * beschikbaar / bruikbaar

    def beschikbare_energie_kwh(self) -> float | None:
        """De bruikbare energie in de accu (v1.24.1).

        Gemeld met screenshot: "Nog geen planning" en "Accustand
        onbekend" terwijl de accu gewoon 7,69 kWh had.

        De oorzaak: `last_available_kwh` wordt alleen gezet als de HELE
        energie-check slaagt, en op een tak zonder verbruiksschatting
        wordt hij zelfs expliciet op None gezet. Dat veld is dus een
        bijproduct van die check, geen betrouwbare accustand.

        Deze functie leest de sensor rechtstreeks, met het bijproduct
        als terugval. Nieuwe onderdelen die alleen de accustand nodig
        hebben, horen niet af te hangen van een berekening die om heel
        andere redenen kan afbreken.
        """
        gemeten = self._read_sensor_float(
            self.config.get(CONF_AVAILABLE_ENERGY_SENSOR)
        )
        if gemeten is not None and gemeten >= 0:
            # v5.72 (L-EMS-014): min de verwachte sprong van een bijna lege
            # module. De terugval hieronder komt uit de brug, die al
            # gecorrigeerd is.
            return self._na_module_leeg(gemeten)
        if gemeten is not None:
            # v5.167.0 (audit 02-11): onder de min-SoC meldt de Zendure een
            # negatieve beschikbare energie (-0,576 gezien). Dat is een
            # verse meting van "niets bruikbaar", geen storing: 0, niet de
            # (mogelijk oude) terugval hieronder.
            return 0.0

        # v3.50.0: het bijproduct mag terugval blijven, maar alleen
        # zolang het VERS is.
        #
        # Eerst had ik de terugval helemaal geschrapt, net als bij
        # `accustand_procent()`. Achtenveertig toetsen vielen om, en dat
        # was terecht: bij een sensor die één ronde niets zegt, is een
        # waarde van een minuut geleden prima. De aansturing helemaal
        # stilzetten bij elke hapering is erger dan het kwaad.
        #
        # Het probleem is niet de terugval maar de LEEFTIJD ervan. Op 27
        # augustus stond de accustand op 38% terwijl de accu op 6% zat -
        # een waarde uit de nacht. Een minuut oud is bruikbaar, vijf uur
        # niet, en zonder tijdstempel is dat verschil niet te zien.
        if self._meting_is_vers("last_available_kwh"):
            return self.last_available_kwh
        return self.last_projection_available_kwh

    # --- v5.72 (L-EMS-014): een module die bijna leeg is ----------------

    _module_leeg: dict | None = None
    _module_leeg_socs: list | None = None
    # Bewaard (PERSISTED_FIELDS); None tot de eerste gemeten sprong.
    module_leeg_sprongen: list | None = None

    def module_leeg_correctie_kwh(self) -> float:
        """Hoeveel van de beschikbare energie er vooraf af gaat (v5.72).

        In 2 van 2 bijna-lege nachten sprong de laadstand 4-5% omlaag zodra
        een module (AB3000 00996) onder 15% kwam: circa 0,35 kWh die de EMS
        dacht nog te hebben. Zolang een module onder `MODULE_LEEG_SOC_PROCENT`
        staat (of een cel onder `MODULE_LEEG_CEL_V`) en die sprong nog niet
        gezien is, telt hij niet als beschikbaar. Geen moduledata, geen
        correctie.

        v5.176.0 (L-EMS-061): alleen voor een module die zelf zo'n sprong
        liet zien (`module_leeg_sprongen[].module`), met de mediaan van
        haar eigen sprongen. Na het vertrek van 00996 werkte haar sprong
        door op de andere drie, die op 16 van 40 dagen op <= 14 % stonden
        en nooit naar 0 gingen: tot 0,43 kWh telde als leeg. Springt een
        andere module wel, dan wordt dat gemeten en geldt het voor haar.
        """
        staat = self._module_leeg or {}
        if not staat.get("actief") or staat.get("sprong_gezien"):
            return 0.0
        module = staat.get("apparaat")
        if not self._module_eigen_sprongen(module):
            return 0.0
        sprong = self._module_leeg_sprong_kwh(module)
        # v5.172.0 (punt 4): de sprong is de lage module die naar 0 % gaat
        # (01-11 18:15: module 00996 18 -> 0 %, totaal 20 -> 15 %, gemeten
        # 0,551 kWh = ~18 % van een module). Hij kan dus nooit meer zijn dan
        # wat die module zelf nog meldt (hoogste stand van het laatste half
        # uur, tegen het zaagtandje). 02-11 's nachts stond de module op
        # 11-15 %: hooguit 0,43 kWh in plaats van 0,551.
        plafond = staat.get("plafond_kwh")
        if isinstance(plafond, (int, float)) and plafond >= 0:
            return min(sprong, float(plafond))
        return sprong

    def _module_eigen_sprongen(self, module: str | None) -> list[float]:
        """De geldige gemeten sprongen van één module, of alle bij None."""
        return [
            float(r["kwh"]) for r in (self.module_leeg_sprongen or [])
            if isinstance(r, dict) and isinstance(r.get("kwh"), (int, float))
            and 0 < r["kwh"] <= MODULE_LEEG_SPRONG_MAX_KWH
            and (module is None or r.get("module") == module)
        ]

    def _module_leeg_sprong_kwh(self, module: str | None = None) -> float:
        """De sprong: gemeten als die er is, anders de constante (v5.72).

        Met `module` alleen haar eigen sprongen (v5.176.0). De constante is
        alleen nog de weergave; `module_leeg_correctie_kwh` trekt hem niet af.
        """
        gemeten = self._module_eigen_sprongen(module)
        return round(statistics.median(gemeten), 3) if gemeten else MODULE_LEEG_SPRONG_KWH

    def _na_module_leeg(
        self, beschikbaar_kwh: float | None, correctie: float | None = None
    ) -> float | None:
        """De bruikbare energie uit de gemeten beschikbare energie (v5.72).

        Elke lezer van de beschikbare energie (sturing, plan, reserve,
        tekort, spiegel, besparing) gaat hierdoor. v5.172.0: eerst het
        SoC-flapperen bij stilstand eruit (`_demp_soc_flapperen`, punt 1),
        dan eraf wat er boven de werkelijke bodem niet uit kan: de grootste
        van de verwachte modulesprong en de effectieve ondergrens (punt 4,
        `ondergrens_correctie_kwh`). Die twee beschrijven hetzelfde (een
        module die eerder leeg is), dus niet optellen. Nooit onder nul;
        None blijft None.
        """
        if beschikbaar_kwh is None:
            return None
        beschikbaar_kwh = self._demp_soc_flapperen(beschikbaar_kwh)
        if correctie is None:
            correctie = self.beschikbaar_correctie_kwh()
        if correctie <= 0:
            return beschikbaar_kwh
        return max(0.0, beschikbaar_kwh - correctie)

    def beschikbaar_correctie_kwh(self) -> float:
        """Wat `_na_module_leeg` nu van de meting aftrekt (v5.175.0).

        De grootste van de modulesprong en de ondergrenscorrectie; veilig
        falen naar 0 (of de ondergrens).
        """
        try:
            correctie = self.module_leeg_correctie_kwh()
        except Exception:  # noqa: BLE001 - veilig falen: geen correctie
            correctie = 0.0
        try:
            correctie = max(correctie, self.ondergrens_correctie_kwh())
        except Exception:  # noqa: BLE001 - veilig falen: de min-SoC
            pass
        return max(0.0, float(correctie or 0.0))

    # --- v5.172.0 punt 1: SoC-flapperen bij stilstand ----------------------

    _soc_demper: dict | None = None

    def _demp_soc_flapperen(self, gemeten: float) -> float:
        """De gemeten beschikbare energie zonder flapperen bij 0 W (v5.172.0).

        Zie `demp_soc_stap`. Alleen met een werkende accuvermogenssensor en
        een niet-negatieve meting; anders de meting zelf.
        """
        if not isinstance(gemeten, (int, float)) or gemeten < 0:
            return gemeten
        if not self.config.get(CONF_BATTERY_POWER_SENSOR):
            return gemeten
        try:
            vermogen = self._read_corrected_battery_power()
        except Exception:  # noqa: BLE001 - zonder vermogen niet dempen
            vermogen = None
        if vermogen is None:
            return gemeten
        waarde, self._soc_demper = demp_soc_stap(
            self._soc_demper, float(gemeten), float(vermogen), dt_util.now()
        )
        return waarde

    def voorraad_inhoud_kwh(self) -> float | None:
        """De gemeten inhoud boven de min-SoC voor de besparing (v5.172.0, punt 3).

        Gedempt tegen flapperen, maar ZONDER de modulesprong en de
        ondergrens: dat zijn verwachtingen voor de sturing. De voorraad
        waarderen met een verwachting gaf op 02-11 een schijnverlies: de
        dag eindigde op 15-16 % (0,58-0,69 kWh gemeten) maar telde als
        0,02 kWh, ~EUR 0,24 te weinig. Gaat de module later echt naar 0 %,
        dan is dat verlies er op dat moment wel, in de meting.
        """
        entiteit = (getattr(self, "config", None) or {}).get(CONF_AVAILABLE_ENERGY_SENSOR)
        gemeten = self._read_sensor_float(entiteit) if entiteit else None
        if gemeten is None:
            return self.beschikbare_energie_kwh()
        if gemeten < 0:
            return 0.0
        return self._demp_soc_flapperen(gemeten)

    def get_soc_demper(self) -> dict:
        """De toestand van de demper, voor sensor en export (v5.172.0)."""
        st = self._soc_demper or {}
        return {
            "actief": bool(st),
            "waarde_kwh": None if st.get("waarde") is None else round(st["waarde"], 3),
            "kandidaat_kwh": None if st.get("kandidaat") is None else round(st["kandidaat"], 3),
            "stroom_sinds_kwh": round(float(st.get("stroom_kwh") or 0.0), 3),
            "gedempte_stappen": int(st.get("gedempt") or 0),
            "regel": (
                f"stilstand (< {SOC_DEMPER_STIL_W:.0f} W) en stap <= "
                f"{SOC_DEMPER_MAX_STAP_KWH} kWh: oude inhoud tot de nieuwe "
                f"{SOC_DEMPER_MINUTEN} min aanhoudt of er echt stroom liep"
            ),
        }

    # --- v5.172.0 punt 4: de effectieve ondergrens -------------------------

    #: Bewaard (PERSISTED_FIELDS): [{moment, soc, module, cel_min_v}].
    ondergrens_waarnemingen: list | None = None
    _ondergrens_stop: dict | None = None
    _ondergrens_vorig: dict | None = None

    def effectieve_ondergrens_procent(self, now: datetime | None = None) -> float:
        """De laadstand waaronder de accu in de praktijk niet levert (v5.172.0).

        De min-SoC, of hoger als de accu de laatste dagen eerder stopte (zie
        `effectieve_ondergrens`). Het apparaat zelf blijft op zijn min-SoC.
        """
        return effectieve_ondergrens(
            self.ondergrens_waarnemingen, self.effective_min_soc_percent(), now or dt_util.now()
        )[0]

    def ondergrens_correctie_kwh(self) -> float:
        """Wat er van de beschikbare energie af gaat door de ondergrens (v5.172.0).
        De Zendure meldt (SoC - min-SoC) x capaciteit; boven de bodem blijft
        (SoC - bodem) x capaciteit over."""
        if not self.ondergrens_waarnemingen:
            return 0.0
        boven = self.effectieve_ondergrens_procent() - self.effective_min_soc_percent()
        if boven <= 0:
            return 0.0
        capaciteit = self.bruikbare_capaciteit_kwh() or 0.0
        return capaciteit * boven / 100

    def _volg_ondergrens(self, now: datetime) -> None:
        """Stopte de accu met leveren boven de min-SoC? (v5.172.0, punt 4)

        Een stop telt als de accu leverde (>= ONDERGRENS_LEVER_W), daarna
        ONDERGRENS_STIL_MINUTEN lang stilstaat (< ONDERGRENS_STIL_W) terwijl
        het huis van het net neemt (>= ONDERGRENS_AFNAME_W), in een stand
        die de accu laat leveren (smart) en zonder wisseling van stand, met
        de laadstand tussen min-SoC + ONDERGRENS_MIN_BOVEN en + MAX_BOVEN.
        Levert de accu duidelijk onder een geleerde bodem, dan vervalt die.
        Alleen meten en rekenen; het apparaat blijft op zijn min-SoC.
        """
        accu = self._read_corrected_battery_power()
        net = self._read_sensor_float(self.config.get(CONF_CONSUMPTION_POWER_SENSOR))
        soc = self.accustand_procent()
        stand = getattr(self, "last_applied_operation", None)
        if accu is None or net is None or soc is None:
            self._ondergrens_stop = None
            return
        vorig, self._ondergrens_vorig = self._ondergrens_vorig, {"accu": accu, "stand": stand}
        self._ondergrens_vervalt_bij_dieper(now, soc, accu)
        min_soc = self.effective_min_soc_percent()
        stop = self._ondergrens_stop
        if accu >= ONDERGRENS_LEVER_W or stand not in (OPTION_SMART, OPTION_SMART_DISCHARGING):
            self._ondergrens_stop = None
            return
        if stop is None:
            if vorig and vorig.get("accu", 0) >= ONDERGRENS_LEVER_W and vorig.get("stand") == stand \
                    and abs(accu) < ONDERGRENS_STIL_W:
                self._ondergrens_stop = {"sinds": now, "soc": soc}
            return
        if abs(accu) >= ONDERGRENS_STIL_W or net < ONDERGRENS_AFNAME_W:
            self._ondergrens_stop = None
            return
        if (now - stop["sinds"]).total_seconds() < ONDERGRENS_STIL_MINUTEN * 60 or stop.get("genoteerd"):
            return
        stop["genoteerd"] = True
        soc_stop = float(stop["soc"])
        if not (min_soc + ONDERGRENS_MIN_BOVEN <= soc_stop <= min_soc + ONDERGRENS_MAX_BOVEN):
            return
        laag = min(
            (m for m in (self.battery_module_live or []) if m.get("soc_percent") is not None),
            key=lambda m: m["soc_percent"], default={},
        )
        self.ondergrens_waarnemingen = (list(self.ondergrens_waarnemingen or []) + [{
            "moment": stop["sinds"].isoformat(), "soc": round(soc_stop, 1),
            "module": laag.get("apparaat_id") or laag.get("naam"),
            "module_soc": laag.get("soc_percent"), "cel_min_v": laag.get("cel_min_v"),
            "net_w": round(net),
        }])[-ONDERGRENS_WAARNEMINGEN_BEWAARD:]

    def _ondergrens_vervalt_bij_dieper(self, now: datetime, soc: float, accu: float) -> None:
        """Levert de accu duidelijk onder de geleerde bodem, dan klopt die niet
        meer (module vervangen of gebalanceerd): waarnemingen erboven weg."""
        if not self.ondergrens_waarnemingen or accu < ONDERGRENS_LEVER_W:
            return
        bodem = self.effectieve_ondergrens_procent(now)
        if soc <= bodem - 1.0:
            self.ondergrens_waarnemingen = [
                w for w in self.ondergrens_waarnemingen
                if isinstance(w, dict) and isinstance(w.get("soc"), (int, float)) and w["soc"] <= soc
            ] or None

    def get_ondergrens(self, now: datetime | None = None) -> dict:
        """De effectieve ondergrens, voor sensor, uitleg en export (v5.172.0)."""
        now = now or dt_util.now()
        min_soc = self.effective_min_soc_percent()
        bodem, reden = effectieve_ondergrens(self.ondergrens_waarnemingen, min_soc, now)
        try:
            correctie = round(self.ondergrens_correctie_kwh(), 3)
        except Exception:  # noqa: BLE001
            correctie = None
        return {
            "procent": bodem,
            "min_soc_procent": min_soc,
            "reden": reden,
            "correctie_kwh": correctie,
            "waarnemingen": list(self.ondergrens_waarnemingen or []),
            "geldig_dagen": ONDERGRENS_GELDIG_DAGEN,
        }

    def ondergrens_zin(self) -> str | None:
        """Eén regel voor de uitleg, alleen als de bodem boven de min-SoC ligt."""
        info = self.get_ondergrens()
        if info["procent"] <= info["min_soc_procent"]:
            return None
        return (
            f"bruikbaar gerekend vanaf {info['procent']:.0f} % in plaats van "
            f"{info['min_soc_procent']:.0f} %: {info['reden']}"
        )

    def _volg_module_leeg(self, now: datetime) -> None:
        """Staat er een module bijna leeg, en is de sprong al gekomen? (v5.72)

        Aan: een module onder `MODULE_LEEG_SOC_PROCENT` of een cel onder
        `MODULE_LEEG_CEL_V`. Uit: alle bekende modules weer
        `MODULE_LEEG_HERSTEL_PROCENT` erboven (en de cellen
        `MODULE_LEEG_HERSTEL_V`). De sprong is gezien als de laadstand in één
        ronde (binnen tien minuten) minstens `MODULE_LEEG_SPRONG_MIN_PROCENT`
        zakt - ook als dat in het kwartier vóór het aanslaan gebeurde, want
        de modulesensor loopt soms achter op de totale laadstand. Daarna
        geen correctie meer: de sprong zit dan al in de meting. De gemeten
        sprong wordt bewaard. Ontbreekt de data, dan geen correctie.
        """
        modules = self.battery_module_live or []
        socs = [m.get("soc_percent") for m in modules if m.get("soc_percent") is not None]
        cellen = [m.get("cel_min_v") for m in modules if m.get("cel_min_v") is not None]
        soc_nu = self._read_sensor_float(self.config.get(CONF_SOC_SENSOR))
        # De totale laadstand van de laatste twintig minuten.
        reeks = [
            (t, v) for t, v in (self._module_leeg_socs or [])
            if (now - t).total_seconds() <= 1200
        ]
        if soc_nu is not None:
            reeks.append((now, float(soc_nu)))
        self._module_leeg_socs = reeks
        if not socs and not cellen:
            self._module_leeg = None
            return
        laag = [
            m for m in modules
            if (m.get("soc_percent") is not None and m["soc_percent"] < MODULE_LEEG_SOC_PROCENT)
            or (m.get("cel_min_v") is not None and m["cel_min_v"] < MODULE_LEEG_CEL_V)
        ]
        staat = self._module_leeg
        if staat and staat.get("actief"):
            hersteld = all(
                v >= MODULE_LEEG_SOC_PROCENT + MODULE_LEEG_HERSTEL_PROCENT for v in socs
            ) and all(v >= MODULE_LEEG_CEL_V + MODULE_LEEG_HERSTEL_V for v in cellen)
            if hersteld:
                self._module_leeg = None
                return
        elif laag:
            eerste = laag[0]
            staat = {
                "actief": True,
                "sinds": now.isoformat(),
                "module": eerste.get("module"),
                "apparaat": eerste.get("apparaat_id") or eerste.get("naam"),
                "soc_percent": eerste.get("soc_percent"),
                "cel_min_v": eerste.get("cel_min_v"),
                "sprong_gezien": False,
            }
            self._module_leeg = staat
        else:
            self._module_leeg = None
            return
        # v5.176.0 (L-EMS-061): staan er meer modules laag, dan telt de module
        # die zelf al eens sprong, ook als een andere als eerste laag stond.
        if not staat.get("sprong_gezien") and not self._module_eigen_sprongen(staat.get("apparaat")):
            met_sprong = next(
                (
                    m for m in laag
                    if self._module_eigen_sprongen(m.get("apparaat_id") or m.get("naam"))
                ),
                None,
            )
            if met_sprong is not None:
                staat.update(
                    module=met_sprong.get("module"),
                    apparaat=met_sprong.get("apparaat_id") or met_sprong.get("naam"),
                    soc_percent=met_sprong.get("soc_percent"),
                    cel_min_v=met_sprong.get("cel_min_v"),
                )
                self._module_leeg_modsocs = None
        self._module_leeg_plafond(now, staat, modules)
        if staat.get("sprong_gezien"):
            return
        # Is de sprong er (al)? Twee opeenvolgende metingen, hooguit tien
        # minuten uit elkaar, met minstens de drempel ertussen - na aftrek
        # van wat het ontladen in die tijd verklaart (bij 2,4 kW is dat
        # ruim 2% per vijf minuten; dat is geen sprong).
        capaciteit = self.bruikbare_capaciteit_kwh()
        try:
            accu_w = max(0.0, float(self._read_corrected_battery_power() or 0.0))
        except Exception:  # noqa: BLE001
            accu_w = 0.0
        for (t1, v1), (t2, v2) in zip(reeks, reeks[1:]):
            duur_s = (t2 - t1).total_seconds()
            if duur_s > 600:
                continue
            verklaard = (
                accu_w * duur_s / 3600 / 1000 / capaciteit * 100 if capaciteit else 0.0
            )
            sprong = (v1 - v2) - verklaard
            if sprong >= MODULE_LEEG_SPRONG_MIN_PROCENT:
                staat["sprong_gezien"] = True
                staat["sprong_moment"] = t2.isoformat()
                if capaciteit:
                    kwh = round(capaciteit * sprong / 100, 3)
                    if 0 < kwh <= MODULE_LEEG_SPRONG_MAX_KWH:
                        staat["sprong_kwh"] = kwh
                        self.module_leeg_sprongen = (
                            list(self.module_leeg_sprongen or [])
                            + [{"moment": t2.isoformat(), "kwh": kwh,
                                "module": staat.get("apparaat"),
                                "van_procent": round(v1, 1), "naar_procent": round(v2, 1)}]
                        )[-MODULE_LEEG_SPRONGEN_BEWAARD:]
                break

    _module_leeg_modsocs: list | None = None

    def _module_leeg_plafond(self, now: datetime, staat: dict, modules: list) -> None:
        """Hoe groot de modulesprong hooguit kan zijn (v5.172.0, punt 4).

        De hoogste stand van de lage module over het laatste half uur, maal
        de capaciteit van één module. Zie `module_leeg_correctie_kwh`.
        """
        naam = staat.get("apparaat")
        module = next(
            (m for m in modules if (m.get("apparaat_id") or m.get("naam")) == naam), None
        )
        reeks = [
            (t, v) for t, v in (self._module_leeg_modsocs or [])
            if (now - t).total_seconds() <= 1800
        ]
        if module is not None and module.get("soc_percent") is not None:
            reeks.append((now, float(module["soc_percent"])))
        self._module_leeg_modsocs = reeks
        capaciteit = self.bruikbare_capaciteit_kwh()
        if not reeks or not capaciteit or not modules:
            staat.pop("plafond_kwh", None)
            return
        hoogste = max(v for _t, v in reeks)
        staat["module_soc_max_30min"] = hoogste
        staat["plafond_kwh"] = round(max(0.0, hoogste) / 100 * capaciteit / len(modules), 3)

    def get_module_leeg(self) -> dict:
        """De toestand van de modulesprong, voor sensor en export (v5.72)."""
        staat = dict(self._module_leeg or {})
        return {
            "actief": bool(staat.get("actief")),
            "correctie_kwh": round(self.module_leeg_correctie_kwh(), 3),
            "sprong_kwh": self._module_leeg_sprong_kwh(staat.get("apparaat")),
            "eigen_sprong": bool(self._module_eigen_sprongen(staat.get("apparaat"))),
            "bron": "gemeten" if any(
                isinstance(r, dict) and r.get("kwh") for r in (self.module_leeg_sprongen or [])
            ) else "constante",
            "toestand": staat,
            "gemeten_sprongen": list(self.module_leeg_sprongen or []),
        }

    def effective_min_soc_percent(self) -> float:
        """De minimum-SoC die de accu WERKELIJK aanhoudt (v1.23.3).

        Gemeld: "Laagste SoC kan nooit 0% zijn, minimale SoC van mijn
        accu is 10%." En daarna: "Nee er is 1 harde begrenzing van 10%
        verder nergens."

        De configuratie stond op 15% terwijl de accu op 10% staat. Dat
        maakte 0,43 kWh onbruikbaar in elke berekening: de reserve hield
        te veel achter, het uitbreidingsadvies zag een kleinere accu, de
        SoC-percentages klopten niet en tekort-nachten werden eerder
        gemeld dan nodig.

        De omvormer weet het zelf - `number.solarflow_2400_ac_min_soc`
        stond al geconfigureerd maar werd op één plek gebruikt, terwijl
        het handmatige getal de berekeningen bepaalde. Nu andersom: de
        gemeten waarde gaat voor, het ingestelde getal is de terugval.
        """
        entity_id = self.config.get(CONF_BATTERY_MIN_SOC_NUMBER)
        if entity_id:
            gemeten = self._read_sensor_float(entity_id)
            if gemeten is not None and 0 <= gemeten <= 100:
                return float(gemeten)
        return float(
            self.instelling(CONF_MIN_SOC_PERCENT, DEFAULT_MIN_SOC_PERCENT) or 0
        )

    def get_celspanning_oordeel(self) -> dict:
        """Staat er een cel te laag, en wat zou bijladen kosten?
        (v3.52.0)

        Meet, oordeelt en rekent voor - maar stuurt niets. De keuze om
        bij te laden blijft handmatig, zoals afgesproken.

        Waarom de laagste celspanning en niet de laadstand: LiFePO4
        heeft een vlakke spanningskromme, dus onderin zegt de laadstand
        weinig. Wat telt is dat één cel de afschakelspanning raakt
        terwijl de rest nog ruimte heeft.
        """
        modules = self.battery_module_live or []
        spanningen = [
            (m["module"], m["cel_min_v"])
            for m in modules
            if m.get("cel_min_v") is not None
        ]
        uit: dict = {
            "beschikbaar": bool(spanningen),
            "aandachtsgrens_v": CELSPANNING_AANDACHT_V,
            "kritieke_grens_v": CELSPANNING_KRITIEK_V,
        }
        if not spanningen:
            uit["reden"] = "Geen celspanningen beschikbaar."
            return uit

        module, laagste = min(spanningen, key=lambda x: x[1])
        uit["laagste_cel_v"] = laagste
        uit["module"] = module
        uit["per_module"] = {str(m): v for m, v in spanningen}

        # Hoeveel dagen op rij zakte de laagste cel onder de grens?
        dagen = 0
        for staat in (self.battery_module_health or {}).values():
            reeks = (staat.get("geschiedenis") or {}).get("laagste_cel_v") or []
            achter_elkaar = 0
            for waarde in reversed(reeks):
                if waarde < CELSPANNING_AANDACHT_V:
                    achter_elkaar += 1
                else:
                    break
            dagen = max(dagen, achter_elkaar)
        uit["dagen_onder_grens"] = dagen

        if laagste < CELSPANNING_KRITIEK_V:
            uit["oordeel"] = "kritiek"
            uit["advies"] = (
                f"Module {module} staat op {laagste:.2f} V. Onder "
                f"{CELSPANNING_KRITIEK_V:.2f} V grijpt de BMS in op deze "
                "ene cel terwijl de rest nog ruimte heeft. "
                + (
                    # v5.157.0: de sturing doet het nu zelf.
                    "Het EMS laadt in het goedkoopste kwartier van de "
                    f"komende {CELSPANNING_VENSTER_UREN} uur "
                    f"{CELBESCHERMING_BUFFER_KWH:.1f} kWh bij en ontlaadt tot "
                    "dan niet verder."
                    if CELBESCHERMING_AAN and laagste < CELBESCHERMING_START_V
                    else "Het EMS laadt pas zelf bij onder "
                    f"{CELBESCHERMING_START_V:.2f} V."
                )
            )
        elif laagste < CELSPANNING_AANDACHT_V:
            uit["oordeel"] = "aandacht"
            uit["advies"] = (
                f"Module {module} staat op {laagste:.2f} V, onder de "
                f"grens van {CELSPANNING_AANDACHT_V:.2f} V. Niet "
                "dringend - LiFePO4 heeft geen last van laag staan - maar "
                "deze cel raakt de afschakelspanning eerder dan de rest."
            )
        else:
            uit["oordeel"] = "ruim"
            uit["advies"] = (
                f"De laagste cel staat op {laagste:.2f} V, ruim boven de "
                f"grens van {CELSPANNING_AANDACHT_V:.2f} V."
            )

        uit.update(self._celspanning_bijlaadkosten())
        return uit

    def _celspanning_bijlaadkosten(self) -> dict:
        """Wat zou bijladen kosten, en wanneer is het het goedkoopst?

        Een gezondheidsgrens mag geen aankoop afdwingen op het moment dat
        hij aanslaat - dat is bijna altijd een duur kwartier. De juiste
        vorm is een randvoorwaarde met een VENSTER: koop het goedkoopste
        kwartier binnen de komende uren.
        """
        entries = self._get_forecast_entries()
        if not entries:
            return {}
        nu = dt_util.now()
        venster = [
            (start, prijs / PRICE_SCALE_FACTOR)
            for start, _einde, prijs in entries
            if nu <= start <= nu + timedelta(hours=CELSPANNING_VENSTER_UREN)
        ]
        if not venster:
            return {}
        moment, prijs = min(venster, key=lambda x: x[1])
        slijtage = (
            (self.get_wear_cost_overview() or {}).get("slijtage_ct_per_kwh")
            or 0.0
        ) / 100
        return {
            "goedkoopste_moment": moment.isoformat(),
            "goedkoopste_prijs_ct": round(prijs * 100, 1),
            "kosten_per_kwh_ct": round((prijs + slijtage) * 100, 1),
            "kosten_toelichting": (
                f"Eén kWh bijladen kost daar {(prijs + slijtage) * 100:.1f} "
                f"ct inclusief {slijtage * 100:.1f} ct slijtage. Wachten op "
                "dat kwartier in plaats van nu kopen is het verschil tussen "
                "een randvoorwaarde en een dure ingreep."
            ),
        }

    #: v5.117.0: wanneer de accu het laatst vol was (ISO, bewaard) en de
    #: grootste celspreiding in het vlakke midden sinds die keer (bewaard).
    balanceer_laatst_vol: str | None = None
    balanceer_max_delta_v: float | None = None

    def _volg_balanceren(self, now: datetime) -> None:
        """Houdt bij wanneer de accu vol was en hoe ver de cellen uiteenlopen (v5.117.0)."""
        soc = self.accustand_procent()
        if soc is not None and soc >= BALANCEER_VOL_PERCENT:
            self.balanceer_laatst_vol = now.isoformat()
            self.balanceer_max_delta_v = None
            return
        if self.balanceer_laatst_vol is None:
            self.balanceer_laatst_vol = self._balanceer_laatst_vol_uit_dagrapport(now)
        for m in self.battery_module_live or []:
            delta, msoc = m.get("cel_delta_v"), m.get("soc_percent")
            if delta is None or msoc is None:
                continue
            # Alleen in het vlakke midden zegt de spreiding iets over balans;
            # onderin en bovenin is ze bij LFP vanzelf groot.
            if not (BATTERY_MODULE_FLAT_SOC_MIN_PERCENT <= msoc <= BATTERY_MODULE_FLAT_SOC_MAX_PERCENT):
                continue
            if self.balanceer_max_delta_v is None or delta > self.balanceer_max_delta_v:
                self.balanceer_max_delta_v = round(delta, 3)

    def _read_battery_modules(self) -> list[dict]:
        """Leest per accumodule de beschikbare metingen (v0.63.123).

        De volgorde van de geconfigureerde lijsten bepaalt het
        modulenummer: de eerste entiteit in elke lijst hoort bij module
        1. Lijsten mogen van verschillende lengte zijn (bijv. wel
        celspanningen maar geen vermogen per module); ontbrekende
        metingen worden None.

        Levert altijd één dict per module op, ook als een enkele meting
        wegvalt - een tijdelijk onbereikbare sensor mag niet de hele
        module uit de weergave laten verdwijnen.
        """
        max_v = self.config.get(CONF_BATTERY_MODULE_CELL_VOLTAGE_MAX_SENSORS) or []
        min_v = self.config.get(CONF_BATTERY_MODULE_CELL_VOLTAGE_MIN_SENSORS) or []
        temps = self.config.get(CONF_BATTERY_MODULE_TEMPERATURE_SENSORS) or []
        socs = self.config.get(CONF_BATTERY_MODULE_SOC_SENSORS) or []
        powers = self.config.get(CONF_BATTERY_MODULE_POWER_SENSORS) or []

        aantal = max(len(max_v), len(min_v), len(temps), len(socs), len(powers))
        modules = []
        for index in range(aantal):
            # v4.10: `index` gebonden aan de iteratie. Zonder de
            # standaardwaarde leest `lees` de variabele bij AANROEP, niet
            # bij definitie - hier viel dat goed uit, maar zodra de
            # aanroep verplaatst of uitgesteld wordt, lezen alle modules
            # de laatste index.
            def lees(lijst, index=index):
                if index >= len(lijst):
                    return None
                return self._read_sensor_float(lijst[index])

            cel_max = lees(max_v)
            cel_min = lees(min_v)
            delta_v = None
            if cel_max is not None and cel_min is not None:
                delta_v = round(cel_max - cel_min, 4)
            # v5.35: welke module dit is, als de sensor bij een apparaat hoort.
            eerste = next(
                (
                    lijst[index]
                    for lijst in (max_v, min_v, socs, powers, temps)
                    if index < len(lijst) and lijst[index]
                ),
                None,
            )
            modules.append(
                {
                    "module": index + 1,
                    "naam": self.apparaatnaam_van(eerste),
                    # v5.68.4: de fabrieksnaam ("AB3000 00996"), ook als het
                    # apparaat een eigen naam kreeg ("Accu module 1") - zo
                    # herkent het EMS een vervangen module.
                    "apparaat_id": self.apparaatnaam_van(eerste, eigen_naam=False),
                    "cel_max_v": cel_max,
                    "cel_min_v": cel_min,
                    "cel_delta_v": delta_v,
                    "temperatuur_c": lees(temps),
                    "soc_percent": lees(socs),
                    "vermogen_w": lees(powers),
                }
            )
        return modules

    @staticmethod
    def _deviation_from_peers(waarden: list, index: int) -> float | None:
        """Afwijking van één module t.o.v. het gemiddelde van de ANDERE
        modules (v0.63.123).

        Bewust t.o.v. de andere modules en niet t.o.v. het gemiddelde
        inclusief zichzelf: bij drie modules trekt een uitschieter het
        gemiddelde waar hij zelf in zit met zich mee, waardoor zijn
        eigen afwijking structureel wordt onderschat (met n modules
        wordt de afwijking met factor (n-1)/n afgezwakt). Uitsluiten van
        zichzelf maakt de maat scherp en onafhankelijk van het aantal
        modules.

        Deze differentiële vergelijking is het hart van de
        modulebewaking: alle modules staan onder identieke
        omstandigheden (zelfde SoC, zelfde omgevingstemperatuur, zelfde
        belasting), dus alles wat ze gemeenschappelijk hebben valt weg
        en wat overblijft is een eigenschap van díe module. Dat maakt
        het ook ongevoelig voor de sterke SoC-afhankelijkheid van het
        celspanningsverschil bij LFP.
        """
        eigen = waarden[index]
        if eigen is None:
            return None
        anderen = [
            w for i, w in enumerate(waarden) if i != index and w is not None
        ]
        if not anderen:
            return None
        return eigen - (sum(anderen) / len(anderen))

    def _meet_kalibratiecapaciteit(
        self, now: datetime, soc_percent: float | None
    ) -> None:
        """Telt op wat er tijdens een kalibratie de accu in gaat
        (v3.29.0).

        Gevonden bij de doorlichting van 19 augustus: de proefstand-
        kandidaat "Accugezondheid over de tijd" meldde "8,64 kWh nu,
        +0,00 kWh sinds 11 augustus" en zal dat altijd blijven melden.
        Die 8,64 komt uit `sensor.zendure_manager_total_kwh` - een
        TYPEPLAATJE. Dat getal verandert nooit, dus die kandidaat kan
        per definitie geen veroudering vinden.

        Een kalibratie is wél een meting: van 5% naar 100% in één keer,
        zonder ontladen ertussen. Wat er dan ingaat, gedeeld door het
        doorlopen deel van de schaal, is de werkelijke capaciteit.

        Er wordt niets op gestuurd. Dit legt alleen vast wat er te meten
        viel, zodat een tweede kalibratie over een jaar iets heeft om
        mee te vergelijken.
        """
        if not self.kalibratie:
            self.kalibratie_meting = None
            return

        accu_w = self._read_corrected_battery_power()
        meting = self.kalibratie_meting
        if meting is None:
            if soc_percent is None:
                return
            self.kalibratie_meting = {
                "begin_soc": soc_percent,
                "begin": now.isoformat(),
                "kwh_in": 0.0,
                "laatste": now.isoformat(),
            }
            return

        # v3.33.1: als tekst bewaren, zodat de meting een herstart
        # overleeft.
        #
        # Gemeten bij de kalibratie van 19 augustus: er kwam geen
        # capaciteit uit, omdat de herstart voor v3.31.0 de lopende
        # meting op nul zette. Hij begon opnieuw bij 71% en had 70% van
        # de schaal nodig. Een kalibratie duurt uren en wordt zelden
        # gedaan - dan mag één herstart hem niet kosten.
        vorige = meting.get("laatste")
        if isinstance(vorige, str):
            try:
                vorige = datetime.fromisoformat(vorige)
            except ValueError:
                vorige = None
        meting["laatste"] = now.isoformat()
        if accu_w is None or vorige is None:
            return
        uren = (now - vorige).total_seconds() / 3600
        if uren <= 0 or uren > 0.5:
            # Na een herstart of een gat valt er niets af te leiden.
            return
        if accu_w > 0:
            meting["kwh_in"] += accu_w / 1000 * uren

        if soc_percent is None:
            return
        meting["eind_soc"] = soc_percent
        deel = (soc_percent - meting["begin_soc"]) / 100
        if deel >= KALIBRATIE_MIN_SCHAALDEEL and meting["kwh_in"] > 0:
            meting["gemeten_capaciteit_kwh"] = round(
                meting["kwh_in"] / deel, 2
            )

    def _kalibratie_naar_trend(self, now: datetime) -> None:
        """Zet een geldige kalibratiemeting in de capaciteitstrend
        (v3.99.3).

        v3.29.0 meet tijdens een kalibratie hoeveel kWh er in gaat en
        over welk deel van de schaal. Die meting landde in
        `kalibratie_momentopname` en nergens anders; de trend kreeg elke
        dag de nominale sensor. De bron bestond, de verbinding niet.

        Wat er in gaat is meer dan wat er in blijft. De correctie is de
        wortel van het geleerde rondgangsrendement - de AANNAME dat laden
        en ontladen elk de helft van het verlies dragen. Staat erbij.
        """
        meting = self.kalibratie_meting or {}
        gemeten = meting.get("gemeten_capaciteit_kwh")
        if not gemeten:
            return
        sleutel = f"{meting.get('begin_soc')}-{meting.get('eind_soc')}-{meting.get('kwh_in')}"
        reeks = self.capacity_trend_history or []
        if any(r.get("kalibratie_sleutel") == sleutel for r in reeks):
            return
        rendement = (self.learned_battery_efficiency_percent or 90.0) / 100
        laadrendement = rendement ** 0.5
        reeks.append(
            {
                "datum": now.date().isoformat(),
                "capaciteit_kwh": round(gemeten * laadrendement, 2),
                "doorzet_kwh": None,
                "bron": "kalibratie",
                # v5.97.1: bij welke opstelling deze meting hoort.
                "nominaal_kwh": self._read_sensor_float(
                    self.config.get(CONF_BATTERY_TOTAL_CAPACITY_SENSOR)
                ),
                "kalibratie_sleutel": sleutel,
                "begin_soc": meting.get("begin_soc"),
                "eind_soc": meting.get("eind_soc"),
                "kwh_in": meting.get("kwh_in"),
                "laadrendement_aanname": round(laadrendement, 3),
            }
        )
        self.capacity_trend_history = reeks[-CAPACITY_TREND_HISTORY_DAYS:]
        self.schedule_persisted_state_save()

    def _leg_kalibratie_vast(
        self, now: datetime, soc_percent: float | None
    ) -> None:
        """Legt de celspreiding vast zodra de accu vol is (v3.27.0).

        Waarom bovenin: daar balanceert de BMS. Module 1 stond op 19
        augustus op 2,72 tegen 3,18 V - een verschil van 0,46 bij 12%
        laadstand - terwijl module 2 en 3 vlak stonden. Zakt dat
        verschil op vol mee naar nul, dan was het een balanceer-
        achterstand. Blijft het staan, dan is het een zwakke cel, en dan
        is dit de meting om aan Zendure voor te leggen.

        Eén meting per kalibratie: de eerste op vol. Daarna zakt de
        spanning weer zodra er ontladen wordt, en dan zegt het getal
        niets meer.
        """
        if not self.kalibratie or self.kalibratie_momentopname is not None:
            return
        if soc_percent is None or soc_percent < KALIBRATIE_VOL_PERCENT:
            return

        modules = self.battery_module_live or []
        if not modules:
            return

        meting = self.kalibratie_meting or {}
        self._kalibratie_naar_trend(now)
        self.kalibratie_momentopname = {
            "moment": now.isoformat(),
            "soc_percent": soc_percent,
            "modules": [dict(m) for m in modules],
            # v3.29.0: de werkelijk gemeten capaciteit, als de kalibratie
            # genoeg van de schaal heeft doorlopen.
            "begin_soc_percent": meting.get("begin_soc"),
            "geladen_kwh": (
                round(meting["kwh_in"], 2) if meting.get("kwh_in") else None
            ),
            "gemeten_capaciteit_kwh": meting.get("gemeten_capaciteit_kwh"),
            "typeplaatje_kwh": self._read_sensor_float(
                self.config.get(CONF_BATTERY_TOTAL_CAPACITY_SENSOR)
            ),
        }
        self._meld_kalibratie_vol(soc_percent, modules)

    def _meld_kalibratie_vol(self, soc_percent: float, modules: list) -> None:
        """Meldt dat de kalibratie klaar is (v3.27.1).

        Gevraagd: "melding wanneer accu in kalibratie modus 100%
        bereikt, indien mogelijk kritisch."

        Kritiek is hier de juiste soort. Niet omdat er iets mis is, maar
        omdat er iets moet GEBEUREN: de kalibratiestand uit en de
        ondergrens in de Zendure-app terug. Blijft de melding in de
        wachtrij hangen tot de volgende ochtend, dan staat de sturing
        uren onnodig stil.

        De celspreiding gaat mee in het bericht. Dat is de reden dat
        deze kalibratie gedraaid wordt, en op de telefoon is het meteen
        af te lezen zonder de export erbij te halen.
        """
        regels = []
        for m in sorted(modules, key=lambda x: x.get("module") or 0):
            delta = m.get("cel_delta_v")
            if delta is None:
                continue
            regels.append(
                f"module {m.get('module')}: {delta:.3f} V "
                f"({m.get('cel_min_v')}-{m.get('cel_max_v')})"
            )
        spreiding = "; ".join(regels) or "geen modulegegevens"

        self._dispatch_notification(
            notify_service=self.config.get(CONF_APPLIANCE_NOTIFY_SERVICE),
            title="🔋 Kalibratie klaar - accu is vol",
            message=(
                f"De accu staat op {soc_percent:.0f}%. Het EMS houdt hem nog "
                f"{KALIBRATIE_HOUD_MIN} min bovenin om te balanceren en zet daarna "
                f"zelf de kalibratiestand uit.\n\n"
                f"Celspreiding bovenin: {spreiding}."
            ),
            notification_id="ems_kalibratie_vol",
            kind="kalibratie_vol",
        )

    def _update_battery_module_health(self, now: datetime) -> None:
        """Verzamelt per module de live metingen en de afwijking t.o.v.
        de andere modules, en rondt aan het einde van de dag een
        mediaan-dagwaarde af per grootheid (v0.63.123).

        Mediaan en niet gemiddelde, consistent met de rest van dit
        project: één laadpiek of een moment met direct zonlicht op één
        module mag een dagwaarde niet verslepen.
        """
        # v5.31.1: een CUSUM die met andere parameters is opgebouwd, eerst
        # opnieuw berekenen - anders blijft een oude valse drift staan.
        self._herijk_module_cusums()
        # v5.172.0 (punt 4): de effectieve ondergrens, ook zonder moduledata.
        # v5.186.0 (B28): veilig falen (de min-SoC), en de vlag eraf als het lukt.
        self._bewaak_stap("ondergrens", lambda: self._volg_ondergrens(now))
        modules = self._read_battery_modules()
        if not modules:
            self.battery_module_live = []
            # v5.72: zonder moduledata geen correctie.
            self._module_leeg = None
            return

        deltas = [m["cel_delta_v"] for m in modules]
        temps = [m["temperatuur_c"] for m in modules]
        socs = [m["soc_percent"] for m in modules]
        powers = [m["vermogen_w"] for m in modules]

        for index, module in enumerate(modules):
            module["cel_delta_afwijking_v"] = self._deviation_from_peers(deltas, index)
            module["temperatuur_afwijking_c"] = self._deviation_from_peers(temps, index)
            module["soc_afwijking_percent"] = self._deviation_from_peers(socs, index)
            module["vermogen_afwijking_w"] = self._deviation_from_peers(powers, index)
        self.battery_module_live = modules
        # v5.72 (L-EMS-014): een module die bijna leeg is.
        # v5.186.0 (B28): veilig falen (geen correctie), vlag eraf als het lukt.
        if not self._bewaak_stap("module_leeg", lambda: self._volg_module_leeg(now)):
            self._module_leeg = None
        self._onthoud_hoogste_capaciteit()

        day_key = now.date()
        if self._battery_module_day_key is None:
            self._battery_module_day_key = day_key
        elif day_key != self._battery_module_day_key:
            self._finalize_battery_module_day()
            self._battery_module_day_key = day_key

        geldige_socs = [s for s in socs if s is not None]
        bucket = None
        if geldige_socs:
            gemiddelde_soc = sum(geldige_socs) / len(geldige_socs)
            bucket = str(
                int(gemiddelde_soc // BATTERY_MODULE_SOC_BUCKET_SIZE_PERCENT)
                * BATTERY_MODULE_SOC_BUCKET_SIZE_PERCENT
            )

        for module in modules:
            sleutel = str(module["module"])
            # v5.68.1: een vervangen module (andere apparaatnaam, bv. een
            # nieuwe AB3000 voor 00996) begint met een schone lei - de
            # geschiedenis en de CUSUM van de oude accu horen er niet bij.
            identiteit = module.get("apparaat_id") or module.get("naam")
            vorige = (self.battery_module_health.get(sleutel) or {}).get("apparaat")
            # (v5.68.1-v5.68.3 bewaarden de eigen naam; die is geen vervanging.)
            if identiteit and vorige and vorige not in (identiteit, module.get("naam")):
                self.battery_module_health.pop(sleutel, None)
            staat = self.battery_module_health.setdefault(
                sleutel,
                {
                    "dag_metingen": {},
                    "geschiedenis": {},
                    "cusum": {},
                    "soc_buckets": {},
                    "waarschuwingen": [],
                },
            )
            if identiteit:
                staat["apparaat"] = identiteit
                staat["naam"] = module.get("naam")
            metingen = staat["dag_metingen"]
            for veld, waarde in (
                ("cel_delta_afwijking_v", module["cel_delta_afwijking_v"]),
                ("temperatuur_afwijking_c", module["temperatuur_afwijking_c"]),
                ("soc_afwijking_percent", module["soc_afwijking_percent"]),
                ("cel_delta_v", module["cel_delta_v"]),
                ("temperatuur_c", module["temperatuur_c"]),
            ):
                if waarde is not None:
                    metingen.setdefault(veld, []).append(waarde)

            # v3.52.0: de LAAGSTE celspanning van de dag.
            #
            # Gevraagd: "Kan de integratie zelf beoordelen of bijladen
            # noodzakelijk is? In de winter moet hier wel rekening mee
            # worden gehouden."
            #
            # De laadstand zegt daar weinig over. LiFePO4 heeft een
            # vlakke spanningskromme, dus onderin is 6% en 12% nauwelijks
            # te onderscheiden - en lang laag staan is bij LFP niet
            # schadelijk, anders dan bij de accu's in telefoons.
            #
            # Wat wél telt is dat één cel de afschakelspanning raakt
            # terwijl de rest nog ruimte heeft. Gemeten op 27 augustus:
            #
            #     module 1  laagste cel 3,08 V
            #     module 2  3,21     module 3  3,21
            #
            # De pakketspanning ziet er dan gemiddeld prima uit terwijl
            # één cel al bijna leeg is, en de BMS grijpt in op die ene.
            #
            # Let op: dit is een MINIMUM, geen mediaan. De dagelijkse
            # geschiedenis vat elk ander veld samen met de mediaan, en
            # dat is hier precies verkeerd - een dieptepunt van een
            # kwartier verdwijnt dan in het gemiddelde van een etmaal.
            if module.get("cel_min_v") is not None:
                staat["laagste_cel_vandaag_v"] = min(
                    staat.get("laagste_cel_vandaag_v", module["cel_min_v"]),
                    module["cel_min_v"],
                )

            # Absolute celdelta per SoC-bucket, puur ter referentie: bij
            # LFP hoort de delta aan de uiteinden hoger te liggen, dus
            # zonder die opsplitsing is een absolute waarde niet met
            # zichzelf over de tijd te vergelijken.
            if bucket is not None and module["cel_delta_v"] is not None:
                buckets = staat["soc_buckets"].setdefault(bucket, [])
                buckets.append(module["cel_delta_v"])
                staat["soc_buckets"][bucket] = buckets[-200:]

        self._evaluate_battery_module_warnings(modules)
        self._meld_lage_celspanning()

    def _finalize_battery_module_day(self) -> None:
        """Sluit de dag af: mediaan per grootheid de geschiedenis in, en
        de CUSUM-drift bijwerken (v0.63.123)."""
        for staat in self.battery_module_health.values():
            metingen = staat.get("dag_metingen", {})
            for veld, waarden in metingen.items():
                if len(waarden) < BATTERY_MODULE_MIN_SAMPLES_PER_DAY:
                    continue
                mediaan = statistics.median(waarden)
                geschiedenis = staat["geschiedenis"].setdefault(veld, [])
                geschiedenis.append(round(mediaan, 4))
                staat["geschiedenis"][veld] = geschiedenis[
                    -BATTERY_MODULE_HISTORY_DAYS:
                ]
                self._update_battery_module_cusum(staat, veld, mediaan)
            # v3.52.0: het dagminimum apart wegschrijven - de mediaan
            # hierboven zou het dieptepunt juist wegmiddelen.
            laagste = staat.pop("laagste_cel_vandaag_v", None)
            # Dezelfde eis als de andere velden: een dag met te weinig
            # metingen telt niet mee.
            #
            # Gevangen door de bestaande toets: mijn eerste versie
            # schreef het minimum weg ongeacht het aantal metingen, en
            # dan zou één uitlezing na een herstart als volwaardige dag
            # in de geschiedenis komen.
            genoeg = any(
                len(w) >= BATTERY_MODULE_MIN_SAMPLES_PER_DAY
                for w in (staat.get("dag_metingen") or {}).values()
            )
            if laagste is not None and genoeg:
                reeks = staat["geschiedenis"].setdefault("laagste_cel_v", [])
                reeks.append(round(laagste, 3))
                staat["geschiedenis"]["laagste_cel_v"] = reeks[
                    -BATTERY_MODULE_HISTORY_DAYS:
                ]

            staat["dag_metingen"] = {}

    @staticmethod
    def _battery_module_cusum_parameters(veld: str) -> tuple[float, float] | None:
        if veld == "cel_delta_afwijking_v":
            return BATTERY_MODULE_CUSUM_SLACK_V, BATTERY_MODULE_CUSUM_THRESHOLD_V
        if veld == "temperatuur_afwijking_c":
            return BATTERY_MODULE_CUSUM_SLACK_C, BATTERY_MODULE_CUSUM_THRESHOLD_C
        if veld == "soc_afwijking_percent":
            return (
                BATTERY_MODULE_CUSUM_SLACK_PERCENT,
                BATTERY_MODULE_CUSUM_THRESHOLD_PERCENT,
            )
        return None

    def _herijk_module_cusums(self) -> None:
        """Bouw een module-CUSUM opnieuw op als de parameters veranderden
        (v5.31.1).

        De speling en drempel worden bij elke CUSUM bewaard. Wijken die af
        van de huidige, dan wordt de hele dagelijkse geschiedenis met de
        nieuwe parameters opnieuw doorgerekend, dag voor dag zoals hij
        destijds binnenkwam. Zo verdwijnt een valse drift meteen, en blijft
        een echte drift staan.
        """
        # Een CUSUM van vóór v5.31.1 draagt geen parameters; die is
        # opgebouwd met de waarden van toen. Alleen de laadstand is
        # veranderd - de andere velden blijven zoals ze zijn.
        vroeger = {"soc_afwijking_percent": [0.5, 5.0]}
        for staat in (self.battery_module_health or {}).values():
            for veld, cusum in list((staat.get("cusum") or {}).items()):
                parameters = self._battery_module_cusum_parameters(veld)
                if parameters is None:
                    continue
                opgebouwd = cusum.get("parameters") or vroeger.get(veld, list(parameters))
                if list(opgebouwd) == list(parameters):
                    cusum["parameters"] = list(parameters)
                    continue
                reeks = list((staat.get("geschiedenis") or {}).get(veld) or [])
                staat["cusum"].pop(veld, None)
                for dag in range(len(reeks)):
                    self._update_battery_module_cusum(
                        staat, veld, reeks[dag], geschiedenis=reeks[: dag + 1]
                    )
                staat["cusum"].setdefault(
                    veld,
                    {"accumulator": 0.0, "referentie": None, "drift": False, "streak": 0},
                )["parameters"] = list(parameters)

    def _update_battery_module_cusum(
        self,
        staat: dict,
        veld: str,
        dagwaarde: float,
        geschiedenis: list | None = None,
    ) -> None:
        """Klassieke eenzijdige CUSUM op de dagelijkse afwijking
        (v0.63.123).

        Alleen op de AFWIJKINGS-grootheden, niet op de absolute waarden:
        die laatste hangen sterk van SoC en seizoen af en zouden een
        stroom van valse alarmen geven. Alleen positieve drift telt -
        een module die het juist béter doet dan de rest is geen
        probleem.
        """
        parameters = self._battery_module_cusum_parameters(veld)
        if parameters is None:
            return
        slack, drempel = parameters

        if geschiedenis is None:
            geschiedenis = staat["geschiedenis"].get(veld, [])
        if len(geschiedenis) < CUSUM_MIN_HISTORY_FOR_REFERENCE:
            return
        if len(geschiedenis) > CUSUM_REFERENCE_EXCLUDE_RECENT_DAYS:
            referentie_reeks = geschiedenis[:-CUSUM_REFERENCE_EXCLUDE_RECENT_DAYS]
        else:
            referentie_reeks = geschiedenis
        if not referentie_reeks:
            return
        referentie = statistics.median(referentie_reeks)

        cusum = staat["cusum"].setdefault(
            veld,
            {"accumulator": 0.0, "referentie": None, "drift": False, "streak": 0},
        )
        cusum["referentie"] = round(referentie, 4)
        cusum["parameters"] = [slack, drempel]

        bijdrage = (dagwaarde - referentie) - slack
        cusum["accumulator"] = max(0.0, cusum["accumulator"] + max(0.0, bijdrage))

        if dagwaarde <= referentie:
            cusum["streak"] = cusum.get("streak", 0) + 1
        else:
            cusum["streak"] = 0
        if cusum["accumulator"] > 0 and cusum["streak"] >= NILM_CUSUM_RESET_STREAK_DAYS:
            cusum["accumulator"] = 0.0
            cusum["drift"] = False

        if cusum["accumulator"] > drempel:
            cusum["drift"] = True
        cusum["accumulator"] = round(cusum["accumulator"], 4)

    _celbescherming: dict | None = None
    last_celbescherming: dict | None = None

    def celbeschermingsbesluit(self, now: datetime) -> dict:
        """Moet de accu nu bijladen of vasthouden voor een lage cel? (v5.157.0)

        Gemeld 01-11 (akkoord Ruud 02-11): de melding "n Cel steet te lege"
        zei "Nu bijladen, ongeacht de prijs", maar niets in de sturing deed
        dat; de accu bleef de hele nacht op zijn ondergrens met module 4 op
        2,80 V.

        Zakt de laagste cel onder CELBESCHERMING_START_V, dan:
          - tot het goedkoopste kwartier binnen CELSPANNING_VENSTER_UREN:
            "houden" (niet ontladen, de zon mag erin);
          - vanaf dat kwartier: "laden" tot CELBESCHERMING_BUFFER_KWH;
          - daarna "houden" zolang de accu op die buffer staat.
        Boven de buffer geldt de gewone sturing (die mag tot de buffer
        ontladen). Zodra de accu CELBESCHERMING_VRIJ_KWH bevat, vervalt de
        bescherming. Het tijdstip ligt vast bij de start, zodat het niet
        eindeloos naar een nog goedkoper kwartier kan schuiven.

        Geeft {"actie": None | "laden" | "houden", ...}.
        """
        uit: dict = {"actie": None, "aan": CELBESCHERMING_AAN}
        if not CELBESCHERMING_AAN:
            return uit
        beschikbaar = self.beschikbare_energie_kwh()
        if beschikbaar is None:
            uit["reden"] = "accu-inhoud onbekend"
            return uit
        beschikbaar = max(0.0, beschikbaar)
        stand = self._celbescherming
        if stand and beschikbaar >= CELBESCHERMING_VRIJ_KWH:
            self._celbescherming = stand = None
        if not stand:
            oordeel = self.get_celspanning_oordeel()
            laagste = oordeel.get("laagste_cel_v")
            if (
                laagste is None
                or laagste >= CELBESCHERMING_START_V
                or beschikbaar >= CELBESCHERMING_VRIJ_KWH
            ):
                uit["reden"] = "geen cel onder de startgrens"
                return uit
            stand = self._celbescherming = {
                "sinds": now.isoformat(),
                "module": oordeel.get("module"),
                "laagste_cel_v": laagste,
                "laden_om": self._celbescherming_laadmoment(now).isoformat(),
                "buffer_gevuld": False,
            }
        if beschikbaar >= CELBESCHERMING_BUFFER_KWH:
            stand["buffer_gevuld"] = True
        laden_om = dt_util.parse_datetime(stand["laden_om"]) or now
        if not stand["buffer_gevuld"] and now >= laden_om:
            actie = "laden"
        elif beschikbaar <= CELBESCHERMING_BUFFER_KWH or not stand["buffer_gevuld"]:
            actie = "houden"
        else:
            actie = None
        uit.update(
            {
                "actie": actie,
                "beschikbaar_kwh": round(beschikbaar, 3),
                "buffer_kwh": CELBESCHERMING_BUFFER_KWH,
                "vrij_kwh": CELBESCHERMING_VRIJ_KWH,
                **stand,
            }
        )
        return uit

    def _celbescherming_laadmoment(self, now: datetime) -> datetime:
        """Het goedkoopste kwartier binnen het venster, of nu (v5.157.0)."""
        huidig = now.replace(minute=now.minute // 15 * 15, second=0, microsecond=0)
        try:
            venster = [
                (prijs, start)
                for start, _einde, prijs in (self._get_forecast_entries() or [])
                if huidig <= start <= now + timedelta(hours=CELSPANNING_VENSTER_UREN)
            ]
        except Exception:  # noqa: BLE001 - zonder prijzen: nu
            venster = []
        if not venster:
            return huidig
        return min(venster, key=lambda x: (x[0], x[1]))[1]

    async def _celbescherming_als_nodig(self, now: datetime, entries) -> bool:
        """Past `celbeschermingsbesluit` toe. True als de beslissing klaar is."""
        besluit = self.last_celbescherming = self.celbeschermingsbesluit(now)
        if besluit.get("actie") == "laden":
            charge_power = self.instelling(CONF_MANUAL_CHARGE_POWER, DEFAULT_MANUAL_CHARGE_POWER)
            await self._async_apply_manual(charge_power)
            self.last_reason = "celbescherming_laden"
            self.last_charge_power_applied = charge_power
        elif besluit.get("actie") == "houden":
            await self._async_apply_operation(OPTION_SMART_CHARGING)
            self.last_reason = "celbescherming_houden"
            charge_power = None
        else:
            # v5.158.0: geen celbescherming nodig - dan beslist het
            # waardeplan, vóór de oude regels. Hier aangeroepen zodat
            # `_async_update_locked` (ratel) niet groeit.
            return await self._waardeplan_als_nodig(now, entries)
        self._update_financial_tracking(now, entries, self.last_reason, None, charge_power)
        self._update_shortfall_detection(
            now, self.last_reason, self.last_available_kwh, self.last_needed_kwh_to_bridge
        )
        self._finish_decision_tick(now)
        return True

    def _waarom_celbescherming(self, reden: str) -> list[str]:
        """Waarom-regels bij de celbescherming (v5.157.0)."""
        b = self.last_celbescherming or {}
        regels = []
        if b.get("laagste_cel_v") is not None:
            regels.append(
                f"module {b.get('module')} stond op {b['laagste_cel_v']:.2f} V, "
                f"onder {CELBESCHERMING_START_V:.2f} V; onder "
                f"{CELSPANNING_KRITIEK_V:.2f} V grijpt het accubeheer in"
            )
        laden_om = dt_util.parse_datetime(b.get("laden_om") or "")
        if reden == "celbescherming_laden":
            regels.append(
                f"er wordt {CELBESCHERMING_BUFFER_KWH:.1f} kWh bijgeladen, ook als dat niet loont"
            )
        elif laden_om is not None and not b.get("buffer_gevuld"):
            regels.append(f"bijladen in het goedkoopste kwartier: {dt_util.as_local(laden_om):%H:%M}")
        else:
            regels.append(f"de accu houdt een buffer van {CELBESCHERMING_BUFFER_KWH:.1f} kWh vast")
        regels.append(
            f"vanaf {CELBESCHERMING_VRIJ_KWH:.1f} kWh in de accu geldt de gewone sturing weer"
        )
        return regels

    def _meld_lage_celspanning(self) -> None:
        """Meldt een cel die meerdere dagen te laag staat (v3.52.0).

        Pas bij een PATROON, niet bij één bewolkte dag. Eén dag laag is
        bij LiFePO4 geen probleem; meerdere dagen op rij betekent dat de
        zon het niet meer bijhoudt, en dan is dit de winter die eraan
        komt.
        """
        oordeel = self.get_celspanning_oordeel()
        if not oordeel.get("beschikbaar"):
            return
        kritiek = oordeel["oordeel"] == "kritiek"
        patroon = (
            oordeel["oordeel"] == "aandacht"
            and oordeel.get("dagen_onder_grens", 0)
            >= CELSPANNING_DAGEN_VOOR_PATROON
        )
        if not (kritiek or patroon):
            return

        kosten = oordeel.get("kosten_toelichting", "")
        moment = oordeel.get("goedkoopste_moment")
        wanneer = (
            f" Het goedkoopste moment binnen {CELSPANNING_VENSTER_UREN} uur "
            f"is {moment[11:16]}."
            if moment
            else ""
        )
        self._dispatch_notification(
            notify_service=self.config.get(CONF_APPLIANCE_NOTIFY_SERVICE),
            title="🔋 Een cel staat laag",
            message=f"{oordeel['advies']}{wanneer} {kosten}".strip(),
            notification_id="ems_celspanning_laag",
            kind="celspanning_laag",
        )

    def _evaluate_battery_module_warnings(self, modules: list[dict]) -> None:
        """Directe, absolute controles per module (v0.63.123).

        Los van de langzame CUSUM-drift: sommige dingen zijn nú relevant
        en hoeven niet op een trend van weken te wachten.
        """
        deltas = [m["cel_delta_v"] for m in modules if m["cel_delta_v"] is not None]
        temps = [m["temperatuur_c"] for m in modules if m["temperatuur_c"] is not None]
        socs = [m["soc_percent"] for m in modules if m["soc_percent"] is not None]

        for module in modules:
            sleutel = str(module["module"])
            staat = self.battery_module_health.setdefault(
                sleutel,
                {
                    "dag_metingen": {},
                    "geschiedenis": {},
                    "cusum": {},
                    "soc_buckets": {},
                    "waarschuwingen": [],
                },
            )
            waarschuwingen = []
            delta = module["cel_delta_v"]
            if delta is not None:
                melding = self._beoordeel_celspreiding(
                    staat, delta, module.get("soc_percent")
                )
                if melding:
                    waarschuwingen.append(melding)
            temperatuur = module["temperatuur_c"]
            if (
                temperatuur is not None
                and temperatuur >= BATTERY_MODULE_TEMPERATURE_ATTENTION_C
            ):
                waarschuwingen.append(f"celtemperatuur {temperatuur:.1f} °C")
            staat["waarschuwingen"] = waarschuwingen

        self.battery_module_spread = {
            "cel_delta_v": round(max(deltas) - min(deltas), 4) if deltas else None,
            "temperatuur_c": round(max(temps) - min(temps), 1) if temps else None,
            "soc_percent": round(max(socs) - min(socs), 1) if socs else None,
        }

    def _module_drift_velden(
        self, nummer: str, staat: dict, live: dict | None = None
    ) -> list[str]:
        """De velden waarop een module MATERIEEL uit de pas loopt (v5.36).

        De CUSUM kijkt naar de afwijking tegenover de andere modules, en
        die kan statistisch aanhoudend zijn terwijl hij in volt niets
        betekent. Op 7 oktober: AB3000 00996 met een celdelta van 0,01-0,03
        V tegen 0,00 V bij de andere twee - meerdaags gemeld als "loopt uit
        de pas", terwijl een BMS dat verschil gewoon wegbalanceert. Een
        celdelta-drift telt pas vanaf BATTERY_MODULE_CELL_DELTA_MATERIEEL_V.
        """
        velden = [
            veld
            for veld, waarde in (staat.get("cusum") or {}).items()
            if waarde.get("drift")
        ]
        if "cel_delta_afwijking_v" not in velden and "temperatuur_afwijking_c" not in velden:
            return velden
        if live is None:
            live = next(
                (m for m in (self.battery_module_live or []) if str(m.get("module")) == str(nummer)),
                None,
            )
        # v5.192.2: temperatuur alleen als de afwijking er echt toe doet (plek in
        # de stapel, bij de omvormer, geeft een vaste ~1 °C).
        # v5.194.3 (Ruud 08-11: "logisch, er zit er 1 direct onder de
        # omvormer"): een vaste plek-afwijking is geen drift. Telt alleen als
        # de module de laatste dagen (dagmediaan, niet het moment: onder
        # belasting warmt de omvormer extra) minstens de drempel warmer of
        # kouder is dan zijn EIGEN normaal (de CUSUM-referentie).
        if "temperatuur_afwijking_c" in velden:
            reeks = (staat.get("geschiedenis") or {}).get("temperatuur_afwijking_c") or []
            ref = ((staat.get("cusum") or {}).get("temperatuur_afwijking_c") or {}).get("referentie")
            if reeks:
                afw = max(reeks[-3:], key=lambda v: abs(v - (ref or 0.0)))
            else:
                afw = (live or {}).get("temperatuur_afwijking_c")
            if afw is not None and abs(afw - (ref or 0.0)) < BATTERY_MODULE_TEMPERATURE_MATERIEEL_C:
                velden.remove("temperatuur_afwijking_c")
        if "cel_delta_afwijking_v" not in velden:
            return velden
        delta = (live or {}).get("cel_delta_v")
        if delta is None:
            reeks = (staat.get("geschiedenis") or {}).get("cel_delta_v") or []
            delta = max(reeks[-3:]) if reeks else None
        if delta is not None and delta < BATTERY_MODULE_CELL_DELTA_MATERIEEL_V:
            velden.remove("cel_delta_afwijking_v")
        return velden

    def _modules_met_drift(self) -> list[str]:
        """Modules die materieel uit de pas lopen, zonder die waarvoor de
        melding is uitgezet (v5.68.2, op apparaatnaam)."""
        stil = set(self.battery_module_stil or [])
        # v5.186.0: alleen modules die er NU zijn. Melding 04-11 17:12 "Module
        # 4" bij drie modules: een oude sleutel in battery_module_health (van
        # een eerdere modulelijst) bleef meetellen.
        live = {str(m.get("module")) for m in (self.battery_module_live or [])}
        return [
            nummer
            for nummer, gegevens in (self.battery_module_health or {}).items()
            if (not live or nummer in live)
            and gegevens.get("apparaat") not in stil
            and gegevens.get("naam") not in stil
            and self._module_drift_velden(nummer, gegevens)
        ]

    def _module_drift_labels(self, nummers: list[str]) -> list[str]:
        """Naam + apparaat-id per module, zoals de cockpit (v5.186.0)."""
        live = {str(m.get("module")): m for m in (self.battery_module_live or [])}
        labels = []
        for nummer in sorted(nummers, key=lambda n: (len(n), n)):
            m = live.get(nummer) or {}
            staat = (self.battery_module_health or {}).get(nummer) or {}
            naam = m.get("naam") or staat.get("naam")
            apparaat = m.get("apparaat_id") or staat.get("apparaat")
            if naam and apparaat and apparaat != naam:
                labels.append(f"{naam} ({apparaat})")
            else:
                labels.append(naam or apparaat or f"Module {nummer}")
        return labels

    def zet_module_melding(self, naam: str, melden: bool) -> None:
        """De melding per accumodule uit of weer aan (v5.68.2) - zie de
        dienst `accumodule_melding`."""
        stil = [n for n in (self.battery_module_stil or []) if n != naam]
        if not melden and naam:
            stil.append(naam)
        self.battery_module_stil = stil

    def get_battery_module_table(self) -> list[dict]:
        """Overzicht per module voor het dashboard (v0.63.123) - live
        waarden plus de status van de drift-detectie."""
        tabel = []
        for module in self.battery_module_live:
            staat = self.battery_module_health.get(str(module["module"]), {})
            drift = self._module_drift_velden(str(module["module"]), staat, module)
            tabel.append(
                {
                    **module,
                    "waarschuwingen": staat.get("waarschuwingen", []),
                    "drift_op": drift,
                    # v5.68.2: melding uitgezet voor deze module.
                    "melding_uit": bool(
                        {module.get("naam"), module.get("apparaat_id")} & set(self.battery_module_stil or [])
                    ),
                    # v5.35: "1 (AB3000 00996)" - welke module het is.
                    "label": (
                        f"{module['module']} ({module['naam']})"
                        if module.get("naam")
                        else module["module"]
                    ),
                    "dagen_geleerd": max(
                        (len(v) for v in staat.get("geschiedenis", {}).values()),
                        default=0,
                    ),
                }
            )
        return tabel
