"""
Rigorous airframe study on the 25.4 mm minimum-diameter rocket.

Phase 1: all five openMotor configs on the identical baseline airframe.
Phase 2: one-factor-at-a-time on motor E, so each gain is attributable.
Phase 3: constrained grid search over the levers that actually paid off.

Hard constraints (a design that violates any of these is discarded, no matter how
high it flies):
  - launch stability margin between 1.5 and 3.0 calibres
  - burnout stability margin >= 1.0 calibre
  - rail exit velocity >= 15 m/s  (below this the fins have no authority)
  - no OpenRocket simulation warnings
"""
import itertools

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
from java.io import FileInputStream, File, FileOutputStream            # noqa: E402

ENG = {
    'A': '/home/sebasvelace/openMotor/eng/A.eng',
    'B': '/home/sebasvelace/openMotor/eng/B.eng',
    'C': '/home/sebasvelace/openMotor/eng/C.eng',
    'D': '/home/sebasvelace/openMotor/eng/D.eng',
    'E': '/home/sebasvelace/openMotor/eng/E.eng',
}

AIRFRAME_OD = 0.0274      # fixed: the 25.4 mm motor sets it

# Baseline airframe (what we flew so far)
BASELINE = dict(
    nose_shape='Ogive',
    nose_param=1.0,
    nose_length=0.110,
    nose_thickness=0.002,
    body_length=0.450,
    body_wall=0.001,
    fin_count=3,
    fin_root=0.060,
    fin_tip=0.030,
    fin_height=0.040,
    fin_sweep=0.030,
    fin_thickness=0.0024,
    fin_section='SQUARE',
    finish='Regularpaint',
)

SHAPES = {
    'Ogive': Transition.Shape.OGIVE,
    'Conical': Transition.Shape.CONICAL,
    'Ellipsoid': Transition.Shape.ELLIPSOID,
    'Haack': Transition.Shape.HAACK,
    'Power': Transition.Shape.POWER,
    'Parabolic': Transition.Shape.PARABOLIC,
}
SECTIONS = {
    'SQUARE': FinSet.CrossSection.SQUARE,
    'ROUNDED': FinSet.CrossSection.ROUNDED,
    'AIRFOIL': FinSet.CrossSection.AIRFOIL,
}
FINISHES = {
    'Regularpaint': ExternalComponent.Finish.NORMAL,
    'Smoothpaint': ExternalComponent.Finish.SMOOTH,
    'Polished': ExternalComponent.Finish.POLISHED,
}

_motor_cache = {}


def motor(key):
    if key not in _motor_cache:
        path = ENG[key]
        _motor_cache[key] = GeneralMotorLoader().load(
            FileInputStream(path), path).get(0).build()
    return _motor_cache[key]


def build(p, motor_key):
    rocket = Rocket()
    rocket.setName(f'MinDia {motor_key}')
    stage = AxialStage()
    rocket.addChild(stage)

    finish = FINISHES[p['finish']]

    nose = NoseCone()
    nose.setShapeType(SHAPES[p['nose_shape']])
    nose.setShapeParameter(p['nose_param'])
    nose.setLength(p['nose_length'])
    nose.setAftRadius(AIRFRAME_OD / 2)
    nose.setThickness(p['nose_thickness'])
    nose.setFinish(finish)
    stage.addChild(nose)

    body = BodyTube()
    body.setLength(p['body_length'])
    body.setOuterRadius(AIRFRAME_OD / 2)
    body.setThickness(p['body_wall'])
    body.setFinish(finish)
    stage.addChild(body)

    fins = TrapezoidFinSet()
    fins.setFinCount(p['fin_count'])
    fins.setRootChord(p['fin_root'])
    fins.setTipChord(p['fin_tip'])
    fins.setHeight(p['fin_height'])
    fins.setSweep(p['fin_sweep'])
    fins.setThickness(p['fin_thickness'])
    fins.setCrossSection(SECTIONS[p['fin_section']])
    fins.setFinish(finish)
    fins.setAxialMethod(AxialMethod.BOTTOM)
    fins.setAxialOffset(0.0)
    body.addChild(fins)

    chute = Parachute()
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
    rocket.createFlightConfiguration(fcid).setName(motor_key)
    mc = MotorConfiguration(body, fcid)
    mc.setMotor(motor(motor_key))
    mc.setEjectionDelay(0.0)
    body.setMotorConfig(mc, fcid)
    rocket.setSelectedConfiguration(fcid)
    return rocket, fcid


def fly(p, motor_key, save_to=None):
    rocket, fcid = build(p, motor_key)
    doc = OpenRocketDocumentFactory.createDocumentFromRocket(rocket)
    sim = Simulation(doc, rocket)
    sim.setFlightConfigurationId(fcid)
    sim.getOptions().setLaunchRodLength(1.5)     # identical conditions for all
    sim.getOptions().setWindSpeedAverage(2.0)
    sim.getOptions().setLaunchRodAngle(0.0)
    doc.addSimulation(sim)
    sim.simulate()

    b = sim.getSimulatedData().getBranch(0)
    cfg = rocket.getSelectedConfiguration()
    cond = FlightConditions(cfg)
    cond.setMach(0.3)
    cp = BarrowmanCalculator().getCP(cfg, cond, WarningSet())
    launch = MassCalculator.calculateLaunch(cfg)
    burnout = MassCalculator.calculateBurnout(cfg)
    struct = MassCalculator.calculateStructure(cfg)

    if save_to:
        out = FileOutputStream(File(save_to))
        try:
            OpenRocketSaver().save(out, doc, WarningSet(), ErrorSet())
        finally:
            out.close()

    return {
        'apogee': float(b.getMaximum(FlightDataType.TYPE_ALTITUDE)),
        'vmax': float(b.getMaximum(FlightDataType.TYPE_VELOCITY_TOTAL)),
        'mach': float(b.getMaximum(FlightDataType.TYPE_MACH_NUMBER)),
        'accel': float(b.getMaximum(FlightDataType.TYPE_ACCELERATION_TOTAL)),
        'rail': float(b.get(FlightDataType.TYPE_VELOCITY_TOTAL).get(
            _rail_index(b))) if False else _rail_exit(b),
        'mass': float(launch.getMass()) * 1000,
        'struct': float(struct.getMass()) * 1000,
        'margin': float((cp.x - launch.getCM().x) / AIRFRAME_OD),
        'margin_bo': float((cp.x - burnout.getCM().x) / AIRFRAME_OD),
        'warn': [str(w) for w in sim.getSimulatedWarnings()],
    }


def _rail_index(b):
    return 0


def _rail_exit(branch):
    """Velocity when the rocket clears the 1.5 m rail."""
    alt = branch.get(FlightDataType.TYPE_ALTITUDE)
    vel = branch.get(FlightDataType.TYPE_VELOCITY_TOTAL)
    for i in range(len(alt)):
        if float(alt[i]) >= 1.5:
            return float(vel[i])
    return 0.0


def feasible(r):
    return (1.5 <= r['margin'] <= 3.0
            and r['margin_bo'] >= 1.0
            and r['rail'] >= 15.0
            and not r['warn'])


def row(label, r, flag=''):
    ok = 'OK ' if feasible(r) else 'NO '
    return (f"{label:<30}{r['apogee']:7.0f}m{r['vmax']:7.0f}{r['mach']:6.2f}"
            f"{r['mass']:6.0f}g{r['struct']:6.0f}g{r['margin']:6.2f}"
            f"{r['margin_bo']:6.2f}{r['rail']:7.1f}  {ok}{flag}")


HDR = (f"{'':<30}{'apogeo':>8}{'v_max':>7}{'Mach':>6}{'masa':>7}{'estr':>7}"
       f"{'marg':>6}{'m_bo':>6}{'riel':>7}  ok")
