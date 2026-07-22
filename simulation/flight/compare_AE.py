"""
Same airframe, two motors. Config A (G184, max impulse) vs Config E (F167, the
instrumentation motor that actually gets built).

Reuses the rocket builder from build_rocket.py so the airframe is identical --
the only variable is the motor.
"""
import jpype
import jpype.imports

JAR = '/home/sebasvelace/openrocket/OpenRocket-24.12.jar'
jpype.startJVM(classpath=[JAR])

from com.google.inject import Guice                                  # noqa: E402
from info.openrocket.core.startup import Application, CoreModule     # noqa: E402
from info.openrocket.core.plugin import PluginModule                 # noqa: E402

Application.setInjector(Guice.createInjector(CoreModule(), PluginModule()))

from info.openrocket.core.file.motor import GeneralMotorLoader       # noqa: E402
from info.openrocket.core.document import OpenRocketDocumentFactory, Simulation  # noqa: E402
from info.openrocket.core.file.openrocket import OpenRocketSaver     # noqa: E402
from info.openrocket.core.motor import MotorConfiguration            # noqa: E402
from info.openrocket.core.rocketcomponent import (                   # noqa: E402
    Rocket, AxialStage, NoseCone, BodyTube, TrapezoidFinSet,
    FlightConfigurationId, Transition, Parachute, DeploymentConfiguration,
)
from info.openrocket.core.rocketcomponent.position import AxialMethod  # noqa: E402
from info.openrocket.core.simulation import FlightDataType            # noqa: E402
from info.openrocket.core.aerodynamics import BarrowmanCalculator, FlightConditions  # noqa: E402
from info.openrocket.core.masscalc import MassCalculator              # noqa: E402
from info.openrocket.core.logging import WarningSet, ErrorSet         # noqa: E402
from java.io import FileInputStream, File, FileOutputStream           # noqa: E402

# Identical airframe for both motors -- see build_rocket.py for the reasoning.
AIRFRAME_OD = 0.0274
NOSE_LENGTH = 0.110
BODY_LENGTH = 0.450

MOTORS = {
    'A (G184, max impulso)': '/home/sebasvelace/openMotor/KNSB_25mm_BATES.eng',
    'E (F167, instrumentacion)': '/home/sebasvelace/openMotor/KNSB_25mm_BATES_configE.eng',
}
ORK_OUT = '/home/sebasvelace/openrocket/minimum_diameter_E.ork'


def load_motor(path):
    return GeneralMotorLoader().load(FileInputStream(path), path).get(0).build()


def build(motor, name):
    rocket = Rocket()
    rocket.setName(f'Minimum diameter 25.4mm - {name}')

    stage = AxialStage()
    stage.setName('Sustainer')
    rocket.addChild(stage)

    nose = NoseCone()
    nose.setShapeType(Transition.Shape.OGIVE)
    nose.setLength(NOSE_LENGTH)
    nose.setAftRadius(AIRFRAME_OD / 2)
    nose.setThickness(0.002)
    nose.setName('Nose cone')
    stage.addChild(nose)

    body = BodyTube()
    body.setName('Body tube')
    body.setLength(BODY_LENGTH)
    body.setOuterRadius(AIRFRAME_OD / 2)
    body.setThickness(0.001)
    stage.addChild(body)

    fins = TrapezoidFinSet()
    fins.setName('Fins')
    fins.setFinCount(3)
    fins.setRootChord(0.060)
    fins.setTipChord(0.030)
    fins.setHeight(0.040)
    fins.setSweep(0.030)
    fins.setThickness(0.0024)
    fins.setAxialMethod(AxialMethod.BOTTOM)
    fins.setAxialOffset(0.0)
    body.addChild(fins)

    chute = Parachute()
    chute.setName('Parachute')
    chute.setDiameter(0.45)
    chute.setLineCount(6)
    chute.setLineLength(0.5)
    chute.setAxialMethod(AxialMethod.TOP)
    chute.setAxialOffset(0.020)
    chute.getDeploymentConfigurations().getDefault().setDeployEvent(
        DeploymentConfiguration.DeployEvent.APOGEE)
    body.addChild(chute)

    body.setMotorMount(True)
    body.setMotorOverhang(0.003)

    fcid = FlightConfigurationId()
    rocket.createFlightConfiguration(fcid).setName(name)
    mc = MotorConfiguration(body, fcid)
    mc.setMotor(motor)
    mc.setEjectionDelay(0.0)
    body.setMotorConfig(mc, fcid)
    rocket.setSelectedConfiguration(fcid)
    return rocket, fcid


def fly(label, eng_path, save_to=None):
    motor = load_motor(eng_path)
    rocket, fcid = build(motor, label)
    doc = OpenRocketDocumentFactory.createDocumentFromRocket(rocket)
    sim = Simulation(doc, rocket)
    sim.setName(label)
    sim.setFlightConfigurationId(fcid)
    sim.getOptions().setLaunchRodLength(1.5)
    doc.addSimulation(sim)
    sim.simulate()

    b = sim.getSimulatedData().getBranch(0)
    cfg = rocket.getSelectedConfiguration()
    cond = FlightConditions(cfg)
    cond.setMach(0.3)
    cp = BarrowmanCalculator().getCP(cfg, cond, WarningSet())
    launch = MassCalculator.calculateLaunch(cfg)

    if save_to:
        out = FileOutputStream(File(save_to))
        try:
            OpenRocketSaver().save(out, doc, WarningSet(), ErrorSet())
        finally:
            out.close()

    return {
        'impulso': float(motor.getTotalImpulseEstimate()),
        'apogeo': b.getMaximum(FlightDataType.TYPE_ALTITUDE),
        'vmax': b.getMaximum(FlightDataType.TYPE_VELOCITY_TOTAL),
        'mach': b.getMaximum(FlightDataType.TYPE_MACH_NUMBER),
        'accel': b.getMaximum(FlightDataType.TYPE_ACCELERATION_TOTAL),
        'vriel': b.getMaximum(FlightDataType.TYPE_VELOCITY_Z),
        'masa': launch.getMass() * 1000,
        'margen': (cp.x - launch.getCM().x) / AIRFRAME_OD,
        'warn': [str(w) for w in sim.getSimulatedWarnings()],
    }


def main():
    results = {}
    for label, path in MOTORS.items():
        save = ORK_OUT if label.startswith('E') else None
        results[label] = fly(label, path, save)

    hdr = f"{'motor':>26}{'Ns':>7}{'apogeo':>9}{'v_max':>8}{'Mach':>7}{'accel':>8}{'masa':>7}{'margen':>8}"
    print()
    print(hdr)
    print('-' * len(hdr))
    for label, r in results.items():
        print(f"{label:>26}{r['impulso']:7.1f}{r['apogeo']:8.0f}m{r['vmax']:7.0f}"
              f"{r['mach']:7.2f}{r['accel']/9.81:7.0f}g{r['masa']:6.0f}g{r['margen']:7.2f}c")

    a = results['A (G184, max impulso)']
    e = results['E (F167, instrumentacion)']
    d_apo = 100 * (e['apogeo'] - a['apogeo']) / a['apogeo']
    d_imp = 100 * (e['impulso'] - a['impulso']) / a['impulso']
    print()
    print(f"E vs A -> impulso {d_imp:+.0f}%,  apogeo {d_apo:+.0f}%")
    for label, r in results.items():
        if r['warn']:
            print(f"  advertencias {label}: {r['warn']}")
    print(f"\nEscrito: {ORK_OUT}")


if __name__ == '__main__':
    main()
