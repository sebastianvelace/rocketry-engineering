// Measure R via the RC charging time constant.
// Wiring (rebuild the filter): GPIO25 --[R]--+--> GPIO34 ,  node --[C 10uF +]--(-)GND
#include <Arduino.h>
#define N 2000
static uint32_t ts[N];
static uint16_t val[N];
void setup(){
  Serial.begin(115200); delay(300);
  analogReadResolution(12); analogSetAttenuation(ADC_11db);
}
void loop(){
  dacWrite(25, 0); delay(600);          // fully discharge the capacitor
  uint32_t t0 = micros();
  dacWrite(25, 250);                     // step up to ~3.3 V
  for (int i=0;i<N;i++){                  // sample the charging curve as fast as possible
    ts[i]  = micros() - t0;
    val[i] = analogRead(34);
  }
  Serial.println("# BLOCK STEP");
  Serial.println("t_us,adc");
  for (int i=0;i<N;i++){ Serial.print(ts[i]); Serial.print(","); Serial.println(val[i]); }
  Serial.println("# END");
  delay(3000);
}
