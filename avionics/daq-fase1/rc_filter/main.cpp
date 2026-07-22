/*
 * DAQ Fase 3 -- RC anti-aliasing filter: measure its frequency response (Bode)
 * ---------------------------------------------------------------------------
 * A first-order RC low-pass filter now sits between the DAC and the ADC:
 *     GPIO25 --[ R=220 ]--+--> GPIO34
 *                         |
 *                       [ C=10uF ]
 *                         |
 *                        GND
 * Theoretical cutoff: fc = 1/(2*pi*R*C) ~= 72 Hz.
 *
 * This firmware sweeps the DAC sine across many frequencies and, at each,
 * measures the amplitude that survives at the ADC. Low frequencies pass; high
 * frequencies are attenuated. Plotting amplitude vs frequency = the Bode plot,
 * and the -3 dB point should land near 72 Hz.
 *
 * It also prints a one-shot DC sanity check at startup: with a steady DAC, the
 * ADC should read the full voltage (the cap is "open" at DC), proving the wiring.
 */
#include <Arduino.h>
#include <math.h>

static const int DAC_PIN = 25, ADC_PIN = 34;

// Frequencies to test (Hz)
static const float freqs[] = {2, 5, 10, 20, 30, 50, 70, 100, 150,
                              200, 300, 500, 700, 1000, 1500, 2000};
static const int NF = sizeof(freqs) / sizeof(freqs[0]);

int dcCheck() {
  dacWrite(DAC_PIN, 200);          // ~2.6 V steady
  delay(50);
  long s = 0;
  for (int k = 0; k < 64; k++) s += analogRead(ADC_PIN);
  return s / 64;
}

void setup() {
  Serial.begin(115200);
  delay(300);
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);
}

// Drive a sine of frequency f and return the peak-to-peak amplitude seen at the
// ADC (in counts), after letting the filter settle.
int measureAmplitude(float f) {
  const uint32_t SETTLE_US = 40000;    // let the RC filter reach steady state
  // Measure over at least 3 full cycles (so low frequencies aren't clipped).
  uint32_t windowUs = (uint32_t)(3e6f / f);
  if (windowUs < 120000) windowUs = 120000;
  const uint32_t WINDOW_US = windowUs;
  int lo = 4095, hi = 0;

  uint32_t t0 = micros();
  while (micros() - t0 < SETTLE_US + WINDOW_US) {
    float t = (micros() - t0) / 1e6f;
    int dv = (int)(128 + 100 * sinf(2.0f * PI * f * t));
    dacWrite(DAC_PIN, dv);
    int v = analogRead(ADC_PIN);
    if (micros() - t0 > SETTLE_US) {     // ignore the settling transient
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
  }
  return hi - lo;
}

void sweep() {
  Serial.print("# DC_CHECK adc="); Serial.print(dcCheck());
  Serial.println("  (expect ~2900-3100 if wired OK)");
  Serial.println("# BLOCK BODE R=220 C=10uF");
  Serial.println("freq_hz,amp_counts");
  for (int i = 0; i < NF; i++) {
    int amp = measureAmplitude(freqs[i]);
    Serial.print(freqs[i], 0); Serial.print(",");
    Serial.println(amp);
  }
  Serial.println("# END");
}

void loop() {
  sweep();
  delay(3000);
}
