from dataclasses import dataclass
from fractions import Fraction

# ---------------------------------------------------------------------------
# Config (globals are fine for this quick-and-dirty tool)
# ---------------------------------------------------------------------------
diametral_pitch = 20  # teeth per inch of pitch diameter

gear1_allowable_tooth_counts = [12, 14, 15, 16, 18, 20, 24, 30, 36, 40, 48]
gear2_allowable_tooth_counts = [15, 18, 20, 24, 30, 36, 40, 48, 60]

# Desired center distance in DP units, i.e. c2c_in * DP = (N1 + N2) / 2.
# At DP 20 this is 1.5 - 2.0 in.
desired_c2c_min_dp = 30
desired_c2c_max_dp = 40

# A slot built at center distance X accepts a config if
#   X - tight <= config c2c <= X + loose
# These are physical, so they stay in inches. (The loose side is backlash.)
# Spur-gear c2c is quantized in steps of 1 / (2 DP), so unless these exceed
# that, a group is simply "all pairs with the same tooth sum".
c2c_tolerance_tight_in = 0.002
c2c_tolerance_loose_in = 0.005

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
    gear1_teeth: int
    gear2_teeth: int
    c2c_in: float

    @property
    def tooth_sum(self) -> int:
        return self.gear1_teeth + self.gear2_teeth

    @property
    def c2c_dp(self) -> Fraction:
        """Center distance in DP units (c2c_in * DP); exact."""
        return Fraction(self.tooth_sum, 2)

    @property
    def ratio_exact(self) -> Fraction:
        return Fraction(self.gear2_teeth, self.gear1_teeth)

    @property
    def ratio(self) -> float:
        return self.gear2_teeth / self.gear1_teeth

    def __str__(self) -> str:
        return (f"G1: {self.gear1_teeth:2d}, G2: {self.gear2_teeth:2d}, "
                f"c2c: {self.c2c_in:.4f} in ({float(self.c2c_dp):.1f}/DP), "
                f"ratio: {self.ratio:.2f}")


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
    G1_used: list[int]
    G2_used: list[int]

    @property
    def slot_c2c_mid_in(self) -> float:
        return (self.slot_c2c_min_in + self.slot_c2c_max_in) / 2

    def __str__(self) -> str:
        cfg_lines = "\n".join(f"        {c}" for c in self.configurations)
        mid = self.slot_c2c_mid_in
        return (
            f"Slot c2c:        {mid:.4f} in = {mid * diametral_pitch:.3f}/DP "
            f"(feasible {self.slot_c2c_min_in:.4f} - {self.slot_c2c_max_in:.4f} in, "
            f"{self.slot_c2c_min_in * diametral_pitch:.3f} - "
            f"{self.slot_c2c_max_in * diametral_pitch:.3f}/DP)\n"
            f"Configurations:  {len(self.configurations)} "
            f"({self.unique_ratio_count} unique ratios)\n"
            f"Ratio range:     {self.ratio_min:.2f} - {self.ratio_max:.2f}\n"
            f"c2c range:       {self.c2c_min_in:.4f} - {self.c2c_max_in:.4f} in\n"
            f"G1 used:         {self.G1_used}\n"
            f"G2 used:         {self.G2_used}\n"
            f"Configurations:\n{cfg_lines}\n"
        )


# ---------------------------------------------------------------------------
# Geometry: standard spur gears, pitch diameter = N / DP, so
#   c2c = (N1 + N2) / (2 DP)
# ---------------------------------------------------------------------------
def calculate_c2c_in(gear1_teeth: int, gear2_teeth: int) -> float:
    return (gear1_teeth + gear2_teeth) / (2 * diametral_pitch)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
def find_legal_configurations() -> list[Configuration]:
    c2c_min_in = desired_c2c_min_dp / diametral_pitch
    c2c_max_in = desired_c2c_max_dp / diametral_pitch
    configs = []
    for g1 in gear1_allowable_tooth_counts:
        for g2 in gear2_allowable_tooth_counts:
            c2c = calculate_c2c_in(g1, g2)
            if c2c_min_in < c2c < c2c_max_in:
                configs.append(Configuration(g1, g2, c2c))
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
        slot_c2c_min_in=c2c_max - c2c_tolerance_loose_in,
        slot_c2c_max_in=c2c_min + c2c_tolerance_tight_in,
        G1_used=sorted({c.gear1_teeth for c in members}),
        G2_used=sorted({c.gear2_teeth for c in members}),
    )


def find_maximal_groups(configs: list[Configuration]) -> list[ConfigurationGroup]:
    """Every maximal set of configs that one slot can accommodate.

    configs must be sorted by c2c. All members of a group must have c2c within
    a window of width (tight + loose). Maximal windows can always be taken to
    start at some config's c2c, so we try each one, dedupe identical index
    sets, drop sets that fail the ratio requirement, then drop any set that is
    a subset of another.
    """
    width = c2c_tolerance_tight_in + c2c_tolerance_loose_in

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
    for n, g in enumerate(groups[:num_groups_to_print], start=1):
        print(f"==========  Proposed Configuration Set {n}  ==========")
        print(g)


if __name__ == "__main__":
    main()