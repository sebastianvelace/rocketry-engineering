/*
 * DAQ Fase 2a -- Deterministic sampling: hardware timer ISR vs "soft" timing
 * -------------------------------------------------------------------------
 * Both methods try to sample at exactly 1 kHz. To make the difference visible,
 * every DISTURB_EVERY samples the loop is deliberately kept busy for DISTURB_US
 * microseconds (simulating real DAQ work, e.g. writing a chunk to an SD card).
 *
 *   USE_TIMER = 0 : the loop polls micros() to decide when to sample. While the
 *                   loop is busy, it CANNOT check the time -> the sample lands
 *                   late -> timing jitter.
 *
 *   USE_TIMER = 1 : a hardware timer fires an interrupt every 1 ms. An interrupt
 *                   PREEMPTS whatever the CPU is doing -- even the busy wait --
 *                   and stamps the exact time. Timing stays rock-solid.
 *
 * This is the whole reason interrupts exist. We record each sample's timestamp
 * and dump it so Python can measure the jitter of each method.
 *
 * Flash with USE_TIMER 0, capture; then USE_TIMER 1, capture; compare.
 */
#include <Arduino.h>

#define USE_TIMER    1        // <-- 0 = soft polling, 1 = hardware timer ISR
#define N_SAMPLES    400
#define TARGET_US    1000     // 1 kHz target
// Each loop iteration is delayed by a random amount up to HOG_MAX_US, simulating
// the unpredictable workload of a real DAQ (reading other sensors, writing SD...).
#define HOG_MAX_US   700

static const int ADC_PIN = 34;

static uint16_t val[N_SAMPLES];
static uint32_t ts[N_SAMPLES];       // timestamp of each sample, microseconds
static int      idx = 0;

#if USE_TIMER
hw_timer_t *timer = nullptr;
volatile uint32_t isrMicros = 0;
volatile bool     tick = false;
void IRAM_ATTR onTimer() {           // runs in interrupt context
  isrMicros = micros();              // exact moment the timer fired
  tick = true;
}
#else
uint32_t nextUs = 0;
#endif

void hogCpu(uint32_t us) {           // busy wait -- interrupts still fire
  uint32_t t0 = micros();
  while (micros() - t0 < us) { /* spin */ }
}

void setup() {
  Serial.begin(115200);
  delay(300);
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);
  dacWrite(25, 128);                 // constant ~1.65 V so the ADC value is steady

#if USE_TIMER
  timer = timerBegin(0, 80, true);           // 80 MHz / 80 = 1 MHz -> 1 tick = 1 us
  timerAttachInterrupt(timer, &onTimer, true);
  timerAlarmWrite(timer, TARGET_US, true);   // fire every TARGET_US, auto-reload
  timerAlarmEnable(timer);
#else
  nextUs = micros();
#endif
}

void takeSample(uint32_t stamp) {
  ts[idx]  = stamp;
  val[idx] = analogRead(ADC_PIN);
  idx++;
  if (idx >= N_SAMPLES) {
#if USE_TIMER
    Serial.println("# BLOCK METHOD=timer TARGET_US=1000");
#else
    Serial.println("# BLOCK METHOD=soft TARGET_US=1000");
#endif
    for (int i = 0; i < N_SAMPLES; i++) {
      Serial.print(i); Serial.print(",");
      Serial.print(val[i]); Serial.print(",");
      Serial.println(ts[i]);
    }
    Serial.println("# END");
    idx = 0;
    delay(2000);
#if !USE_TIMER
    nextUs = micros();
#endif
  }
}

void loop() {
  // Simulated unpredictable workload, run every loop iteration.
  hogCpu(random(0, HOG_MAX_US));

#if USE_TIMER
  // The timer ISR already stamped the exact time; we just store the sample.
  if (tick) { tick = false; takeSample(isrMicros); }
#else
  // Soft polling: we can only notice the deadline AFTER the hog finishes, so a
  // long hog makes this sample land late -> jitter.
  if ((int32_t)(micros() - nextUs) >= 0) {
    uint32_t stamp = micros();
    nextUs += TARGET_US;
    takeSample(stamp);
  }
#endif
}
