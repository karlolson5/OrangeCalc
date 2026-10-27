import numpy as np
from dataclasses import dataclass

@dataclass
class Configuration:
    pulley1_teeth: int
    pulley2_teeth: int
    belt_teeth: int
    c2c: float
    ratio: float
    def __repr__(self) -> str:
        # Custom elegant format for vectors
        return f"P1: {self.pulley1_teeth}, P2: {self.pulley2_teeth}, Belt: {self.belt_teeth}, c2c: {self.c2c:.3f}, ratio: {self.ratio:.2f}"

belt_pitch_mm = 5
belt_pitch_in = belt_pitch_mm / 25.4

pulley1_min_teeth = 12
pulley1_max_teeth = 24
pulley2_min_teeth = 15
pulley2_max_teeth = 30

desired_c2c_min_in = 7.75
desired_c2c_max_in = 8.25

belt_c2c_tolerance_tight_in = 0.003
belt_c2c_tolerance_loose_in = 0.01

belt_tooth_count_min = 35
belt_tooth_count_max = 200
belt_tooth_count_spacing = 5
belt_allowable_tooth_counts = range(belt_tooth_count_min, belt_tooth_count_max, belt_tooth_count_spacing)

must_include_ratio_below = 0.8
must_include_ratio_above = 2

def calculate_pitch_diameter_mm(teeth):
    return teeth * belt_pitch_mm / np.pi

def calculate_belt_length_mm(teeth):
    return teeth * belt_pitch_mm

def calculate_c2c_mm(belt_teeth, pulley1_teeth, pulley2_teeth):
    L = calculate_belt_length_mm(belt_teeth)
    d = calculate_pitch_diameter_mm(pulley1_teeth)
    D = calculate_pitch_diameter_mm(pulley2_teeth)
    K = 4 * L - 2 * np.pi * (D + d)
    if K**2 - 32 * (D - d)**2 < 0:
        return -np.inf
    return (K + np.sqrt(K**2 - 32 * (D - d)**2)) / 16

def mm_to_in(L):
    return L / 25.4

def main():
    legal_configurations = []
    for p1t in np.arange(pulley1_min_teeth, pulley1_max_teeth):
        for p2t in np.arange(pulley2_min_teeth, pulley2_max_teeth):
            for bt in belt_allowable_tooth_counts:
                c2c = mm_to_in(calculate_c2c_mm(bt, p1t, p2t))
                if c2c > desired_c2c_min_in and c2c < desired_c2c_max_in:
                    legal_configurations += [Configuration(
                        pulley1_teeth = p1t,
                        pulley2_teeth = p2t,
                        belt_teeth = bt,
                        c2c = c2c,
                        ratio = p2t/p1t)]
    legal_configurations = sorted(legal_configurations, key=lambda c: (c.c2c, c.ratio))
    # print(legal_configurations)
    unique_c2cs = sorted(list(set([c.c2c for c in legal_configurations])))
    for c2c in unique_c2cs:
        group_configurations = [c for c in legal_configurations if c.c2c > c2c - belt_c2c_tolerance_tight_in and c.c2c < c2c + belt_c2c_tolerance_loose_in]
        group_configurations = sorted(group_configurations, key=lambda c: (c.ratio, c.c2c))
        if group_configurations[0].ratio > must_include_ratio_below:
            continue
        if group_configurations[-1].ratio < must_include_ratio_above:
            continue
        print(f"For designed c2c: {c2c:.3f}:")
        for c in group_configurations:
            print(c)
    

if __name__ == "__main__":
    main()