"""
Two airframe architectures, head to head.

D1 "fuselaje separado": the aluminium motor slides inside a separate 27.4 mm
    fibreglass body tube. The motor's .eng carries 190 g of hardware, which
    INCLUDES its own aluminium tube.

D2 "diametro minimo real": the aluminium motor tube IS the airframe. Fins bond
    straight to it. No outer tube at all. The motor's .eng carries only 65 g
    (nozzle + closures + bolts); the aluminium tube is modelled as structure so
    its mass is counted exactly once.

Getting the double-count right is the whole point -- otherwise D2 looks lighter
than it is.
"""
import jpype
import jpype.imports

JAR = '/home/sebasvelace/openrocket/OpenRocket-24.12.jar'
jpype.startJVM(classpath=[JAR])

from com.google.inject import Guice                                   # noqa: E402
from info.openrocket.core.startup import Application, CoreModule      # noqa: E402
from info.openrocket.core.plugin import PluginModule                  # noqa: E402

Application.setInjector(Guice.createInjector(CoreModule(), PluginModule()))

from info.openrocket.core.file.motor import GeneralMotorLoader        # noqa: E402
from info.openrocket.core.document import OpenRocketDocumentFactory, Simulation  # noqa: E402
from info.openrocket.core.file.openrocket import OpenRocketSaver      # noqa: E402
from info.openrocket.core.motor import MotorConfiguration             # noqa: E402
from info.openrocket.core.rocketcomponent import (                    # noqa: E402
    Rocket, AxialStage, NoseCone, BodyTube, TrapezoidFinSet,
    FlightConfigurationId, Transition, Parachute, DeploymentConfiguration,
    FinSet, ExternalComponent,
)
from info.openrocket.core.rocketcomponent.position import AxialMethod   # noqa: E402
from info.openrocket.core.simulation import FlightDataType             # noqa: E402
from info.openrocket.core.aerodynamics import BarrowmanCalculator, FlightConditions  # noqa: E402
from info.openrocket.core.masscalc import MassCalculator               # noqa: E402
from info.openrocket.core.logging import WarningSet, ErrorSet          # noqa: E402
from info.openrocket.core.material import Material                     # noqa: E402
from java.io import FileInputStream, File, FileOutputStream            # noqa: E402

ALU = Material.newMaterial(Material.Type.BULK, 'Aluminium 6061', 2700.0, False)
GLASS = Material.newMaterial(Material.Type.BULK, 'Fibreglass', 1850.0, False)

MOTOR_LEN = 0.270
RECOVERY_LEN = 0.110
NOSE_LEN = 0.090

AIRFOIL = FinSet.CrossSection.AIRFOIL
POLISHED = ExternalComponent.Finish.POLISHED
HAACK = Transition.Shape.HAACK

_cache = {}


def motor(path):
    if path not in _cache:
        _cache[path] = GeneralMotorLoader().load(
            FileInputStream(path), path).get(0).build()
    return _cache[path]


def add_fins(parent, fin):
    fins = TrapezoidFinSet()
    fins.setFinCount(3)
    fins.setRootChord(fin['root'])
    fins.setTipChord(fin['tip'])
    fins.setHeight(fin['height'])
    fins.setSweep(fin['sweep'])
    fins.setThickness(fin['thickness'])
    fins.setCrossSection(AIRFOIL)
    fins.setFinish(POLISHED)
    fins.setAxialMethod(AxialMethod.BOTTOM)
    fins.setAxialOffset(0.0)
    parent.addChild(fins)
    return fins


def add_chute(parent, diameter=0.45):
    chute = Parachute()
    chute.setDiameter(diameter)
    chute.setLineCount(6)
    chute.setLineLength(0.5)
    chute.setAxialMethod(AxialMethod.TOP)
    chute.setAxialOffset(0.020)
    chute.getDeploymentConfigurations().getDefault().setDeployEvent(
        DeploymentConfiguration.DeployEvent.APOGEE)
    parent.addChild(chute)


def nose(od, length=NOSE_LEN):
    n = NoseCone()
    n.setShapeType(HAACK)
    n.setShapeParameter(0.0)
    n.setLength(length)
    n.setAftRadius(od / 2)
    n.setThickness(0.002)
    n.setFinish(POLISHED)
    return n


def design_separate(fin, eng, chute=0.45):
    """D1: motor inside a 27.4 mm fibreglass airframe."""
    od = 0.0274
    rocket = Rocket()
    stage = AxialStage()
    rocket.addChild(stage)
    stage.addChild(nose(od))

    body = BodyTube()
    body.setLength(MOTOR_LEN + RECOVERY_LEN)
    body.setOuterRadius(od / 2)
    body.setThickness(0.001)
    body.setMaterial(GLASS)
    body.setFinish(POLISHED)
    stage.addChild(body)

    add_fins(body, fin)
    add_chute(body, chute)
    body.setMotorMount(True)
    body.setMotorOverhang(0.003)
    return finish_rocket(rocket, body, eng), od


def design_mindia(fin, eng, chute=0.45):
    """D2: the aluminium motor tube IS the airframe."""
    od = 0.0254
    rocket = Rocket()
    stage = AxialStage()
    rocket.addChild(stage)
    stage.addChild(nose(od))

    # Upper bay: thin fibreglass, carries the recovery gear.
    upper = BodyTube()
    upper.setLength(RECOVERY_LEN)
    upper.setOuterRadius(od / 2)
    upper.setThickness(0.001)
    upper.setMaterial(GLASS)
    upper.setFinish(POLISHED)
    stage.addChild(upper)
    add_chute(upper, chute)

    # The motor tube itself: 6061-T6, 2.1 mm wall. Structure AND pressure vessel.
    alu = BodyTube()
    alu.setLength(MOTOR_LEN)
    alu.setOuterRadius(od / 2)
    alu.setThickness(0.0021)
    alu.setMaterial(ALU)
    alu.setFinish(POLISHED)
    stage.addChild(alu)

    add_fins(alu, fin)
    alu.setMotorMount(True)
    alu.setMotorOverhang(0.003)
    return finish_rocket(rocket, alu, eng), od


def finish_rocket(rocket, mount, eng):
    fcid = FlightConfigurationId()
    rocket.createFlightConfiguration(fcid)
    mc = MotorConfiguration(mount, fcid)
    mc.setMotor(motor(eng))
    mc.setEjectionDelay(0.0)
    mount.setMotorConfig(mc, fcid)
    rocket.setSelectedConfiguration(fcid)
    return rocket, fcid


def fly(built, od, wind=2.0, save_to=None):
    rocket, fcid = built
    doc = OpenRocketDocumentFactory.createDocumentFromRocket(rocket)
    sim = Simulation(doc, rocket)
    sim.setFlightConfigurationId(fcid)
    o = sim.getOptions()
    o.setLaunchRodLength(1.5)
    o.setWindSpeedAverage(wind)
    doc.addSimulation(sim)
    sim.simulate()

    b = sim.getSimulatedData().getBranch(0)
    cfg = rocket.getSelectedConfiguration()
    c = FlightConditions(cfg)
    c.setMach(0.3)
    cp = BarrowmanCalculator().getCP(cfg, c, WarningSet())
    L = MassCalculator.calculateLaunch(cfg)
    BO = MassCalculator.calculateBurnout(cfg)

    if save_to:
        out = FileOutputStream(File(save_to))
        try:
            OpenRocketSaver().save(out, doc, WarningSet(), ErrorSet())
        finally:
            out.close()

    alt = b.get(FlightDataType.TYPE_ALTITUDE)
    vel = b.get(FlightDataType.TYPE_VELOCITY_TOTAL)
    rail = 0.0
    for i in range(len(alt)):
        if float(alt[i]) >= 1.5:
            rail = float(vel[i])
            break

    return {
        'apogee': float(b.getMaximum(FlightDataType.TYPE_ALTITUDE)),
        'mach': float(b.getMaximum(FlightDataType.TYPE_MACH_NUMBER)),
        'vmax': float(b.getMaximum(FlightDataType.TYPE_VELOCITY_TOTAL)),
        'mass': float(L.getMass()) * 1000,
        'margin': float((cp.x - L.getCM().x) / od),
        'margin_bo': float((cp.x - BO.getCM().x) / od),
        'rail': rail,
        'warn': [str(w) for w in sim.getSimulatedWarnings()],
    }
