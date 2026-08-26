"""Structuurscan 9: aanroepen met het juiste aantal argumenten (v3.32.0).

Uit een echte storing voortgekomen. In het gebeurtenislogboek van de
export van 19 augustus staan twee kritieke regels van 18 augustus:

    08:36  't Systeem löp vast
    08:58  't Systeem löp vast
    detail: _koelen_is_goedkoop() missing 1 required positional
            argument: 'buiten_c'

Twee keer een vastgelopen ronde, en de watchdog die hem weer aan de gang
moest trekken. De methode bestond, de variabelen bestonden - alleen werd
hij met één argument te weinig aangeroepen.

De bestaande structuurscans vangen dat niet:

    1. methoden die niet bestaan
    2. variabelen die in die functie niet bestaan
    3. `@staticmethod` die `self` gebruikt
    4. berekend maar nergens gelezen
    5. onveilige SVG-elementen
    6. getters die ruwe SVG teruggeven
    7. schakelaarkaarten met een afwijkend voorvoegsel
    8. beslisredenen zonder eigen onderbouwing

Alle acht kijken naar NAMEN. Deze negende kijkt naar de vorm van de
aanroep, en dat is precies het gat waar die storing doorheen viel.

Let op de decorators: bij een `@staticmethod` hoort `self` er niet bij,
bij een gewone methode wel. Zonder dat onderscheid meldt de scan
tweeënzestig aanroepen die allemaal in orde zijn.
"""
import ast
from pathlib import Path

import pytest

import custom_components.energy_management_system as pkg

BESTANDEN = sorted(Path(pkg.__file__).parent.glob("*.py"))


def _handtekeningen(klasse: ast.ClassDef) -> dict:
    """Per methode: hoeveel argumenten er minimaal en maximaal in mogen."""
    uit = {}
    for knoop in klasse.body:
        if not isinstance(knoop, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        namen = {
            d.id for d in knoop.decorator_list if isinstance(d, ast.Name)
        }
        if "property" in namen:
            continue
        impliciet = 0 if "staticmethod" in namen else 1
        a = knoop.args
        uit[knoop.name] = {
            "min": len(a.args) - impliciet - len(a.defaults),
            "max": len(a.args) - impliciet,
            "los": bool(a.vararg or a.kwarg),
        }
    return uit


def _foute_aanroepen(pad: Path) -> list:
    boom = ast.parse(pad.read_text())
    fouten = []
    for klasse in [n for n in ast.walk(boom) if isinstance(n, ast.ClassDef)]:
        sig = _handtekeningen(klasse)
        for knoop in ast.walk(klasse):
            if not (
                isinstance(knoop, ast.Call)
                and isinstance(knoop.func, ast.Attribute)
                and isinstance(knoop.func.value, ast.Name)
                and knoop.func.value.id == "self"
                and knoop.func.attr in sig
            ):
                continue
            vorm = sig[knoop.func.attr]
            if vorm["los"]:
                continue
            if any(isinstance(a, ast.Starred) for a in knoop.args):
                continue
            if any(k.arg is None for k in knoop.keywords):
                continue
            gegeven = len(knoop.args)
            samen = gegeven + len(knoop.keywords)
            if gegeven > vorm["max"] or samen < vorm["min"]:
                fouten.append(
                    f"{pad.name}:{knoop.lineno} self.{knoop.func.attr}("
                    f"{gegeven} positioneel + {len(knoop.keywords)} sleutel) "
                    f"- verwacht {vorm['min']} tot {vorm['max']}"
                )
    return fouten


@pytest.mark.parametrize("pad", BESTANDEN, ids=lambda p: p.name)
def test_no_call_has_the_wrong_number_of_arguments(pad):
    """Dit is de fout die op 18 augustus twee rondes liet vastlopen."""
    fouten = _foute_aanroepen(pad)

    assert not fouten, "\n".join(fouten)


def test_the_scan_would_have_caught_that_day():
    """Toetsen dat de scan werkelijk vangt waar hij voor gemaakt is - een

    scan die niets vindt in code die klopt, bewijst nog niets.
    """
    code = '''
class Iets:
    def _koelen_is_goedkoop(self, accu_c, buiten_c):
        return accu_c > buiten_c

    def beslis(self):
        return self._koelen_is_goedkoop(30.0)
'''
    pad = Path("/tmp/scan9_voorbeeld.py")
    pad.write_text(code)

    fouten = _foute_aanroepen(pad)

    assert len(fouten) == 1
    assert "_koelen_is_goedkoop" in fouten[0]


def test_a_static_method_is_not_miscounted():
    """Zonder dit onderscheid meldt de scan tweeënzestig aanroepen die

    allemaal in orde zijn.
    """
    code = '''
class Iets:
    @staticmethod
    def _is_onzin(regel):
        return False

    def controleer(self):
        return self._is_onzin({"datum": "2026-08-16"})
'''
    pad = Path("/tmp/scan9_static.py")
    pad.write_text(code)

    assert _foute_aanroepen(pad) == []


def test_defaults_and_keywords_are_allowed():
    code = '''
class Iets:
    def _kort(self, a, b=1, c=2):
        return a

    def gebruik(self):
        self._kort(1)
        self._kort(1, 2)
        self._kort(1, c=9)
'''
    pad = Path("/tmp/scan9_defaults.py")
    pad.write_text(code)

    assert _foute_aanroepen(pad) == []
