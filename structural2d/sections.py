"""Standard section catalog shared by both workbook builders.

UK open steel sections (Universal Beams / Universal Columns), major-axis
bending, S355/S275 steel with E = 210 GPa. A is in m^2, I in m^4 -- SI
units, consistent with the rest of the sample data (N, m, Pa).

The values are transcribed from standard UK section tables and are
indicative: close enough for scheme design and for this tool's purposes,
but verify against the current SCI "Blue Book" (or manufacturer data)
before relying on them for detailed design. Users can freely add rows to
the Sections sheet in either generated workbook -- the members dropdown
picks up anything in the sheet's name column.
"""
from __future__ import annotations

E_STEEL = 210e9

# (name, E [Pa], A [m^2], I [m^4])  -- I is major-axis
SECTIONS: list[tuple[str, float, float, float]] = [
    # Universal Beams
    ("127x76x13 UB", E_STEEL, 16.5e-4, 473e-8),
    ("152x89x16 UB", E_STEEL, 20.3e-4, 834e-8),
    ("178x102x19 UB", E_STEEL, 24.3e-4, 1356e-8),
    ("203x102x23 UB", E_STEEL, 29.4e-4, 2105e-8),
    ("203x133x25 UB", E_STEEL, 32.0e-4, 2340e-8),
    ("254x102x28 UB", E_STEEL, 36.1e-4, 4005e-8),
    ("254x146x37 UB", E_STEEL, 47.2e-4, 5537e-8),
    ("305x165x40 UB", E_STEEL, 51.3e-4, 8503e-8),
    ("356x171x51 UB", E_STEEL, 64.9e-4, 14140e-8),
    ("406x178x60 UB", E_STEEL, 76.5e-4, 21600e-8),
    ("457x191x82 UB", E_STEEL, 104e-4, 37050e-8),
    ("533x210x92 UB", E_STEEL, 117e-4, 55230e-8),
    ("610x229x113 UB", E_STEEL, 144e-4, 87320e-8),
    ("686x254x140 UB", E_STEEL, 178e-4, 136300e-8),
    ("762x267x173 UB", E_STEEL, 220e-4, 205300e-8),
    # Universal Columns
    ("152x152x23 UC", E_STEEL, 29.2e-4, 1250e-8),
    ("152x152x37 UC", E_STEEL, 47.1e-4, 2210e-8),
    ("203x203x46 UC", E_STEEL, 58.7e-4, 4570e-8),
    ("203x203x60 UC", E_STEEL, 76.4e-4, 6125e-8),
    ("254x254x73 UC", E_STEEL, 93.1e-4, 11410e-8),
    ("254x254x89 UC", E_STEEL, 113e-4, 14270e-8),
    ("305x305x97 UC", E_STEEL, 123e-4, 22250e-8),
    ("305x305x118 UC", E_STEEL, 150e-4, 27670e-8),
]

SECTION_HEADERS = ["name", "E", "A", "I"]


def section_lookup() -> dict[str, tuple[float, float, float]]:
    """{name: (E, A, I)} for resolving a member's section choice."""
    return {name: (E, A, I) for name, E, A, I in SECTIONS}
