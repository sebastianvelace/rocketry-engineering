"""
Exports the recommended BATES motor to RASP .eng format for OpenRocket.

openMotor's own ENG exporter (uilib/converters/engExporter.py) is a QDialog bound
to the GUI's simulation manager, so it cannot be called headless. This reproduces
the exact file format its doConversion() writes.
"""
import sweep_bates as S

# --- Configuration E: the INSTRUMENTATION motor -------------------------------
# Not the max-impulse design. This one is flown to measure the real burn-rate
# coefficient 'a' of the Fe2O3-catalysed mix. It tolerates a x1.35 before mass
# flux crosses into erosive burning, vs only a x1.07 for config A.
CORE_D = 0.013      # 13 mm
N_SEG = 4
SEG_LEN = 0.055     # 55 mm each -> 220 mm of grain

MOTOR_DIAMETER = S.TUBE_OD   # 25.4 mm -- the .eng "diameter" is the motor OD
MOTOR_LENGTH = 0.270         # 220 mm grain + closures/nozzle. ADJUST to your build.
MANUFACTURER = 'Amateur'

# TODO(PENDIENTE): pesar el hardware real en balanza y poner el valor aca.
# Es todo lo que no es propelente: tubo + tobera + cierres + retencion.
# El placeholder de abajo es un ESTIMADO, no un valor medido. OpenRocket usa esta
# masa para calcular el apogeo: 50 g de error mueven la prediccion de altura de
# forma no trivial. No exportar un .eng "final" hasta reemplazarlo.
HARDWARE_MASS = 0.190        # kg  <-- SIN MEDIR. REEMPLAZAR.

OUT_PATH = '/home/sebasvelace/openMotor/KNSB_25mm_BATES_configE.eng'


def write_eng(res, path, designation):
    prop_mass = res.getPropellantMass()
    time_data = list(res.channels['time'].getData())
    force_data = list(res.channels['force'].getData())

    # Same as engExporter: pad a zero-thrust point so RASAero/OpenRocket accept it.
    if force_data[-1] != 0:
        time_data.append(res.getBurnTime() + 0.01)
        force_data.append(0)

    header = ' '.join([
        designation,
        str(round(MOTOR_DIAMETER * 1000, 6)),
        str(round(MOTOR_LENGTH * 1000, 6)),
        'P',                                       # no ejection delays
        str(round(prop_mass, 6)),
        str(round(prop_mass + HARDWARE_MASS, 6)),
        MANUFACTURER,
    ]) + '\n'

    body = ''
    for time, force in zip(time_data, force_data):
        if time == 0:      # first point must not be zero thrust
            force += 0.01
        body += f'{round(time, 4)} {round(force, 4)}\n'

    with open(path, 'w') as out_file:
        out_file.write(header + body + ';\n;\n')

    return prop_mass, len(time_data)


def main():
    res, throat, exit_d = S.simulate(CORE_D, N_SEG, SEG_LEN)
    if res is None:
        raise SystemExit('Simulation failed')

    designation = res.getDesignation()
    prop_mass, points = write_eng(res, OUT_PATH, designation)

    print(f'Geometria    : OD {S.GRAIN_OD*1000:.1f} mm / core {CORE_D*1000:.0f} mm / '
          f'{N_SEG} x {SEG_LEN*1000:.0f} mm')
    print(f'Tobera       : garganta {throat*1000:.2f} mm, salida {exit_d*1000:.2f} mm '
          f'(expansion {(exit_d/throat)**2:.2f})')
    print(f'Kn           : pico {res.getPeakKN():.0f}, promedio {S.kn_average(res):.0f}, '
          f'inicial {res.getInitialKN():.0f}')
    print(f'Presion pico : {res.getMaxPressure()/1e6:.2f} MPa ({res.getMaxPressure()/6895:.0f} psi)')
    print(f'Empuje       : pico {res.channels["force"].getMax():.0f} N, '
          f'promedio {res.getAverageForce():.0f} N')
    print(f'Impulso      : {res.getImpulse():.1f} N-s  ->  {res.getFullDesignation()}')
    print(f'Quemado      : {res.getBurnTime():.2f} s')
    print(f'Propelente   : {prop_mass*1000:.0f} g')
    print(f'Port/throat  : {res.getPortRatio():.2f}   Mass flux pico: {res.getPeakMassFlux():.0f} kg/(m^2*s)')
    print(f'\nEscrito: {OUT_PATH}  ({points} puntos de la curva de empuje)')


if __name__ == '__main__':
    main()
