# DECISIONS.md

Documento de decisiones y evidencia del reto de intake triage de Lumu.
Cubre Parte 1 (corrección de bugs) y Parte 2 (paralelización).

## 1. Esfuerzo y alcance

- Qué partes hice: Parte 1 [Completa] / Parte 2 [Completa]
- **Tiempo aproximado dedicado:**
  - Parte 1 (análisis + correcciones + tests): [2.5 horas]
  - Parte 2 (paralelización + tests + medición): [2 horas]
  - Documentación (este archivo): [0.5 horas]
- **Qué dejé fuera a propósito:**
  - Ventana temporal en la regla de duplicados (complejidad en Parte 2
    sin ganancia clara).
  - Almacenar líneas malformadas (alcance y tiempo para el reto).
  - Filtrado de IPs especiales — necesitaría
    datos reales de Lumu para decidir qué es un "cliente" válido.
  - Alertas de producción por tasa de rechazos o por tasa de
    `clock_suspect`.

## 2. Qué estaba mal

<!-- Por cada problema: qué es, y si lo encontraste LEYENDO el código o
CORRIENDO el servicio. -->

- Problema 1: Mal contadores
 Suma de todos los registros por verdict deberia ser igual a todos los procesados.
 sum(by_verdict.values()) = 4684  ≠  processed = 4597
- Problema 2: No funciona unique events
  Son los misma cantidad de registros que los unicos - sospechoso
- Problema 3: Definir el received_at
- Problema 4: Definir IP valida
- Problema 5: Revisar event_time y received_at, mismo formato
- Problema 6: Validacion : 1990 < as_seconds.year < 2035 y revisar: datetime.fromtimestamp(n / 1000.0, tz=timezone.utc)
- Problema 7: Definir hora del  de los registros (Cuando hay relojes configurados en el futuro)
- Problema 8: except Exception, return None - fallo silencioso
- Problema 9: Definir si se truncan lineas o se ignoran o se registra el fallo
- Problema 10: Orden procesamiento de archivos
- Problema 11: Memoria y tiempos de procesamiento con gran cantidad de datos
- Problema 12: Medicion de tiempos

## 3. Decisiones

Cuatro decisiones centrales, cada una con su regla, su justificación y
su costo.

### 3.1 Duplicados

**Regla.** Dos records describen el mismo evento si comparten
`(collector_id, event_time, client_ip, query, verdict)`. Excluyo
`received_at` del fingerprint porque es metadata de transporte, no
identidad del evento.

**Por qué.** Un retry de red reenvía el mismo evento con distinto
`received_at`. Incluirlo en el fingerprint hace que cada retry parezca
un evento nuevo, y `unique_events` se vuelve una copia de `processed`.
Sin `received_at`, los retries colapsan correctamente.

**Dónde falla.** Un script de análisis (`scripts/analyze_collapses.py`)
clasifica los 371 grupos de records con fingerprint compartido en el
dataset:

- **224 son retries de red** (gap de `received_at` > 1 s). Colapsarlos
  es correcto.
- **147 son gemelos genuinos** (gap ≤ 1 s): dos eventos reales del
  mismo dispositivo en el mismo segundo. Colapsarlos es **incorrecto**:
  subestimo ~147 eventos. `unique_events` da 4487, cuando el "ideal"
  sería ~4634.

**Costo aceptado.** La alternativa (ventana temporal de 1–2 s)
distinguiría retries de gemelos, pero requiere estado con timestamps,
lo que complica la Parte 2 sin ganancia clara para el caso de uso
principal. Además, subcontar eventos (alertas faltantes) es menos grave
que sobrecontar (alertas duplicadas al cliente).

### 3.2 Relojes equivocados

**Regla.** Si `|event_time − received_at|` supera los umbrales, marco
`clock_suspect = True`, pero **no rechazo el record ni reemplazo
`event_time`**. Se preserva el original; la detección debe usar
`received_at` cuando el flag está activo.

**Umbrales.**
- `MAX_FUTURE_CLOCK_SKEW = 5 min` (un `ts` en el futuro).
- `MAX_PAST_CLOCK_SKEW = 24 h` (un `ts` muy en el pasado).

**Por qué.** El generador simula un firmware bug que pone el año 2075.
Sin detección, los consumidores ven eventos con 50 años de skew. Con el
flag, la detección puede decidir. Reemplazar `event_time` destruiría la
información original, contradiciendo "whatever arrives is all you will
ever get".

**Dónde falla.** Sobre el dataset:

- `MAX_FUTURE_CLOCK_SKEW` (5 min) se activa **499 veces**.
- `MAX_PAST_CLOCK_SKEW` (24 h) **no se activa ni una vez**. El delta
  mínimo observado es **−51.4 s**. Este umbral es una **válvula de
  seguridad** para un escenario que el dataset no ejercita.
- El `max delta` es ~1.6 × 10⁹ s (≈ 51 años): es el firmware bug de
  2075, no un skew realista.

**Costo aceptado.** Los umbrales (±5 min, −24 h) son juicio, no verdad.
Deberían calibrarse con datos reales de producción.

### 3.3 Campos faltantes

**Regla.** Distingo identidad de atributos:

- **Identidad:** `ts`, `collector_id`. Sin ellos el record no es
  atribuible. **Rechazo.**
- **Atributos:** `client_ip`, `query`, `verdict`. Sin ellos el record
  sigue siendo evidencia. **Acepto con `None` y flag de calidad.**

**Por qué.** El reto dice que no podemos pedir reenvío. Un record sin
`client_ip` sigue siendo señal de actividad. Rechazarlo es perder
evidencia.

**Dónde falla.** Sobre el dataset:

- 174 records entran con `client_ip = None`. No entran a `unique_ips`.
  La detección debe manejar `None`.
- 0 records con `query = None` o `verdict = None` en este dataset (el
  generador siempre los provee).

### 3.4 Archivos rotos / línea cortada

**Regla.** Una línea malformada se **descarta y se cuenta**; el archivo
**nunca se aborta**. NDJSON es "una línea, un record".

**Por qué.** Abortar el archivo por una línea mala tiraría N-1 records
válidos. La filosofía del reto ("whatever arrives is all you will ever
get") no permite esa pérdida.

**Dónde falla.** Sobre el dataset:

- 134 líneas malformadas descartadas (JSON truncado por el generador).
- 0 líneas clasificadas como `not_a_dict` (el generador no produce
  arrays ni números sueltos).

**Costo aceptado.** Los records malformados se pierden (inevitable).
Pero ahora son visibles en `Rejections`, así que el summary explica la
diferencia entre líneas del archivo y records procesados.

### 3.5 Paralelización (Parte 2)

**Regla.** Paralelizo con `ProcessPoolExecutor`. Cada archivo se procesa
en un worker independiente. Cada worker produce un `Summary` parcial
sin estado compartido. Los parciales se mergean con `Summary.merge`,
que es conmutativo. El sharding es **round-robin** (implícito en
`pool.map`), **no por collector**.

**Por qué `ProcessPoolExecutor` y no otras opciones** 
- **Threads (`ThreadPoolExecutor`):** CPython tiene el GIL. Los threads
  no ejecutan bytecode Python en paralelo.
- **`ProcessPoolExecutor`:** paralelismo real de CPU. Está en la
  stdlib (`concurrent.futures`). Es el enfoque adecuado para trabajo
  CPU-bound. Elegido.

**Costo.** El merge final en el proceso padre es secuencial. Con 300
archivos, es una fracción pequeña del tiempo total. El overhead de
pickling de los `Summary` parciales es de unos MB por worker.

**Resultados.** 5.05× más rápido con 8 workers. Output idéntico byte a
byte con 1, 2, 4 y 8 workers, y con cualquier orden de archivos. Ver
secciones 4.4 y 5.

### Decisión con la que me sentí menos seguro

**Los umbrales de clock (±5 min futuro, −24 h pasado).** Son números
elegidos a ojo, sin datos reales de Lumu sobre distribución de
latencias. El de −24 h **no se activa con el dataset**, así que es una
válvula de seguridad sin validar empíricamente. Con datos de
producción, los recalibraría.

## 4. Evidencia

### 4.1 Tests

30 tests, todos verdes:

```
Ran 30 tests in 0.175s

OK
```

- **24 tests** en `intake/tests/test_intake.py` (Parte 1: los 13 bugs).
- **6 tests** en `intake/tests/test_parallel.py` (Parte 2: invariancia,
  conmutatividad del merge, pureza de `_process_file`).

Cada test que captura un bug referencia la decisión correspondiente en
su docstring.

### 4.2 Corrida sobre el dataset del generador (seed 42, 4992 líneas)

```
=== intake summary ===

Volume
  records processed:       4858
  unique events:           4487
  unique client IPs:       4221

Quality flags
  invalid client_ip:       87
  missing client_ip:       174
  missing query:           0
  missing verdict:         0
  missing received_at:     0
  clock suspect:           499

By verdict
  allow: 2924
  block: 981
  monitor: 953

By collector
  col-01: 344
  col-02: 334
  col-03: 2633
  col-04: 295
  col-05: 294
  col-06: 307
  col-07: 303
  col-08: 348

Rejections
  malformed_line: 134
```

**Verificaciones clave:**

| Chequeo | Resultado |
|---|---|
| `sum(by_verdict) == processed` | 2924 + 981 + 953 = **4858** == 4858 |
| `sum(by_collector) == processed` | suma de los 8 = **4858** |
| `unique_events < processed` | 4487 < 4858 (dedup funciona) |
| `clock_suspect > 0` | 499 |
| `Rejections` presente | `malformed_line: 134` |

### 4.3 Evidencia reproducible

`scripts/analyze_collapses.py` reproduce el análisis de duplicados
(sección 3.1):

```bash
python3 scripts/analyze_collapses.py
```

Salida esperada:

```
Groups with >1 record: 371
Likely retries (gap > 1.0s): 224
Likely twins (gap <= 1.0s): 147
```

La clasificación es heurística (los retries del generador tienen gap
de 3–20 s; los gemelos de 0.02–0.9 s). El orden de magnitud es estable
ante variaciones del umbral.

### 4.4 Parte 2 — Invariancia del output

El reto exige:

> *"The summary output must be exactly the same with 1 worker and with
> 8 workers. It must also be the same no matter which order the files
> are processed in."*

**Verificación realizada.** Sobre el dataset `./incoming_large`
(~1.2M records, 300 archivos):

```bash
python3 -m intake.reader --dir ./incoming_large --workers 1 > /tmp/large-w1.txt
python3 -m intake.reader --dir ./incoming_large --workers 8 > /tmp/large-w8.txt
diff /tmp/large-w1.txt /tmp/large-w8.txt && echo "IDENTICAL 1 vs 8 (large)"
```

Resultado:

```
IDENTICAL 1 vs 8 (large)
```

El `diff` está vacío. El output es idéntico byte a byte con 1 y con 8
workers.

**Verificación de orden.** Sobre el mismo dataset, con `--shuffle`
(semilla fija para reproducibilidad):

```bash
python3 -m intake.reader --dir ./incoming_large --workers 1 --shuffle > /tmp/large-shuf.txt
diff /tmp/large-w1.txt /tmp/large-shuf.txt && echo "ORDER INDEPENDENT"
```

Resultado:

```
ORDER INDEPENDENT
```

El `diff` está vacío. El output es idéntico con archivos en orden
alfabético o en orden aleatorio.

**Por qué funciona.** Dos propiedades del diseño garantizan la
invariancia:

1. **El fingerprint es per-collector.** Incluye `collector_id`, así
   que dos records de distintos collectors nunca colapsan. Los
   `Summary` parciales de distintos workers no pueden tener
   fingerprints que deban colapsar entre sí.
2. **El merge es conmutativo.** Todas las operaciones de `merge`
   son sumas (conmutativas) o uniones de sets (conmutativas). El
   orden de los merges no afecta el resultado.

**Tests automatizados.** Además del `diff` manual, cuatro tests en
`intake/tests/test_parallel.py` cubren:

- `test_same_output_1_vs_8_workers` — mismo output con 1 y 8 workers.
- `test_same_output_shuffled` — mismo output con shuffle.
- `test_same_output_8_workers_shuffled` — mismo output con 8 workers
  y shuffle.
- `test_merge_is_commutative` — `a.merge(b)` == `b.merge(a)`.

---

## 5. Rendimiento

### Método de medición

- **Dataset:** `python3 generate.py --large --out ./incoming_large`.
  ~1.2M records, 300 archivos, ~200 MB en disco.
- **Comando:**
  ```bash
  for w in 1 2 4 8; do
      python3 -m intake.reader --dir ./incoming_large --workers $w --timing \
          > /tmp/large-$w.txt 2> /tmp/large-$w.time
  done
  ```
- **Tiempo:** `time.perf_counter()` dentro del servicio, reportado a
  `stderr` con `--timing`. Mide solo el bucle de procesamiento, no
  el arranque del intérprete ni la impresión del summary.
- **Hardware:**
  - CPU: AMD Ryzen 7 7730U (8 cores físicos, 16 hilos con SMT)
  - RAM: 14 GiB (3.7 GiB libres durante la medición)
  - Disco: NVMe SSD (`/dev/nvme0n1p5`)
  - SO: Linux
- **Corridas:** una por configuración. El dataset es determinístico
  (seed 42). El sistema estaba en reposo durante la medición.

### Resultados

| Workers | Tiempo (s) | Speedup vs 1 | Eficiencia por worker |
|---|---|---|---|
| 1 | 17.187 | 1.00× | 100 % |
| 2 | 9.771 | 1.76× | 88 % |
| 4 | 5.825 | 2.95× | 74 % |
| 8 | 3.406 | **5.05×** | 63 % |

### Interpretación

- **Factor de mejora con 8 workers: 5.05×.** El reto menciona que "6× más
  rápido pero con un número distinto no es una solución". Nosotros
  somos 5.05× más rápido **con el mismo número**. La invariancia se
  verificó con `diff` byte a byte (ver sección 4.4).
- **Escalamiento sublineal.** El factor de mejora no es 8× con 8 workers.
  Razones:
  - **SMT.** La máquina tiene 8 cores físicos pero 16 hilos lógicos.
    Con 8 workers, algunos cores ejecutan 2 workers. Los dos workers
    comparten recursos del mismo core físico.
  - **Overhead de pickling.** Cada `Summary` parcial se serializa
    entre worker y proceso padre. El dataset grande tiene ~1M
    fingerprints únicos; los parciales son de unos MB.
  - **Contención de I/O.** Los 8 workers leen del mismo NVMe. Es
    rápido, pero no infinito.
  - **Merge secuencial.** El merge final de los 8 parciales ocurre en
    el proceso padre, un solo hilo.
  - **Arranque y parada del pool.** `ProcessPoolExecutor` tarda unos
    100–300 ms en crear y cerrar los procesos.
- **Umbral práctico: 4 workers.** Con 4 workers, la eficiencia sigue
  siendo 74 % y el factor de mejora es 2.95×. Con 8, la eficiencia baja a 63 %.
  Para producción, 4 workers es el punto dulce entre velocidad y
  eficiencia.

### Lo que demuestra esto

- **El paralelismo funciona.** 5× más rápido con 8 workers sobre 1.
- **La corrección se mantiene.** El output es idéntico byte a byte.
- **El diseño es sólido.** El merge conmutativo y el fingerprint
  per-collector permiten paralelizar sin coordinación.

---

## 6. Lo que dejé sin hacer

- **Ventana temporal para duplicados** Distinguiría retries de gemelos
  genuinos, pero requiere estado con timestamps. Complica la Parte 2
  sin ganancia clara para el reto.
- **Almacén de rechazados** Guardar líneas malformadas en un archivo
  aparte ayudaría a diagnosticar bugs de collectors en producción.
- **Filtrado de IPs especiales.** El validador acepta `0.0.0.0`,
  `127.0.0.1`, multicast y link-local. Son IPv4 válidas. Decidir
  cuáles son "clientes" requiere contexto de negocio que no tengo.
- **Alertas por tasa de rechazos.** Un pico de `malformed_line` en un
  collector específico es señal de bug. Hoy no se emite alerta.
- **Umbrales de clock calibrados.** Los valores (±5 min, −24 h) son
  juicio. Deberían calibrarse con datos reales.
- **Umbral de archivo corrupto.** No abortamos archivos con muchas
  líneas malas. Un umbral (>50 %) sería señal de corrupción de
  transferencia.
- **Distinguir ausente de tipo incorrecto.** `_clean_attribute_string`
  convierte ambos en `None`. Un contador separado por tipo de problema
  daría más visibilidad.
- **Agrupar contadores de calidad por collector.** `clock_suspect` y
  `missing_client_ip` son totales. Agruparlos por collector diría qué
  collector tiene problemas.
- **Dead lock protection en el pool.** No hay timeout en
  `ProcessPoolExecutor`. Si un worker se cuelga, el proceso padre
  espera indefinidamente. En producción, un timeout sería prudente.

## 7. Herramientas de IA

Uso de IA verificada:

- **Leyendo el código** para confirmar que el análisis era correcto.
- **Corriendo el servicio** sobre el dataset para verificar los
  números antes/después.
- **Escribiendo tests** que capturan los bugs antes de arreglarlos
  (los tests fallan con el código original, pasan con el arreglado).
- **Midiendo con un script propio** (`scripts/analyze_collapses.py`)
  los costos de las decisiones.
- **Verificando la invariancia** con `diff` byte a byte entre distintos
  números de workers y distintos órdenes de archivos.
- Revisión del uso de `argparse` para los nuevos flags, y del diseño
  de `run_parallel` con `pool.map` (round-robin implícito).

Los números de este documento son **medidos**, no afirmados.
Cualquiera puede reproducirlos con los scripts del repo.
