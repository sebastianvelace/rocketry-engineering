"""
Burn-rate sensitivity for configuration A with an ALREADY-MACHINED throat.

The library KNSB coefficients are for plain 65/35 KNO3/sorbitol. A 1% Fe2O3
catalyst raises the burn rate, i.e. scales the 'a' coefficient. This sweeps that
scale factor with the throat FIXED at 7.71 mm and finds where chamber pressure
crosses 10.34 MPa or peak mass flux crosses 1406 kg/(m^2*s).
"""
import copy
import math

import motorlib
from motorlib.motor import Motor
from motorlib.grains import BatesGrain
from uilib.defaults import KNSB_PROPS

import sweep_bates as S

# Configuration A, as chosen. Throat is now a fabricated part -- it does not move.
CORE_D = 0.012
N_SEG = 5
SEG_LEN = 0.050
THROAT = 0.00771      # machined
EXIT = 0.01813


def scaled_propellant(scale):
    """KNSB with every burn-rate 'a' coefficient multiplied by `scale`."""
    props = copy.deepcopy(KNSB_PROPS)
    for tab in props['tabs']:
        tab['a'] = tab['a'] * scale
    prop = motorlib.propellant.Propellant()
    prop.setProperties(props)
    return prop


def run(scale):
    motor = Motor()
    motor.propellant = scaled_propellant(scale)
    motor.grains = []
    for _ in range(N_SEG):
        grain = BatesGrain()
        grain.setProperties({
            'diameter': S.GRAIN_OD,
            'length': SEG_LEN,
            'coreDiameter': CORE_D,
            'inhibitedEnds': 'Neither',
        })
        motor.grains.append(grain)
    motor.nozzle.setProperties({
        'throat': THROAT, 'exit': EXIT, 'efficiency': 0.85,
        'divAngle': 12, 'convAngle': 35, 'throatLength': 0.0,
        'slagCoeff': 0, 'erosionCoeff': 0,
    })
    motor.config.setProperties({'ambPressure': S.AMB_PRESSURE, 'timestep': 0.001})
    res = motor.runSimulation()
    return res if res.success else None


def bisect(metric, limit, lo=1.0, hi=3.0, tol=0.005):
    """Find the 'a' scale factor at which `metric(res)` reaches `limit`."""
    for _ in range(40):
        mid = (lo + hi) / 2
        res = run(mid)
        if res is None:
            hi = mid
            continue
        if metric(res) < limit:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return (lo + hi) / 2


def main():
    print(f"Config A con garganta FIJA en {THROAT*1000:.2f} mm\n")
    hdr = (f"{'a x':>6} {'P pico':>9} {'% lim P':>8} {'flux':>7} {'% lim F':>8} "
           f"{'Kn pico':>8} {'F pico':>7} {'t_b':>6} {'Ns':>7}")
    print(hdr)
    print('-' * len(hdr))
    for scale in (1.0, 1.2, 1.5, 2.0):
        res = run(scale)
        if res is None:
            print(f"{scale:5.1f}x   SIMULACION FALLIDA")
            continue
        p = res.getMaxPressure()
        flux = res.getPeakMassFlux()
        print(f"{scale:5.1f}x {p/1e6:8.2f}M {100*p/S.MAX_PRESSURE:7.0f}% "
              f"{flux:7.0f} {100*flux/S.MAX_MASS_FLUX:7.0f}% "
              f"{res.getPeakKN():8.0f} {res.channels['force'].getMax():7.0f} "
              f"{res.getBurnTime():6.2f} {res.getImpulse():7.1f}")

    print(f"\nLimites: presion {S.MAX_PRESSURE/1e6:.2f} MPa, "
          f"mass flux {S.MAX_MASS_FLUX:.0f} kg/(m^2*s)")

    a_press = bisect(lambda r: r.getMaxPressure(), S.MAX_PRESSURE)
    a_flux = bisect(lambda r: r.getPeakMassFlux(), S.MAX_MASS_FLUX)
    print(f"\nCruce del limite de PRESION  : a x {a_press:.2f}  (+{100*(a_press-1):.0f}%)")
    print(f"Cruce del limite de MASS FLUX: a x {a_flux:.2f}  (+{100*(a_flux-1):.0f}%)")
    print(f"\nEl que manda es: "
          f"{'MASS FLUX' if a_flux < a_press else 'PRESION'}")

    # Pressure at the binding limit -- this is what the retention must survive.
    binding = min(a_press, a_flux)
    res = run(binding)
    print(f"Presion de camara en ese punto: {res.getMaxPressure()/1e6:.2f} MPa "
          f"({res.getMaxPressure()/6895:.0f} psi)")


if __name__ == '__main__':
    main()
