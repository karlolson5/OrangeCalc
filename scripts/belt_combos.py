from dataclasses import dataclass
from fractions import Fraction
import math

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MM_PER_IN = 25.4

belt_pitch_mm = 5

pulley1_min_teeth = 12
pulley1_max_teeth = 24
pulley1_allowable_tooth_counts_manual = [12, 14, 15, 16, 17, 18, 20, 22, 24]  # comma-separated; empty = use min/max
pulley2_min_teeth = 15
pulley2_max_teeth = 30
pulley2_allowable_tooth_counts_manual = [15, 18, 20, 24, 26, 28, 30]  # comma-separated; empty = use min/max

belt_tooth_count_min = 35
belt_tooth_count_max = 200
belt_tooth_count_spacing = 5
belt_allowable_tooth_counts_manual = [95, 100, 105]  # comma-separated; empty = use min/max/spacing

desired_c2c_min_in = 7.75
desired_c2c_max_in = 8.25

# A designed center distance X accepts a config if
#   X - tight <= config c2c <= X + loose
belt_c2c_tolerance_tight_in = 0.003
belt_c2c_tolerance_loose_in = 0.01

# A set must contain a ratio <= the first and a ratio >= the second.
# With both at 1, any set passes (a 1:1 config satisfies both).
must_include_ratio_below = 0.8
must_include_ratio_above = 1.9

max_groups_to_suggest = 5

_EPS = 1e-9  # float calculation wiggle room


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Configuration:
    pulley1_teeth: int
    pulley2_teeth: int
    belt_teeth: int
    c2c_in: float

    @property
    def ratio_exact(self) -> Fraction:
        return Fraction(self.pulley2_teeth, self.pulley1_teeth)

    @property
    def ratio(self) -> float:
        return self.pulley2_teeth / self.pulley1_teeth

    def __str__(self) -> str:
        return (f"P1: {self.pulley1_teeth:2d}, P2: {self.pulley2_teeth:2d}, "
                f"Belt: {self.belt_teeth:3d}, c2c: {self.c2c_in:.3f}, "
                f"ratio: {self.ratio:.2f}")


@dataclass(frozen=True)
class ConfigurationGroup:
    configurations: list[Configuration]  # sorted by (ratio, c2c)
    ratio_min: float
    ratio_max: float
    unique_ratio_count: int
    c2c_min_in: float
    c2c_max_in: float
    designed_c2c_min_in: float  # feasible range for the designed center distance X
    designed_c2c_max_in: float
    P1_used: list[int]
    P2_used: list[int]
    belts_used: list[int]

    @property
    def designed_c2c_mid_in(self) -> float:
        return (self.designed_c2c_min_in + self.designed_c2c_max_in) / 2

    def __str__(self) -> str:
        cfg_lines = "\n".join(f"        {c}" for c in self.configurations)
        return (
            f"Designed c2c:    {self.designed_c2c_mid_in:.3f} "
            f"(feasible {self.designed_c2c_min_in:.3f} - {self.designed_c2c_max_in:.3f})\n"
            f"Unique Ratios:   {self.unique_ratio_count} "
            f"({len(self.configurations)} total configurations)\n"
            f"Ratio range:     {self.ratio_min:.2f} - {self.ratio_max:.2f}\n"
            f"c2c range:       {self.c2c_min_in:.3f} - {self.c2c_max_in:.3f}\n"
            f"P1 used:         {self.P1_used}\n"
            f"P2 used:         {self.P2_used}\n"
            f"Belts used:      {self.belts_used}\n"
            f"Configurations:\n{cfg_lines}\n"
        )


# ---------------------------------------------------------------------------
# Geometry. Internals are mm; the only public interface is inches.
#
# Uses the standard 2nd-order approximation
#   L = 2C + pi (D + d) / 2 + (D - d)^2 / (4C)
# Checked against an exact solver: worst error is 0.0003 mm for the belts and
# pulleys above (~1e-5 in at the target c2c) and 0.003 mm for a 35T belt with
# 24T/30T pulleys, versus 0.076 mm tight tolerance. Worst case over all 35T
# belt / pulley combinations here is 0.065 mm. Fine for this use.
# ---------------------------------------------------------------------------
def _pitch_diameter_mm(teeth: int) -> float:
    return teeth * belt_pitch_mm / math.pi


def _c2c_mm(belt_teeth: int, pulley1_teeth: int, pulley2_teeth: int) -> float | None:
    """Center distance in mm, or None if the belt cannot span the pulleys."""
    L = belt_teeth * belt_pitch_mm
    d = _pitch_diameter_mm(pulley1_teeth)
    D = _pitch_diameter_mm(pulley2_teeth)
    K = 4 * L - 2 * math.pi * (D + d)
    disc = K * K - 32 * (D - d) ** 2
    if disc < 0:
        return None
    return (K + math.sqrt(disc)) / 16


def calculate_c2c_in(belt_teeth: int, pulley1_teeth: int, pulley2_teeth: int) -> float | None:
    """Center distance in inches, or None if no valid geometry."""
    c = _c2c_mm(belt_teeth, pulley1_teeth, pulley2_teeth)
    return None if c is None else c / MM_PER_IN

def _pulley1_counts():
    return pulley1_allowable_tooth_counts_manual or range(pulley1_min_teeth, pulley1_max_teeth + 1)

def _pulley2_counts():
    return pulley2_allowable_tooth_counts_manual or range(pulley2_min_teeth, pulley2_max_teeth + 1)

def _belt_counts():
    return belt_allowable_tooth_counts_manual or range(
        belt_tooth_count_min, belt_tooth_count_max + 1, belt_tooth_count_spacing)

# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
def find_legal_configurations() -> list[Configuration]:
    configs = []
    for p1t in _pulley1_counts():
        for p2t in _pulley2_counts():
            for bt in _belt_counts():
                c2c = calculate_c2c_in(bt, p1t, p2t)
                if c2c is not None and desired_c2c_min_in < c2c < desired_c2c_max_in:
                    configs.append(Configuration(p1t, p2t, bt, c2c))
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
        designed_c2c_min_in=c2c_max - belt_c2c_tolerance_loose_in,
        designed_c2c_max_in=c2c_min + belt_c2c_tolerance_tight_in,
        P1_used=sorted({c.pulley1_teeth for c in members}),
        P2_used=sorted({c.pulley2_teeth for c in members}),
        belts_used=sorted({c.belt_teeth for c in members}),
    )


def find_maximal_groups(configs: list[Configuration]) -> list[ConfigurationGroup]:
    """Every maximal set of configs that one designed can accommodate.

    configs must be sorted by c2c. All members of a group must have c2c within
    a window of width (tight + loose). Maximal windows can always be taken to
    start at some config's c2c, so we try each one, dedupe identical index
    sets, drop sets that fail the ratio requirement, then drop any set that is
    a subset of another.
    """
    width = belt_c2c_tolerance_tight_in + belt_c2c_tolerance_loose_in

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
    groups = sorted(find_maximal_groups(configs), key=rank_key, reverse=True)
    for n, g in enumerate(groups[:max_groups_to_suggest], start=1):
        print(f"==========  Proposed Configuration Set {n}  ==========")
        print(g)


if __name__ == "__main__":
    main()