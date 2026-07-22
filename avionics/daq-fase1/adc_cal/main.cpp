/*
 * DAQ Fase 2c -- ADC characterization & calibration
 * -------------------------------------------------
 * Every measuring instrument lies a little. Before trusting the ADC to record a
 * thrust or pressure curve, we must know HOW it lies and how to correct it.
 *
 * Method: sweep the DAC across its full range (0..255 -> ~0..3.3 V) and, at each
 * step, read the ADC two ways:
 *   - raw    : analogRead() -> a 0..4095 count, converted naively as count/4095*3.3
 *   - cal    : analogReadMilliVolts() -> the ESP32's factory (eFuse) calibration
 *
 * We also record the spread (std dev) of repeated reads = the electrical noise.
 * Python then plots the transfer curve, shows the nonlinearity, and fits our own
 * correction on top.
 *
 * Wiring: same single jumper, GPIO25 (DAC) -> GPIO34 (ADC).
 */
#include <Arduino.h>
#include <math.h>

static const int DAC_PIN = 25, ADC_PIN = 34;
static const int AVG = 64;          // reads averaged per DAC step

void setup() {
  Serial.begin(115200);
  delay(300);
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);
}

void sweep() {
  Serial.println("# BLOCK ADC_CAL");
  Serial.println("dac,dac_mv_ideal,adc_raw_mean,adc_raw_std,adc_cal_mv");

  for (int dac = 0; dac <= 255; dac++) {
    dacWrite(DAC_PIN, dac);
    delay(3);                        // let the voltage settle

    // Average AVG raw counts and AVG calibrated millivolts; also raw std dev.
    double sum = 0, sumSq = 0, sumCal = 0;
    for (int k = 0; k < AVG; k++) {
      int raw = analogRead(ADC_PIN);
      sum   += raw;
      sumSq += (double)raw * raw;
      sumCal += analogReadMilliVolts(ADC_PIN);
    }
    double mean = sum / AVG;
    double var  = sumSq / AVG - mean * mean;
    double std  = var > 0 ? sqrt(var) : 0;
    double calMv = sumCal / AVG;

    double dacIdealMv = dac / 255.0 * 3300.0;   // DAC's nominal output

    Serial.print(dac);            Serial.print(",");
    Serial.print(dacIdealMv, 1);  Serial.print(",");
    Serial.print(mean, 1);        Serial.print(",");
    Serial.print(std, 2);         Serial.print(",");
    Serial.println(calMv, 1);
  }
  Serial.println("# END");
}

void loop() {
  sweep();           // repeat the whole sweep so the PC always catches a block
  delay(3000);
}
