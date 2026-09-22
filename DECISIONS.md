# DECISIONS.md

<!-- Opcional: si terminas usando la "shorter option" (arreglar solo el problema
más grave + documento de diseño), dilo aquí arriba, antes de todo lo demás. -->

## 1. Esfuerzo y alcance

- Qué partes hice: Parte 1 [ ] / Parte 2 [ ]
- Tiempo aproximado dedicado: ...
- Qué dejé fuera a propósito: ...

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

**Limitación no medible con el dataset.** Dos devices detrás del mismo
NAT con la misma IP interna haciendo la misma query al mismo tiempo
colapsan. El generador no produce este caso (todas las IPs son únicas
por device).

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

**Costo aceptado.** Los consumidores deben manejar `None` en los
atributos. Además, no se coerciona `str(None)`: los valores `None` son
explícitos, no strings disfrazadas.

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

### Decisión con la que me sentí menos seguro

**Los umbrales de clock (±5 min futuro, −24 h pasado).** Son números
elegidos a ojo, sin datos reales de Lumu sobre distribución de
latencias. El de −24 h **no se activa con el dataset**, así que es una
válvula de seguridad sin validar empíricamente. Con datos de
producción, los recalibraría.


## 4. Evidencia

### 4.1 Tests

24 tests en `intake/tests/test_intake.py`, todos verdes:

```
Ran 24 tests in 0.001s

OK
```

Cada test que captura un bug referencia la decisión correspondiente en
su docstring.

### 4.2 Corrida sobre el dataset del generador (seed 42)

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

## 5. Rendimiento

- Antes: ... (tiempo, cómo lo medí)
- Después: ... (tiempo, cómo lo medí)
- Método de medición: ...

## 6. Lo que dejé sin hacer

- ...

## 7. Herramientas de IA

- Qué usé y dónde: ...
- Qué se equivocaron / qué rechacé: ...
- Qué se les pasó: ...
- Cómo verifiqué lo que me dieron: ...
