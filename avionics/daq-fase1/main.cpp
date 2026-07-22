/*
 * DAQ Fase 1 -- Sampling & aliasing demo on ESP32
 * -------------------------------------------------
 * The board generates a known sine wave on its DAC (GPIO25) and samples it back
 * on its ADC (GPIO34). By choosing F_SIGNAL and F_SAMPLE you can watch the
 * Nyquist-Shannon theorem and aliasing happen for real.
 *
 * WIRING: a single jumper from GPIO25 to GPIO34. Nothing else -- both pins share
 * the board's ground internally.
 *
 * NOTE: only the classic ESP32 (WROOM/WROVER) has a DAC on GPIO25/26. On an
 * ESP32-S3 or -C3 there is no DAC and this exact demo won't drive a signal.
 *
 * The timing here is "soft" (scheduled with micros() in loop) -- perfect for
 * seeing the concept. Fase 2 replaces it with a hardware-timer ISR + DMA for
 * jitter-free sampling, which is what a real thrust DAQ needs.
 */
#include <Arduino.h>
#include <math.h>

// ---- Experiment parameters: CHANGE THESE, re-flash, and compare ------------
// Clean case (well above Nyquist):   F_SIGNAL=50,  F_SAMPLE=1000  -> real 50 Hz
// Aliasing case (below Nyquist):     F_SIGNAL=950, F_SAMPLE=1000  -> FAKE 50 Hz
// The punchline: both plots look identical. From the samples alone you cannot
// tell a real 50 Hz sine from an aliased 950 Hz sine. That is aliasing.
static const float F_SIGNAL = 950.0f;    // Hz, the sine we generate on the DAC
static const float F_SAMPLE = 1000.0f;  // Hz, how fast we sample the ADC

// ---- Fixed hardware / demo constants ---------------------------------------
static const int   DAC_PIN        = 25;      // DAC1 output
static const int   ADC_PIN        = 34;      // input-only ADC pin
static const float DAC_UPDATE_HZ  = 20000.0; // DAC refresh rate (smooth sine)
static const int   N_SAMPLES      = 200;     // samples per printed block

// Derived periods, in microseconds
static const uint32_t DAC_PERIOD_US    = (uint32_t)(1e6 / DAC_UPDATE_HZ);
static const uint32_t SAMPLE_PERIOD_US = (uint32_t)(1e6 / F_SAMPLE);

// Sine lookup table for the DAC (0..255, centered at 128)
static const int LUT_SIZE = 256;
static uint8_t   sineLut[LUT_SIZE];

// Sampling buffer
static uint16_t sampleBuf[N_SAMPLES];
static int      sampleIdx = 0;

// Schedulers
static uint32_t nextDacUs    = 0;
static uint32_t nextSampleUs = 0;
static float    dacPhase     = 0.0f;             // radians
static const float DAC_PHASE_STEP = 2.0f * PI * F_SIGNAL / DAC_UPDATE_HZ;

void buildSineLut() {
  for (int i = 0; i < LUT_SIZE; i++) {
    float angle = 2.0f * PI * i / LUT_SIZE;
    sineLut[i] = (uint8_t)(128 + 100 * sinf(angle));  // ~0.3V .. ~3.0V swing
  }
}

void setup() {
  Serial.begin(115200);
  delay(300);
  buildSineLut();

  analogReadResolution(12);          // 0..4095
  analogSetAttenuation(ADC_11db);    // full ~0..3.3V input range

  Serial.println();
  Serial.println("# DAQ Fase 1 ready");
  Serial.print("# F_SIGNAL="); Serial.print(F_SIGNAL);
  Serial.print(" Hz  F_SAMPLE="); Serial.print(F_SAMPLE);
  Serial.print(" Hz  Nyquist="); Serial.print(F_SAMPLE / 2.0f);
  Serial.println(" Hz");
  if (F_SIGNAL > F_SAMPLE / 2.0f) {
    Serial.println("# WARNING: F_SIGNAL is ABOVE Nyquist -> expect ALIASING");
  }

  uint32_t now = micros();
  nextDacUs = now;
  nextSampleUs = now;
}

void loop() {
  uint32_t now = micros();

  // 1) Refresh the DAC to trace the analog sine, independent of sampling.
  if ((int32_t)(now - nextDacUs) >= 0) {
    nextDacUs += DAC_PERIOD_US;
    dacPhase += DAC_PHASE_STEP;
    if (dacPhase >= 2.0f * PI) dacPhase -= 2.0f * PI;
    int lutIndex = (int)(dacPhase / (2.0f * PI) * LUT_SIZE) & (LUT_SIZE - 1);
    dacWrite(DAC_PIN, sineLut[lutIndex]);
  }

  // 2) Sample the ADC at F_SAMPLE.
  if ((int32_t)(now - nextSampleUs) >= 0) {
    nextSampleUs += SAMPLE_PERIOD_US;
    sampleBuf[sampleIdx++] = analogRead(ADC_PIN);

    if (sampleIdx >= N_SAMPLES) {
      // Dump one block as CSV: index,value
      Serial.print("# BLOCK F_SIGNAL="); Serial.print(F_SIGNAL);
      Serial.print(" F_SAMPLE="); Serial.print(F_SAMPLE);
      Serial.print(" N="); Serial.println(N_SAMPLES);
      for (int i = 0; i < N_SAMPLES; i++) {
        Serial.print(i); Serial.print(","); Serial.println(sampleBuf[i]);
      }
      Serial.println("# END");
      sampleIdx = 0;
      delay(1500);                 // pause so you can read/plot one block at a time
      nextSampleUs = micros();     // resync after the pause
      nextDacUs = nextSampleUs;
    }
  }
}
