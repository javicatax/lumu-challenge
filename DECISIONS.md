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

<!-- Por cada caso ambiguo: tu regla, por qué la elegiste, y en qué casos
falla. Al final di cuál decisión te dio más dudas. -->

- Duplicados: regla → ... | por qué → ... | dónde falla → ...
- Relojes equivocados: regla → ... | por qué → ... | dónde falla → ...
- Campos faltantes: regla → ... | por qué → ... | dónde falla → ...
- Archivos rotos / línea cortada: regla → ... | por qué → ... | dónde falla → ...

Decisión con la que me sentí menos seguro: ...

## 4. Evidencia

- Cómo sé que mi versión hace lo que creo: ...
- (Parte 2) Prueba de que el summary es idéntico con 1 y 8 workers: ...

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
