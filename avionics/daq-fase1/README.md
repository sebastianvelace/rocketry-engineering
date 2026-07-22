# DAQ Fase 1 — Muestreo y aliasing con la ESP32

Primer proyecto del sistema de adquisición de datos (DAQ) del banco de pruebas.
La ESP32 genera una senoidal conocida en su DAC y la muestrea con su ADC, para
ver el teorema de Nyquist y el aliasing en la práctica.

## Conexión (un solo cable)

```
   ESP32
  ┌─────────┐
  │  GPIO25 ●───────┐   (DAC, salida analógica)
  │         │       │   jumper
  │  GPIO34 ●───────┘   (ADC, entrada analógica)
  └─────────┘
```

Un jumper de GPIO25 a GPIO34. Nada más — los dos pines comparten la tierra
interna de la placa.

> Solo el ESP32 clásico (WROOM/WROVER) tiene DAC en GPIO25/26. Si tenés un
> ESP32-S3 o -C3, no hay DAC y este demo no genera señal (avisame y lo adapto).

## Uso

Todos los comandos desde esta carpeta (`~/rocketry-avionics/daq-fase1`).

1. **Conectá** la ESP32 por USB y hacé la conexión del jumper de arriba.

2. **Cargá el firmware:**
   ```
   ./pio.sh run -t upload
   ```
   (Si falla por permisos del puerto, desconectá y reconectá el USB.)

3. **Graficá una captura:**
   ```
   ../.pio-venv/bin/python plot.py
   ```
   Genera `capture.png` y abre la ventana con la señal muestreada.

## El experimento

Editá las dos líneas de arriba en `src/main.cpp`, recompilá con
`./pio.sh run -t upload`, y compará:

| Caso | F_SIGNAL | F_SAMPLE | Qué vas a ver |
|------|----------|----------|----------------|
| Limpio (sobre Nyquist) | 50 Hz  | 1000 Hz | La senoidal real de 50 Hz |
| **Aliasing** (bajo Nyquist) | **950 Hz** | 1000 Hz | Una senoidal **falsa** de 50 Hz |

**La lección:** los dos gráficos se ven IDÉNTICOS. Desde las muestras solas no
podés distinguir una señal real de 50 Hz de una de 950 Hz mal muestreada. Ese
fantasma es el aliasing, y es por eso que en tu cohete la frecuencia de muestreo
del DAQ no es un detalle — decide si medís la verdad o un espejismo.

## Para monitorear el serial crudo (sin graficar)
```
./pio.sh device monitor
```
(salir con Ctrl+C)
