"""
Starting-point sizing for nozzle / forward-closure retention bolts.

openMotor does NOT model this. These are hand calculations to hand to a materials
engineer, not a final design.

Axial blow-out force = chamber pressure x pressurized bore cross-section.
The bore that carries pressure is the TUBE ID (21.2 mm), not the grain OD -- the
paper/epoxy liner is a thermal barrier, it carries no structural load.

Three failure paths are checked for radial bolts through the tube wall:
  1. bolt shear (steel, across threads -- conservative)
  2. bearing on the aluminium hole (6061-T6)
  3. shear tear-out of the aluminium to the tube end
"""
import math

TUBE_ID = 0.0212          # m, pressurized bore
WALL = 0.0021             # m, 6061-T6 tube wall
BORE_AREA = math.pi / 4 * TUBE_ID ** 2

SAFETY_FACTOR = 4.0

# Steel bolts, ISO grade 8.8: Rm = 800 MPa, ultimate shear ~= 0.6 * Rm
BOLT_SHEAR_STRENGTH = 0.6 * 800e6

# 6061-T6
AL_BEARING_YIELD = 386e6   # Fbry
AL_SHEAR_ULT = 207e6       # Fsu

# Thread minor-diameter areas (shear taken across the threads = worst case)
BOLTS = {
    'M3': {'d': 0.003, 'minor_area': 4.75e-6},
    'M4': {'d': 0.004, 'minor_area': 8.25e-6},
    'M5': {'d': 0.005, 'minor_area': 13.4e-6},
}

# Pressure cases: nominal, credible-fast propellant, and the chamber's rating.
CASES = [
    ('A nominal (a de libreria)', 3.32e6),
    ('a x1.5 (catalizador rapido)', 6.73e6),
    ('Limite de camara (openMotor)', 10.34e6),
]

EDGE_DISTANCE = 0.008     # m, hole centre to tube end. 2x bolt dia is the usual floor.


def bolts_needed(force_required, spec):
    """Minimum bolt count for each failure path."""
    shear_cap = spec['minor_area'] * BOLT_SHEAR_STRENGTH          # per bolt
    bearing_cap = spec['d'] * WALL * AL_BEARING_YIELD             # per bolt
    tearout_cap = 2 * EDGE_DISTANCE * WALL * AL_SHEAR_ULT         # per bolt
    return (
        math.ceil(force_required / shear_cap),
        math.ceil(force_required / bearing_cap),
        math.ceil(force_required / tearout_cap),
        shear_cap, bearing_cap, tearout_cap,
    )


def main():
    print(f"Bore presurizado : {TUBE_ID*1000:.1f} mm  ->  area {BORE_AREA*1e6:.1f} mm^2")
    print(f"Factor de seguridad: {SAFETY_FACTOR:.0f}x\n")

    for label, pressure in CASES:
        force = pressure * BORE_AREA
        design = force * SAFETY_FACTOR
        print(f"=== {label}: {pressure/1e6:.2f} MPa ===")
        print(f"  Fuerza axial sobre tobera Y sobre tapon: {force:.0f} N  ({force/9.81:.0f} kgf)")
        print(f"  Fuerza de diseno (x{SAFETY_FACTOR:.0f}): {design:.0f} N")
        for name, spec in BOLTS.items():
            n_shear, n_bearing, n_tear, c_s, c_b, c_t = bolts_needed(design, spec)
            n = max(n_shear, n_bearing, n_tear)
            driver = 'corte perno' if n == n_shear else ('aplastamiento Al' if n == n_bearing else 'desgarro Al')
            print(f"    {name}: {n} pernos  (corte {n_shear} / aplast. {n_bearing} / desgarro {n_tear})"
                  f"  -> manda: {driver}")
        print()

    print("Capacidad por perno (para verificar a mano):")
    for name, spec in BOLTS.items():
        _, _, _, c_s, c_b, c_t = bolts_needed(1, spec)
        print(f"  {name}: corte {c_s:.0f} N | aplastamiento en Al {c_b:.0f} N | "
              f"desgarro en Al {c_t:.0f} N")

    circ = math.pi * (TUBE_ID + 2 * WALL)
    print(f"\nCircunferencia del tubo: {circ*1000:.1f} mm")
    for name, spec in BOLTS.items():
        max_bolts = int(circ / (3 * spec['d']))   # 3x diameter minimum spacing
        print(f"  {name}: caben ~{max_bolts} pernos con separacion de 3 diametros")


if __name__ == '__main__':
    main()
