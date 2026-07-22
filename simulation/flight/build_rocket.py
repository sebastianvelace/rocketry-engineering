"""
Builds a minimum-diameter rocket around the openMotor 'Configuration A' motor,
simulates it headless with OpenRocket's own core, and writes an .ork the GUI can
open.

Everything here is driven by OpenRocket's real API via JPype -- no hand-written
XML, no invented schema.
"""
import jpype
import jpype.imports

JAR = '/home/sebasvelace/openrocket/OpenRocket-24.12.jar'
ENG = '/home/sebasvelace/openMotor/KNSB_25mm_BATES.eng'          # Config A, G184
ORK_OUT = '/home/sebasvelace/openrocket/minimum_diameter_A.ork'

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
from java.io import FileInputStream, File                            # noqa: E402

# --- Airframe assumptions (state them, do not hide them) ----------------------
# Minimum diameter: the airframe is a tube that the 25.4 mm motor slides into.
AIRFRAME_ID = 0.0254        # motor OD
AIRFRAME_WALL = 0.001       # 1 mm fibreglass/phenolic
AIRFRAME_OD = AIRFRAME_ID + 2 * AIRFRAME_WALL     # 27.4 mm

NOSE_LENGTH = 0.110         # ~4 calibres, ogive
BODY_LENGTH = 0.450         # 300 mm motor + ~150 mm recovery bay

FIN_COUNT = 3
FIN_ROOT = 0.060
FIN_TIP = 0.030
FIN_HEIGHT = 0.040
FIN_SWEEP = 0.030
FIN_THICKNESS = 0.0024      # 2.4 mm G10

MOTOR_OVERHANG = 0.003


def load_motor(path):
    loader = GeneralMotorLoader()
    builders = loader.load(FileInputStream(path), path)
    return builders.get(0).build()


def build_rocket(motor):
    rocket = Rocket()
    rocket.setName('Minimum diameter 25.4mm - KNSB config A')

    stage = AxialStage()
    stage.setName('Sustainer')
    rocket.addChild(stage)

    nose = NoseCone()
    nose.setName('Nose cone')
    nose.setShapeType(Transition.Shape.OGIVE)
    nose.setLength(NOSE_LENGTH)
    nose.setAftRadius(AIRFRAME_OD / 2)
    nose.setThickness(0.002)
    stage.addChild(nose)

    body = BodyTube()
    body.setName('Body tube')
    body.setLength(BODY_LENGTH)
    body.setOuterRadius(AIRFRAME_OD / 2)
    body.setThickness(AIRFRAME_WALL)
    stage.addChild(body)

    fins = TrapezoidFinSet()
    fins.setName('Fins')
    fins.setFinCount(FIN_COUNT)
    fins.setRootChord(FIN_ROOT)
    fins.setTipChord(FIN_TIP)
    fins.setHeight(FIN_HEIGHT)
    fins.setSweep(FIN_SWEEP)
    fins.setThickness(FIN_THICKNESS)
    fins.setAxialMethod(AxialMethod.BOTTOM)
    fins.setAxialOffset(0.0)
    body.addChild(fins)

    # Recovery. Without it OpenRocket warns and the descent is a lawn dart.
    chute = Parachute()
    chute.setName('Parachute')
    chute.setDiameter(0.45)
    chute.setLineCount(6)
    chute.setLineLength(0.5)
    chute.setAxialMethod(AxialMethod.TOP)
    chute.setAxialOffset(0.020)
    # The default deploy event fires at BURNOUT -- at Mach 0.87 that shreds the
    # chute and kills the flight. Force apogee deployment.
    chute.getDeploymentConfigurations().getDefault().setDeployEvent(
        DeploymentConfiguration.DeployEvent.APOGEE)
    body.addChild(chute)

    # The body tube IS the motor mount -- that is what minimum diameter means.
    body.setMotorMount(True)
    body.setMotorOverhang(MOTOR_OVERHANG)

    fcid = FlightConfigurationId()
    config = rocket.createFlightConfiguration(fcid)
    config.setName('Config A - G184')

    mc = MotorConfiguration(body, fcid)
    mc.setMotor(motor)
    mc.setEjectionDelay(0.0)
    body.setMotorConfig(mc, fcid)

    rocket.setSelectedConfiguration(fcid)
    return rocket, fcid


def main():
    motor = load_motor(ENG)
    print(f'Motor    : {motor.getDesignation()} ({motor.getManufacturer()})  '
          f'{float(motor.getTotalImpulseEstimate()):.1f} N-s, '
          f'{float(motor.getBurnTimeEstimate()):.2f} s')

    rocket, fcid = build_rocket(motor)

    doc = OpenRocketDocumentFactory.createDocumentFromRocket(rocket)
    sim = Simulation(doc, rocket)
    sim.setName('Config A - vuelo nominal')
    sim.setFlightConfigurationId(fcid)
    sim.getOptions().setLaunchRodLength(1.5)     # 1.5 m rail
    doc.addSimulation(sim)

    print(f'Airframe : OD {AIRFRAME_OD*1000:.1f} mm, '
          f'largo total {(NOSE_LENGTH+BODY_LENGTH)*1000:.0f} mm')

    sim.simulate()
    branch = sim.getSimulatedData().getBranch(0)
    from info.openrocket.core.simulation import FlightDataType
    apogee = sim.getSimulatedData().getBranch(0).getMaximum(FlightDataType.TYPE_ALTITUDE)
    vmax = branch.getMaximum(FlightDataType.TYPE_VELOCITY_TOTAL)
    amax = branch.getMaximum(FlightDataType.TYPE_ACCELERATION_TOTAL)
    mach = branch.getMaximum(FlightDataType.TYPE_MACH_NUMBER)

    print()
    print(f'  Apogeo            : {apogee:.0f} m')
    print(f'  Velocidad maxima  : {vmax:.0f} m/s  (Mach {mach:.2f})')
    print(f'  Aceleracion maxima: {amax:.0f} m/s^2  ({amax/9.81:.0f} g)')

    # Stability -- the number that decides whether it flies straight or cartwheels.
    from info.openrocket.core.aerodynamics import BarrowmanCalculator, FlightConditions
    from info.openrocket.core.masscalc import MassCalculator
    from info.openrocket.core.logging import WarningSet

    cfg = rocket.getSelectedConfiguration()
    cond = FlightConditions(cfg)
    cond.setMach(0.3)
    cp = BarrowmanCalculator().getCP(cfg, cond, WarningSet())
    launch = MassCalculator.calculateLaunch(cfg)
    burnout = MassCalculator.calculateBurnout(cfg)

    print()
    print(f'  Masa en despegue  : {launch.getMass()*1000:.0f} g')
    print(f'  Masa en burnout   : {burnout.getMass()*1000:.0f} g  (estructura + casing)')
    print(f'  CP                : {cp.x*1000:.0f} mm desde la punta')
    print(f'  Margen (despegue) : '
          f'{(cp.x - launch.getCM().x)/AIRFRAME_OD:.2f} calibres')
    print(f'  Margen (burnout)  : '
          f'{(cp.x - burnout.getCM().x)/AIRFRAME_OD:.2f} calibres')
    warnings = [str(w) for w in sim.getSimulatedWarnings()]
    print(f'  Advertencias      : {warnings if warnings else "ninguna"}')

    from info.openrocket.core.logging import WarningSet, ErrorSet
    from java.io import FileOutputStream
    out = FileOutputStream(File(ORK_OUT))
    try:
        OpenRocketSaver().save(out, doc, WarningSet(), ErrorSet())
    finally:
        out.close()
    print(f'\nEscrito: {ORK_OUT}')


if __name__ == '__main__':
    main()
