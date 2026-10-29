# Bitácora de Incidencias y Diagnóstico — AgroVisión

> **Propósito:** Registro histórico y cronológico de bugs, hipótesis de diagnóstico, resoluciones técnicas y lecciones aprendidas.
> **Ámbito:** Cualquier aplicación con arquitectura modular desacoplada (Frontend, Backend/API, Workers/Queues, Base de Datos, Caché).
> **Instrucciones:** Agrega una nueva entrada al principio del documento (orden cronológico inverso) por cada incidente, bug crítico o refactor de arquitectura resuelto.

---

## 2026-10-20 — Gate global de F02 bloqueado por deuda preexistente de F01 — Backend / DB / Tests

### 1. Síntoma Observado / Reporte
Al ejecutar la validación de cierre de la Fase 2, los tests propios de la fase pasan, pero la suite unitaria completa y `ruff check .` fallan.
*   **Qué falló:** `tests/unit/test_profiles.py` falla con `KeyError: 'DATABASE_URL'`; `ruff check .` reporta 11 incidencias E402/E501 en `backend/db/repositories.py` y `backend/services/weather.py`.
*   **Entorno:** Local (worktree `F02-esquema-ddl-migraciones-versionadas`, basada en `main` 58a866d).
*   **Logs / Traza de Error:**
    ```text
    KeyError: 'DATABASE_URL' (tests/unit/test_profiles.py)
    E501 Line too long -> backend/db/repositories.py:131,438,465
    E402 Module level import not at top of file -> backend/services/weather.py:31-35
    E501 Line too long -> backend/services/weather.py:106,164,190,210
    ```

### 2. Hipótesis de Diagnóstico
1.  **Hipótesis 1:** El código de F02 introdujo las fallas. → *Resultado:* Descartada; `git diff` de F02 no toca `repositories.py` ni `weather.py`, y los tests de F02 pasan aislados.
2.  **Hipótesis 2:** Las fallas son deuda preexistente que la Fase 1 debe resolver. → *Resultado:* Confirmada; el worktree `F01-estabilizacion-backend-robustez-tests` tiene cambios sin commitear exactamente en esos archivos.

### 3. Causa Raíz
La rama de F02 se creó desde `main` (58a866d), que aún no incluye la corrección de linters y del aislamiento de `DATABASE_URL` de la Fase 1. Por eso el gate global del Apéndice A no puede estar verde aunque el alcance de F02 sí lo esté.

### 4. Resolución e Implementación
1.  **Alcance F02:** se validó el DoD específico de F02 (tests unitarios/integración de migraciones, Ruff de archivos tocados, docs de DB/arquitectura y tablero).
2.  **Diferimiento:** la corrección de `repositories.py`, `weather.py` y `test_profiles.py` queda en la rama F01; no se duplica en F02 para evitar conflictos.
3.  **Registro:** se emitieron los recibos de DoD en `docs/logs/recibos/dod-receipts.jsonl` con la observación de la deuda global.

### 5. Verificación y Mediciones
*   **Pruebas F02:** `pytest tests/unit/test_migrations.py` → 11 passed; `pytest tests/integration/test_migrations.py tests/integration/test_db.py` contra PostGIS 16 → 6 passed.
*   **Lint F02:** `ruff check backend/db/migrate.py tests/unit/test_migrations.py tests/integration/test_migrations.py` → All checks passed.
*   **Lint global:** 11 errores preexistentes (no introducidos por F02).
*   **Suite unitaria global:** 2 fallos preexistentes por `DATABASE_URL` ausente en tests de perfiles.

### 6. Lecciones Aprendidas (Retroalimentación)
*   No abrir una fase de implementación sobre una rama base con el gate global en rojo; mergear F01 primero.
*   Mantener el lint y los tests globales en verde como precondición de cada worktree de fase.
*   Registrar explícitamente la deuda diferida para que el PR de F02 no se confunda con una regresión.

---

## [Plantilla Vacía - Copiar para Nuevas Entradas]

## AAAA-MM-DD — [Título corto del Incidente o Feature] — [Componentes Afectados, ej: Gateway / Worker / DB]

### 1. Síntoma Observado / Reporte
*Describe el error tal como lo reportó el usuario o cómo se detectó en los sistemas de monitoreo.*
*   **Qué falló:** [Ej. El usuario ve un error 504 Gateway Timeout al intentar procesar un reporte]
*   **Entorno:** [Ej. Local / Staging / Producción]
*   **Logs / Traza de Error:**
    ```text
    [Traza de error de consola, logs del servidor o payload fallido]
    ```

### 2. Hipótesis de Diagnóstico
*¿Qué teorías se investigaron y cómo se validaron o descartaron?*
1.  **Hipótesis 1:** [Teoría...] → *Resultado:* [Descartada porque...]
2.  **Hipótesis 2:** [Teoría...] → *Resultado:* [Confirmada mediante...]

### 3. Causa Raíz
*Explicación técnica detallada de por qué ocurrió el problema en la arquitectura (ej. condiciones de carrera, desalineación de contratos de API, problemas de concurrencia en la DB, fallos de red en llamadas síncronas).*
*   [Ej. "El microservicio X asumía que la base de datos respondía en menos de 2s, pero bajo alta carga la query demoraba 5s, haciendo que el API Gateway cortara la conexión por timeout antes de recibir la respuesta."]

### 4. Resolución e Implementación
*Pasos exactos y cambios realizados en el código. Lista los archivos editados o refactorizados.*
1.  **[Servicio/Componente 1]:** [Descripción del cambio...]
2.  **[Servicio/Componente 2]:** [Descripción del cambio...]
*   **Cambios en el código (Diff de referencia):**
    ```diff
    - código_antiguo
    + código_nuevo
    ```

### 5. Verificación y Mediciones
*Pruebas ejecutadas para certificar que el bug está resuelto y no causa regresiones. Si aplica, incluye telemetría o tiempos antes/después.*
*   **Pruebas unitarias/integración:** [Ej. Ejecución de suite de test local o de integración]
*   **Tiempos de ejecución / Latencia:**
    *   **Antes:** [Ej. 5.4s por petición]
    *   **Después:** [Ej. 120ms (reducción del 97% mediante indexación/caché)]

### 6. Lecciones Aprendidas (Retroalimentación)
*¿Cómo podemos evitar que este error vuelva a ocurrir? ¿Qué patrones de diseño o guardarrailes defensivos deberíamos añadir?*
*   [Ej. "No confiar en que el cliente valide los payloads; el backend debe implementar validaciones robustas de esquema."]
*   [Ej. "Configurar políticas de reintentos (retries con exponential backoff) y disyuntores (circuit breakers) en llamadas externas."]

---

## [Ejemplo de Entrada Completada para Referencia]

## 2026-06-03 — Error de concurrencia al actualizar estado de procesamiento — Worker / Database

### 1. Síntoma Observado / Reporte
Varios usuarios reportaron que tras subir un archivo masivo para procesamiento asíncrono, la barra de progreso se quedaba colgada en "99%", a pesar de que el backend había terminado de procesar todos los registros.
*   **Qué falló:** El estado final de la tarea en la tabla `tasks` no se actualizaba a `COMPLETED`.
*   **Entorno:** Staging y Producción.
*   **Logs / Traza de Error:**
    ```text
    sqlalchemy.exc.OperationalError: (psycopg2.errors.DeadlockDetected) deadlock detected
    DETAIL:  Process 432 waits for ShareLock on transaction 10452; blocked by process 433.
    Process 433 waits for ShareLock on transaction 10451; blocked by process 432.
    ```

### 2. Hipótesis de Diagnóstico
1.  **Hipótesis 1:** El worker no enviaba la señal de finalización al Message Broker. → *Resultado:* Descartada. Los logs de RabbitMQ confirmaron la entrega del mensaje de éxito.
2.  **Hipótesis 2:** Múltiples hilos del Worker intentaban actualizar la misma fila de la tabla `tasks` de forma simultánea, causando un deadlock en la base de datos al bloquear índices cruzados. → *Resultado:* Confirmada. La transacción de actualización no estaba optimizada y bloqueaba la fila completa durante operaciones de escritura concurrentes.

### 3. Causa Raíz
Cada hilo de procesamiento reportaba el progreso individual del bloque. Cuando los últimos hilos terminaban simultáneamente, ambos intentaban hacer un `UPDATE tasks SET progress = 100, status = 'COMPLETED' WHERE id = :id` mientras mantenían bloqueos compartidos en filas hijas de auditoría relacional, generando un deadlock en el gestor de base de datos.

### 4. Resolución e Implementación
Se implementó un bloqueo optimista en base de datos (`SELECT FOR UPDATE` controlado) y se centralizó la actualización del estado de progreso a través de un agregador en memoria (Redis) que solo persiste en la base de datos principal de manera periódica (throttle) o cuando realmente el contador de elementos pendientes llega a cero.
*   **Cambios en el código (Diff de referencia):**
    ```diff
    # services/task_manager.py
    - db.session.query(Task).filter_by(id=task_id).update({"progress": new_progress})
    + # Se utiliza Redis para contar elementos de forma atómica
    + redis_client.incrby(f"task:{task_id}:progress", increment)
    ```

### 5. Verificación y Mediciones
*   **Pruebas unitarias/integración:** Se ejecutó una prueba de carga simulando 100 workers concurrentes escribiendo sobre la misma tarea. Cero deadlocks detectados.
*   **Tiempos de ejecución / Latencia:** El tiempo bloqueado en base de datos bajó de ~250ms por transacción a menos de 5ms gracias a la delegación a Redis.

### 6. Lecciones Aprendidas (Retroalimentación)
*   **Nunca realizar actualizaciones de base de datos OLTP de alta frecuencia desde múltiples hilos o procesos distribuidos concurrentes.**
*   Utilizar almacenes en memoria rápidos (como Redis) para estados transicionales de alta concurrencia, y consolidar en la base de datos SQL de manera diferida.

---

## 2026-10-28 — Error 500 al conectar Supabase BYOK en Hugging Face Spaces (Pooler 6543 y Migraciones Ausentes)

### 1. Síntoma Observado / Reporte
Al ejecutar `POST /api/credentials/connect-db` desde la UI o API en `https://alexp97-agrovision.hf.space` configurando el Supabase del usuario (Transaction Pooler, puerto `6543`), el endpoint retornaba `HTTP 500 Internal Server Error`.
*   **Qué falló:** La auto-conexión y migración inicial del esquema en la base de datos Supabase del usuario.
*   **Entorno:** Producción (Hugging Face Spaces, Docker container).
*   **Logs / Traza de Error:**
    1. Traza 1 (ausencia de archivos SQL en runtime):
       ```text
       FileNotFoundError: No existe el directorio de migraciones: /home/user/app/supabase/migrations
       ```
    2. Traza 2 (PgBouncer en modo transacción puerto 6543):
       ```text
       asyncpg.exceptions.DuplicatePreparedStatementError: prepared statement "__asyncpg_stmt_1__" already exists
       ```

### 2. Hipótesis de Diagnóstico
1.  **Hipótesis 1:** La URL de Supabase del usuario tenía credenciales inválidas. → *Resultado:* Descartada. La conexión directa con psql/asyncpg desde local funcionaba.
2.  **Hipótesis 2:** `.dockerignore` excluía `supabase/` del contexto Docker y `Dockerfile` no copiaba las migraciones SQL al contenedor final. → *Resultado:* Confirmada. El contenedor no tenía acceso a `supabase/migrations/*.sql`.
3.  **Hipótesis 3:** El pooler de transacciones de Supabase (puerto 6543) rechaza prepared statements reutilizados por asyncpg cuando `statement_cache_size > 0`. → *Resultado:* Confirmada. Asyncpg intenta cachear statements por defecto a menos que se fuerce `statement_cache_size=0`.

### 3. Causa Raíz
1.  **Contexto Docker incompleto:** `.dockerignore` contenía la regla `supabase/` que ignoraba todo el directorio, y `Dockerfile` únicamente copiaba `backend/` sin incluir `supabase/migrations/`.
2.  **Incompatibilidad con Transaction Pooler:** `backend/db/migrate.py` ejecutaba `asyncpg.connect(dsn=dsn, timeout=30)` sin `statement_cache_size=0`. A diferencia de `backend/db/session.py` (que sí incluía `connect_args={"statement_cache_size": 0}` para SQLAlchemy), la conexión directa de migraciones fallaba en PgBouncer `6543`.

### 4. Resolución e Implementación
*   **`.dockerignore`:** Reemplazada la exclusión global `supabase/` por exclusión de temporales `supabase/.temp/` y `supabase/.branches/`, permitiendo que `supabase/migrations/` ingrese al contexto.
*   **`Dockerfile`:** Añadida la directiva `COPY --chown=user supabase/migrations/ ./supabase/migrations/`.
*   **`backend/db/migrate.py`:** Añadido `statement_cache_size=0` en `asyncpg.connect`:
    ```python
    conn = await asyncpg.connect(dsn=dsn, timeout=30, statement_cache_size=0)
    ```
*   **`tests/unit/test_deploy_script.py`:** Añadida prueba `test_dockerfile_and_dockerignore_include_supabase_migrations` para prevenir regresiones.

### 5. Verificación y Mediciones
*   **Pruebas unitarias:** 167 tests unitarios en verde (`test_deploy_script.py`, `test_migrations.py`, `test_byok_db_session.py`, `test_env_example.py`).
*   **Prueba en vivo:** Petición HTTP directa contra el endpoint `/api/credentials/connect-db` en Hugging Face Spaces usando el Transaction Pooler (puerto 6543) retorna `HTTP 200` y `{"connected": true, "schema_ready": true}`.

### 6. Lecciones Aprendidas (Retroalimentación)
*   Todo componente que ejecute DDL o DML mediante `asyncpg` contra bases de datos en la nube con PgBouncer (como Supabase Transaction Pooler en puerto 6543) DEBE configurar `statement_cache_size=0`.
*   Las pruebas de empaquetado de despliegue (`test_deploy_script.py`) deben certificar que los archivos estáticos o de migración que consume el backend en runtime formen parte del `Dockerfile` y no sean filtrados por `.dockerignore`.
