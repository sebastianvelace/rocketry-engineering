#!/usr/bin/env python3
import sys, glob, numpy as np, serial, matplotlib.pyplot as plt
C = 10e-6
port = sys.argv[1] if len(sys.argv)>1 else (glob.glob('/dev/ttyUSB*')+glob.glob('/dev/ttyACM*'))[0]
s = serial.Serial(port,115200,timeout=15); rows=[]; cap=False
import time; t=time.time()
while time.time()-t<12:
    l=s.readline().decode(errors='ignore').strip()
    if l.startswith('# BLOCK STEP'): rows=[]; cap=True
    elif l=='# END' and cap: break
    elif cap and ',' in l and not l[0].isalpha():
        try: rows.append([float(x) for x in l.split(',')])
        except: pass
s.close()
d=np.array(rows); t_us=d[:,0]; adc=d[:,1]
final=np.mean(adc[t_us>t_us.max()*0.8])          # steady-state value
start=adc[0]
target=start+0.632*(final-start)                  # 63.2% point = tau
tau_us=np.interp(target, adc, t_us)               # time to reach it
R=tau_us*1e-6/C
print(f"Final ADC   : {final:.0f}")
print(f"63% point   : {target:.0f} at t = {tau_us:.0f} us")
print(f"tau         : {tau_us/1000:.2f} ms")
print(f"C (assumed) : {C*1e6:.0f} uF")
print(f"=> R = tau/C = {R:.0f} ohms")
verdict = "220 ohm" if R<800 else ("3.3k ohm" if R<8000 else "something else")
print(f"=> resistor is most likely: {verdict}")
plt.figure(figsize=(9,4)); plt.plot(t_us/1000, adc, '.', ms=2)
plt.axhline(target, color='r', ls='--', alpha=.6, label=f'63% (tau={tau_us/1000:.1f}ms -> R={R:.0f}ohm)')
plt.xlabel('time (ms)'); plt.ylabel('ADC counts'); plt.title('Capacitor charging curve -> R from RC time constant')
plt.legend(); plt.grid(alpha=.3); plt.tight_layout(); plt.savefig('step.png',dpi=110)
print('Saved step.png')
