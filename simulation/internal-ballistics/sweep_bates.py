"""
Headless BATES grain sweep for a 1" (25.4mm OD) 6061-T6 minimum-diameter motor.

Uses motorlib directly. Propellant is Nakka KNSB straight from openMotor's
default library (uilib.defaults.KNSB_PROPS) -- burn rate coefficients are NOT
modified.

For each geometry the nozzle throat is solved analytically so that peak Kn hits
a target value: Kn = Ab / At, and Ab(regression) is fixed by geometry, so peak Kn
scales exactly as 1/At. One rescale step is therefore exact.
"""
import math
import itertools

import motorlib
from motorlib.motor import Motor
from motorlib.grains import BatesGrain
from motorlib.nozzle import eRatioFromPRatio
from uilib.defaults import KNSB_PROPS

# --- Chamber / liner geometry -------------------------------------------------
TUBE_OD = 0.0254          # 1 in
WALL = 0.0021             # 2.1 mm
LINER_PER_SIDE = 0.00075  # 0.75 mm of cured kraft/epoxy per side (see notes)

TUBE_ID = TUBE_OD - 2 * WALL              # 21.2 mm
GRAIN_OD = TUBE_ID - 2 * LINER_PER_SIDE   # 19.7 mm

TARGET_PEAK_KN = 280.0    # safety ceiling from the user's 200-280 window
KN_MIN = 200.0

AMB_PRESSURE = 101325.0

# openMotor's own default limits, straight from uilib/defaults.py DEFAULT_PREFERENCES.
MAX_PRESSURE = 1500 * 6895      # 10.34 MPa
MAX_MASS_FLUX = 2 / 0.001422    # 1406 kg/(m^2*s)
MAX_MACH = 0.7
MIN_PORT_THROAT = 2.0


def make_propellant():
    prop = motorlib.propellant.Propellant()
    prop.setProperties(KNSB_PROPS)
    return prop


def build_motor(core_d, n_seg, seg_len, throat_d, exit_d):
    motor = Motor()
    motor.propellant = make_propellant()
    motor.grains = []
    for _ in range(n_seg):
        grain = BatesGrain()
        grain.setProperties({
            'diameter': GRAIN_OD,
            'length': seg_len,
            'coreDiameter': core_d,
            'inhibitedEnds': 'Neither',
        })
        motor.grains.append(grain)
    motor.nozzle.setProperties({
        'throat': throat_d,
        'exit': exit_d,
        'efficiency': 0.85,
        'divAngle': 12,
        'convAngle': 35,
        'throatLength': 0.0,
        'slagCoeff': 0,
        'erosionCoeff': 0,
    })
    motor.config.setProperties({
        'ambPressure': AMB_PRESSURE,
        'timestep': 0.001,
    })
    return motor


def optimal_exit_diameter(throat_d, chamber_pressure, k=1.1361):
    """Exit diameter for exit pressure == ambient at the given chamber pressure.

    eRatioFromPRatio returns At/Ae (the inverse expansion ratio) -- see
    Nozzle.getExitPressure, which compares it against 1/calcExpansion().
    """
    inv_ratio = eRatioFromPRatio(k, AMB_PRESSURE / chamber_pressure)
    return throat_d / math.sqrt(inv_ratio)


def simulate(core_d, n_seg, seg_len):
    """Solve throat for TARGET_PEAK_KN, size the nozzle, return the sim result."""
    # First pass with an arbitrary throat to read the geometry's peak Kn.
    throat = 0.008
    exit_d = throat * 2.5
    res = build_motor(core_d, n_seg, seg_len, throat, exit_d).runSimulation()
    if not res.success:
        return None, None, None

    # Kn scales as 1/At exactly -> rescale throat to land peak Kn on target.
    throat = throat * math.sqrt(res.getPeakKN() / TARGET_PEAK_KN)

    # Size the exit for the resulting average pressure, then re-run.
    res = build_motor(core_d, n_seg, seg_len, throat, throat * 2.5).runSimulation()
    if not res.success:
        return None, None, None
    exit_d = optimal_exit_diameter(throat, res.getAveragePressure())

    motor = build_motor(core_d, n_seg, seg_len, throat, exit_d)
    res = motor.runSimulation()
    return (res, throat, exit_d) if res.success else (None, None, None)


def kn_average(res):
    return sum(res.channels['kn'].getData()) / len(res.channels['kn'].getData())


def main():
    print(f"Tube ID          : {TUBE_ID*1000:.1f} mm")
    print(f"Grain OD (liner) : {GRAIN_OD*1000:.1f} mm")
    print()

    core_diameters = [d / 1000 for d in range(9, 17)]
    segment_counts = [2, 3, 4, 5, 6]
    segment_lengths = [l / 1000 for l in range(25, 61, 5)]

    rejected = {'kn': 0, 'port': 0, 'flux': 0, 'mach': 0, 'pressure': 0}
    rows = []
    for core_d, n_seg, seg_len in itertools.product(core_diameters, segment_counts, segment_lengths):
        total_len = n_seg * seg_len
        if total_len > 0.320:          # keep the motor a sane length
            continue
        # Rule of thumb for BATES: segment length under ~3x outer diameter
        if seg_len > 3 * GRAIN_OD:
            continue

        res, throat, exit_d = simulate(core_d, n_seg, seg_len)
        if res is None:
            continue

        # Hard safety gates -- openMotor's own limits, not invented ones.
        kn_avg = kn_average(res)
        if kn_avg < KN_MIN:
            rejected['kn'] += 1
            continue
        if res.getPortRatio() < MIN_PORT_THROAT:
            rejected['port'] += 1
            continue
        if res.getPeakMassFlux() > MAX_MASS_FLUX:
            rejected['flux'] += 1
            continue
        if res.getPeakMachNumber() > MAX_MACH:
            rejected['mach'] += 1
            continue
        if res.getMaxPressure() > MAX_PRESSURE:
            rejected['pressure'] += 1
            continue

        rows.append({
            'core': core_d, 'nseg': n_seg, 'seglen': seg_len, 'total': total_len,
            'throat': throat, 'exit': exit_d,
            'kn_peak': res.getPeakKN(), 'kn_avg': kn_avg, 'kn_init': res.getInitialKN(),
            'p_peak': res.getMaxPressure(), 'f_peak': res.channels['force'].getMax(),
            'f_avg': res.getAverageForce(),
            'impulse': res.getImpulse(), 'burn': res.getBurnTime(),
            'desig': res.getDesignation(), 'full': res.getFullDesignation(),
            'mass': res.getPropellantMass(),
            'port_throat': res.getPortRatio(),
            'mass_flux': res.getPeakMassFlux(),
        })

    rows.sort(key=lambda r: r['impulse'], reverse=True)

    hdr = (f"{'core':>5} {'seg':>3} {'len':>5} {'total':>6} {'throat':>6} {'exit':>6} "
           f"{'Kn_pk':>6} {'Kn_av':>6} {'Ppk':>6} {'Fpk':>6} {'Ns':>7} {'t_b':>5} "
           f"{'P/T':>4} {'flux':>5} {'class':>6}")
    print(hdr)
    print('-' * len(hdr))
    for r in rows[:25]:
        print(f"{r['core']*1000:5.1f} {r['nseg']:3d} {r['seglen']*1000:5.1f} {r['total']*1000:6.1f} "
              f"{r['throat']*1000:6.2f} {r['exit']*1000:6.2f} "
              f"{r['kn_peak']:6.0f} {r['kn_avg']:6.0f} {r['p_peak']/1e6:6.2f} {r['f_peak']:6.0f} "
              f"{r['impulse']:7.1f} {r['burn']:5.2f} {r['port_throat']:4.1f} "
              f"{r['mass_flux']:5.0f} {r['full']:>6}")

    print(f"\n{len(rows)} configuraciones viables.")
    print(f"Descartadas -> Kn bajo: {rejected['kn']}, port/throat<2: {rejected['port']}, "
          f"mass flux: {rejected['flux']}, mach: {rejected['mach']}, presion: {rejected['pressure']}")
    return rows


if __name__ == '__main__':
    main()
