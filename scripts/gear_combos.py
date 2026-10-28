from dataclasses import dataclass
from fractions import Fraction

# ---------------------------------------------------------------------------
# Config (globals are fine for this quick-and-dirty tool)
# ---------------------------------------------------------------------------
diametral_pitch = 20  # teeth per inch of pitch diameter

gear1_allowable_tooth_counts = [12, 14, 15, 16, 18, 20, 24, 30, 36, 40, 48]
gear2_allowable_tooth_counts = [15, 18, 20, 24, 30, 36, 40, 48, 60]

# Desired center distance in DP units, i.e. c2c_in * DP = (N1 + N2) / 2.
# Inclusive on both ends. At DP 20 this is 1.5 - 2.0 in.
# Only integer DP spacings are used, so N1 + N2 must be even.
desired_c2c_min_dp = 36
desired_c2c_max_dp = 40

# A set must contain a ratio <= the first and a ratio >= the second.
# With both at 1, any set passes (a 1:1 config satisfies both).
must_include_ratio_below = 1
must_include_ratio_above = 1

num_groups_to_print = 5


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
                f"ratio: {self.ratio:.2f}")


@dataclass(frozen=True)
class ConfigurationGroup:
    configurations: list[Configuration]  # sorted by ratio
    ratio_min: float
    ratio_max: float
    unique_ratio_count: int
    c2c_dp: int  # exact designed center distance in DP units
    c2c_in: float
    G1_used: list[int]
    G2_used: list[int]

    def __str__(self) -> str:
        cfg_lines = "\n".join(f"        {c}" for c in self.configurations)
        return (
            f"Designed c2c:    {self.c2c_in:.4f} in = {self.c2c_dp}/DP\n"
            f"Configurations:  {len(self.configurations)} "
            f"({self.unique_ratio_count} unique ratios)\n"
            f"Ratio range:     {self.ratio_min:.2f} - {self.ratio_max:.2f}\n"
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
    configs = []
    for g1 in gear1_allowable_tooth_counts:
        for g2 in gear2_allowable_tooth_counts:
            tooth_sum = g1 + g2
            if tooth_sum % 2:  # c2c must be an integer number of DP
                continue
            if desired_c2c_min_dp <= tooth_sum // 2 <= desired_c2c_max_dp:
                configs.append(Configuration(g1, g2, calculate_c2c_in(g1, g2)))
    configs.sort(key=lambda c: (c.tooth_sum, c.ratio))
    return configs


def build_group(members: list[Configuration]) -> ConfigurationGroup:
    members = sorted(members, key=lambda c: c.ratio)
    ratios = [c.ratio for c in members]
    return ConfigurationGroup(
        configurations=members,
        ratio_min=min(ratios),
        ratio_max=max(ratios),
        unique_ratio_count=len({c.ratio_exact for c in members}),
        c2c_dp=members[0].tooth_sum // 2,
        c2c_in=members[0].c2c_in,
        G1_used=sorted({c.gear1_teeth for c in members}),
        G2_used=sorted({c.gear2_teeth for c in members}),
    )


def find_groups(configs: list[Configuration]) -> list[ConfigurationGroup]:
    """One group per exact center distance (same tooth sum), keeping only
    groups that satisfy the ratio requirement."""
    by_sum: dict[int, list[Configuration]] = {}
    for c in configs:
        by_sum.setdefault(c.tooth_sum, []).append(c)

    groups = []
    for members in by_sum.values():
        ratios = [c.ratio for c in members]
        if (min(ratios) <= must_include_ratio_below
                and max(ratios) >= must_include_ratio_above):
            groups.append(build_group(members))
    return groups


def rank_key(g: ConfigurationGroup):
    return (g.unique_ratio_count, len(g.configurations), g.ratio_max / g.ratio_min)


def main():
    configs = find_legal_configurations()
    groups = sorted(find_groups(configs), key=rank_key, reverse=True)
    for n, g in enumerate(groups[:num_groups_to_print], start=1):
        print(f"==========  Proposed Configuration Set {n}  ==========")
        print(g)


if __name__ == "__main__":
    main()