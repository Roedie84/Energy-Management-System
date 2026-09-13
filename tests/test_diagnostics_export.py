

# --- v1.29.0: een mislukte export meldt zichzelf ---------------------


def test_a_failing_part_is_registered_as_an_internal_failure():
    """Gemeld: "Dat er een txt wordt gemaakt is een error, ik had daar
    graag een melding van verwacht zoals eerder afgesproken."

    De afscherming ving de fout al netjes op, maar hield hem ook stil:
    het mislukte onderdeel kreeg een {"fout": ...} in de export en
    verder gebeurde er niets.
    """
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()

    kop = bron.index("def _veilig")
    staart = bron[kop : kop + 2000]
    assert "internal_failures" in staart
    assert "pop(" in staart


def test_the_narrative_uses_an_aware_clock():
    """`datetime.now()` geeft een tijd zonder tijdzone; draait er net een
    apparaat, dan rekent het verhaal `nu - starttijd` uit en gooit Python
    "can't subtract offset-naive and offset-aware datetimes"."""
    from pathlib import Path

    import custom_components.energy_management_system as pkg

    bron = (Path(pkg.__file__).parent / "diagnostics.py").read_text()
    code = "\n".join(
        regel for regel in bron.splitlines() if not regel.strip().startswith("#")
    )

    assert "datetime.now()" not in code
    assert "dt_util.now()" in code
