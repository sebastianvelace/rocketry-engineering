"""
Writes the swept configurations out as openMotor .ric motor files so they can be
opened in the GUI (File > Open) and re-simulated there.

The sweeps run headless and keep nothing on disk, so nothing shows up in the app.
This is what makes them visible.
"""
import motorlib
from motorlib.motor import Motor
from motorlib.grains import BatesGrain
from uilib.fileIO import saveFile, fileTypes
from uilib.defaults import KNSB_PROPS, DEFAULT_PREFERENCES

import sweep_bates as S

OUT_DIR = '/home/sebasvelace/openMotor/motors'

# A bare Motor() defaults to ambPressure = 0.0001 Pa -- i.e. VACUUM -- which
# inflates impulse by ~12%. The config must be set explicitly, both for the
# simulation here and for what gets serialised into the .ric file.
MOTOR_CONFIG = {k: v for k, v in DEFAULT_PREFERENCES['general'].items()
                if k != 'igniterPressure'}      # deprecated, not a MotorConfig prop
MOTOR_CONFIG['timestep'] = 0.001                # finer than the 0.03 GUI default

# name -> (core, segments, segment length, throat, exit)
CONFIGS = {
    'A_max_impulso':      (0.012, 5, 0.050, 0.00771, 0.01813),
    'B_6seg':             (0.013, 6, 0.045, 0.00804, 0.01908),
    'C_4seg_largo':       (0.011, 4, 0.055, 0.00722, 0.01680),
    'D_empuje_alto':      (0.014, 6, 0.050, 0.00865, 0.02044),
    'E_instrumentacion':  (0.013, 4, 0.055, 0.00737, 0.01729),
    # Core sensitivity around E -- same throat, different mandrel.
    'E_nucleo_12.00mm':   (0.01200, 4, 0.055, 0.00737, 0.01729),
    'E_nucleo_12.70mm':   (0.01270, 4, 0.055, 0.00737, 0.01729),
    'E_nucleo_14.00mm':   (0.01400, 4, 0.055, 0.00737, 0.01729),
}


def build(core_d, n_seg, seg_len, throat, exit_d):
    motor = Motor()
    prop = motorlib.propellant.Propellant()
    prop.setProperties(KNSB_PROPS)
    motor.propellant = prop
    motor.grains = []
    for _ in range(n_seg):
        grain = BatesGrain()
        grain.setProperties({
            'diameter': S.GRAIN_OD,
            'length': seg_len,
            'coreDiameter': core_d,
            'inhibitedEnds': 'Neither',
        })
        motor.grains.append(grain)
    motor.nozzle.setProperties({
        'throat': throat, 'exit': exit_d, 'efficiency': 0.85,
        'divAngle': 12, 'convAngle': 35, 'throatLength': 0.0,
        'slagCoeff': 0, 'erosionCoeff': 0,
    })
    motor.config.setProperties(MOTOR_CONFIG)
    return motor


def main():
    import os
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, params in CONFIGS.items():
        motor = build(*params)
        path = f'{OUT_DIR}/{name}.ric'
        saveFile(path, motor.getDict(), fileTypes.MOTOR)
        res = motor.runSimulation()
        print(f'{name:22} -> {res.getFullDesignation():>8}  '
              f'{res.getImpulse():5.1f} Ns  P/T {res.getPortRatio():.2f}  '
              f'flux {100*res.getPeakMassFlux()/S.MAX_MASS_FLUX:.0f}%')
    print(f'\nEscritos en {OUT_DIR}/')


if __name__ == '__main__':
    main()
