from dataclasses import dataclass
from fractions import Fraction
import math

# ---------------------------------------------------------------------------
# Config (globals are fine for this quick-and-dirty tool)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChainSpec:
    name: str
    pitch_in: float
    sprocket1_allowable_tooth_counts: list[int]
    sprocket2_allowable_tooth_counts: list[int]
    # Even counts only: an odd count needs an offset link.
    link_counts: list[int]


chains = [
    ChainSpec(
        name="#25",
        pitch_in=0.25,
        sprocket1_allowable_tooth_counts=[10, 12, 14, 15, 16, 18, 20, 22, 24],
        sprocket2_allowable_tooth_counts=[15, 18, 20, 24, 28, 30, 36],
        link_counts=list(range(40, 161, 2)),
    ),
    ChainSpec(
        name="#35",
        pitch_in=0.375,
        sprocket1_allowable_tooth_counts=[10, 12, 14, 15, 16, 18, 20],
        sprocket2_allowable_tooth_counts=[15, 18, 20, 24, 28, 30, 36],
        link_counts=list(range(30, 121, 2)),
    ),
]

# True: one slot may be shared by #25 and #35 configs in the same set
# (swap sprockets and chain together). False: sets never mix chain types.
allow_mixed_chain_types = False
allowed_chain_types = ["#25", "#35"]

desired_c2c_min_in = 7.75
desired_c2c_max_in = 8.25

# A slot built at center distance X accepts a config if
#   X - tight <= config c2c <= X + loose
# The config c2c is the zero-slack distance, so chain tolerates slack
# (loose) much better than being stretched (tight).
chain_c2c_tolerance_tight_in = 0.003
chain_c2c_tolerance_loose_in = 0.020

# Minimum chain wrap on the smaller sprocket, degrees. 0 disables the check.
min_wrap_deg = 120

# A set must contain a ratio <= the first and a ratio >= the second.
# With both at 1, any set passes (a 1:1 config satisfies both).
must_include_ratio_below = 1
must_include_ratio_above = 1

num_groups_to_print = 5

_EPS = 1e-9  # float slop for window membership tests


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Configuration:
    chain: str
    sprocket1_teeth: int
    sprocket2_teeth: int
    links: int
    c2c_in: float
    wrap_deg: float

    @property
    def ratio_exact(self) -> Fraction:
        return Fraction(self.sprocket2_teeth, self.sprocket1_teeth)

    @property
    def ratio(self) -> float:
        return self.sprocket2_teeth / self.sprocket1_teeth

    def __str__(self) -> str:
        return (f"Chain: {self.chain}, S1: {self.sprocket1_teeth:2d}, "
                f"S2: {self.sprocket2_teeth:2d}, Links: {self.links:3d}, "
                f"c2c: {self.c2c_in:.3f}, ratio: {self.ratio:.2f}, "
                f"wrap: {self.wrap_deg:.0f}°")


@dataclass(frozen=True)
class ConfigurationGroup:
    configurations: list[Configuration]  # sorted by (ratio, c2c)
    ratio_min: float
    ratio_max: float
    unique_ratio_count: int
    c2c_min_in: float
    c2c_max_in: float
    slot_c2c_min_in: float  # feasible range for the slot center distance X
    slot_c2c_max_in: float
    S1_used: list[int]
    S2_used: list[int]
    links_used: list[int]
    chains_used: list[str]

    @property
    def slot_c2c_mid_in(self) -> float:
        return (self.slot_c2c_min_in + self.slot_c2c_max_in) / 2

    def __str__(self) -> str:
        cfg_lines = "\n".join(f"        {c}" for c in self.configurations)
        return (
            f"Slot c2c:        {self.slot_c2c_mid_in:.3f} "
            f"(feasible {self.slot_c2c_min_in:.3f} - {self.slot_c2c_max_in:.3f})\n"
            f"Configurations:  {len(self.configurations)} "
            f"({self.unique_ratio_count} unique ratios)\n"
            f"Ratio range:     {self.ratio_min:.2f} - {self.ratio_max:.2f}\n"
            f"c2c range:       {self.c2c_min_in:.3f} - {self.c2c_max_in:.3f}\n"
            f"Chains used:     {self.chains_used}\n"
            f"S1 used:         {self.S1_used}\n"
            f"S2 used:         {self.S2_used}\n"
            f"Links used:      {self.links_used}\n"
            f"Configurations:\n{cfg_lines}\n"
        )


# ---------------------------------------------------------------------------
# Geometry. Public interface is inches.
#
# Standard catalog center-distance formula, with L the chain length in pitches
# and C in pitches:
#   L = 2C + (N1 + N2) / 2 + ((N2 - N1) / (2 pi))^2 / C
# Solved for C below. This is the same 2nd-order approximation as the belt
# version. It ignores the polygonal (chordal) action of the sprockets, as
# every catalog formula does; that effect is real but is absorbed by chain
# slack, which is why `loose` is much larger than for a belt.
# ---------------------------------------------------------------------------
def _c2c_pitches(links: int, n1: int, n2: int) -> float | None:
    """Center distance in chain pitches, or None if the chain can't span."""
    free = links - (n1 + n2) / 2
    k = ((n2 - n1) / (2 * math.pi)) ** 2
    disc = free * free - 8 * k
    if free <= 0 or disc < 0:
        return None
    return (free + math.sqrt(disc)) / 4


def _sprocket_pitch_diameter_in(teeth: int, pitch_in: float) -> float:
    return pitch_in / math.sin(math.pi / teeth)


def calculate_c2c_in(chain: ChainSpec, links: int, n1: int, n2: int) -> float | None:
    """Center distance in inches, or None if no valid geometry."""
    c = _c2c_pitches(links, n1, n2)
    return None if c is None else c * chain.pitch_in


def calculate_wrap_deg(chain: ChainSpec, c2c_in: float, n1: int, n2: int) -> float | None:
    """Wrap angle on the smaller sprocket, or None if the sprockets can't clear."""
    d = _sprocket_pitch_diameter_in(min(n1, n2), chain.pitch_in)
    D = _sprocket_pitch_diameter_in(max(n1, n2), chain.pitch_in)
    s = (D - d) / (2 * c2c_in)
    if s >= 1:
        return None
    return math.degrees(math.pi - 2 * math.asin(s))


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
def find_legal_configurations() -> list[Configuration]:
    configs = []
    for chain in [c in chains if c.name in allowed_chain_types]:
        for n1 in chain.sprocket1_allowable_tooth_counts:
            for n2 in chain.sprocket2_allowable_tooth_counts:
                for links in chain.link_counts:
                    c2c = calculate_c2c_in(chain, links, n1, n2)
                    if c2c is None or not desired_c2c_min_in < c2c < desired_c2c_max_in:
                        continue
                    wrap = calculate_wrap_deg(chain, c2c, n1, n2)
                    if wrap is None or wrap < min_wrap_deg:
                        continue
                    configs.append(Configuration(chain.name, n1, n2, links, c2c, wrap))
    configs.sort(key=lambda c: (c.c2c_in, c.ratio))
    return configs


def build_group(members: list[Configuration]) -> ConfigurationGroup:
    members = sorted(members, key=lambda c: (c.ratio, c.c2c_in))
    ratios = [c.ratio for c in members]
    c2cs = [c.c2c_in for c in members]
    c2c_min, c2c_max = min(c2cs), max(c2cs)
    return ConfigurationGroup(
        configurations=members,
        ratio_min=min(ratios),
        ratio_max=max(ratios),
        unique_ratio_count=len({c.ratio_exact for c in members}),
        c2c_min_in=c2c_min,
        c2c_max_in=c2c_max,
        slot_c2c_min_in=c2c_max - chain_c2c_tolerance_loose_in,
        slot_c2c_max_in=c2c_min + chain_c2c_tolerance_tight_in,
        S1_used=sorted({c.sprocket1_teeth for c in members}),
        S2_used=sorted({c.sprocket2_teeth for c in members}),
        links_used=sorted({c.links for c in members}),
        chains_used=sorted({c.chain for c in members}),
    )


def find_maximal_groups(configs: list[Configuration]) -> list[ConfigurationGroup]:
    """Every maximal set of configs that one slot can accommodate.

    configs must be sorted by c2c. All members of a group must have c2c within
    a window of width (tight + loose). Maximal windows can always be taken to
    start at some config's c2c, so we try each one, dedupe identical index
    sets, drop sets that fail the ratio requirement, then drop any set that is
    a subset of another.
    """
    width = chain_c2c_tolerance_tight_in + chain_c2c_tolerance_loose_in

    candidates: set[frozenset[int]] = set()
    for lo_cfg in configs:
        lo = lo_cfg.c2c_in
        candidates.add(frozenset(
            i for i, c in enumerate(configs)
            if lo - _EPS <= c.c2c_in <= lo + width + _EPS
        ))

    def passes_ratio_requirement(idxs: frozenset[int]) -> bool:
        ratios = [configs[i].ratio for i in idxs]
        return (min(ratios) <= must_include_ratio_below
                and max(ratios) >= must_include_ratio_above)

    candidates = [s for s in candidates if passes_ratio_requirement(s)]

    maximal: list[frozenset[int]] = []
    for s in sorted(candidates, key=len, reverse=True):
        if not any(s <= kept for kept in maximal):
            maximal.append(s)

    return [build_group([configs[i] for i in s]) for s in maximal]


def rank_key(g: ConfigurationGroup):
    return (g.unique_ratio_count, len(g.configurations), g.ratio_max / g.ratio_min)


def main():
    configs = find_legal_configurations()
    if allow_mixed_chain_types:
        groups = find_maximal_groups(configs)
    else:
        groups = []
        for chain in chains:
            groups += find_maximal_groups([c for c in configs if c.chain == chain.name])
    groups.sort(key=rank_key, reverse=True)
    for n, g in enumerate(groups[:num_groups_to_print], start=1):
        print(f"==========  Proposed Configuration Set {n}  ==========")
        print(g)


if __name__ == "__main__":
    main()