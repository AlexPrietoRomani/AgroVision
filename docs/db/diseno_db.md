# Especificación y Diseño de Base de Datos — AgroVisión (Plataforma Completa)

> **Propósito:** Definir el modelo físico y lógico de persistencia de AgroVisión, justificar la elección del motor y servir como mapa de referencia para migraciones e implementación.
> **Origen:** Se construye a partir de [`docs/reference/description_proyecto_agrovision.md`](../reference/description_proyecto_agrovision.md).
> **Aplicabilidad:** Solo la **plataforma completa**. El [MVP](../reference/description_proyecto_agrovision_mvp.md) opera en **modo efímero sin base de datos** (todo en memoria de sesión).
>
> **Alcance de construcción (esta iteración):** se implementan **todas** las tablas, pero con dos matices:
> - **`fields`, `ndvi_timeseries`, `chat_messages`** se usan activamente (parcelas, teledetección 5 años, agente).
> - **`plant_counts`** y la **cola PGMQ `count_tasks`** se crean en la migración pero quedan **inactivas** (el módulo de Conteo está **en desarrollo**); se activan con `COUNTING_ENABLED=true`.
> - **Clima:** se consulta **on-demand** (Open-Meteo, sin llave) y **no se persiste** en esta versión (cacheable a futuro si hace falta). No hay tabla de clima por ahora (YAGNI).
>
> **Persistencia de credenciales:** ninguna. Las llaves del usuario (Supabase URL/anon, Copernicus, Groq) son **efímeras** (memoria de sesión); la BD es BYOK (proyecto Supabase del propio usuario).

---

## 1. Criterios de Selección del Motor de Base de Datos

*   **Motor Seleccionado:** **PostgreSQL 16 + extensión PostGIS 3.4**, provisto por **Supabase** (capa gratuita). Modelo **BYOK**: cada usuario aporta su propio proyecto Supabase; el repo entrega las migraciones.
*   **Justificación Técnica:**
    *   *Consistencia vs. Flexibilidad:* se elige **SQL relacional** porque el agente conversacional (function calling) ejecuta *joins* entre `fields` y `ndvi_timeseries`, requiere integridad referencial (FK con `ON DELETE CASCADE`) y cálculos agregados. Para los resultados heterogéneos de detección YOLO se usa una columna **`JSONB`** (`result_json`), obteniendo flexibilidad documental sin renunciar a ACID.
    *   *Capacidad espacial:* **PostGIS** es innegociable — almacena `geometry(Polygon, 4326)`, calcula áreas (`ST_Area`) para densidad pl/Ha e indexa con **GIST**. Ningún NoSQL ofrece este soporte geográfico nativo de forma gratuita y madura.
    *   *Cola embebida:* **Supabase Queues (PGMQ)** vive dentro del mismo Postgres, dando mensajería transaccional ACID sin broker externo (no Redis/RabbitMQ) — clave para el costo cero.
    *   *Concurrencia:* Postgres gestiona bloqueos de fila óptimamente; el worker usa *visibility timeout* (vt=120) de PGMQ para exclusión mutua sobre tareas.
    *   *Infraestructura:* Supabase Free (500 MB DB, *connection pooler* incluido, pausa a 7 días sin actividad — mitigada con keep-alive).

---

## 2. Diagrama de Entidad-Relación (ERD)

```mermaid
erDiagram
    USUARIO ||--o{ FIELDS : "posee"
    USUARIO ||--o{ PLANT_COUNTS : "ejecuta"
    USUARIO ||--o{ CHAT_MESSAGES : "conversa"
    FIELDS ||--o{ NDVI_TIMESERIES : "registra"
    FIELDS ||--o{ PLANT_COUNTS : "asocia"

    USUARIO {
        uuid id PK "auth.users (Supabase Auth)"
        string email "UNIQUE, NOT NULL"
        timestamp created_at "DEFAULT now()"
    }

    FIELDS {
        uuid id PK "DEFAULT gen_random_uuid()"
        uuid user_id FK "NOT NULL, CASCADE ON DELETE"
        string name "NOT NULL"
        geometry geom "Polygon 4326, NOT NULL, GIST"
        timestamp created_at "DEFAULT now()"
    }

    NDVI_TIMESERIES {
        int id PK "SERIAL"
        uuid field_id FK "CASCADE ON DELETE"
        date date "NOT NULL"
        float mean_ndvi "NOT NULL"
        float min_ndvi
        float max_ndvi
        float cloud_cover
        string source "DEFAULT 'sentinel2'"
    }

    PLANT_COUNTS {
        int id PK "SERIAL"
        uuid user_id FK "CASCADE ON DELETE"
        uuid field_id FK "SET NULL ON DELETE"
        string image_url "NOT NULL, Storage privado"
        int count "NOT NULL"
        jsonb result_json "GIN"
        timestamp processed_at "DEFAULT now()"
    }

    CHAT_MESSAGES {
        int id PK "SERIAL"
        uuid user_id FK "CASCADE ON DELETE"
        string session_id "NOT NULL"
        string role "CHECK (user|assistant)"
        string content "NOT NULL"
        timestamp created_at "DEFAULT now()"
    }
```

---

## 3. Diccionario de Datos (Tablas)

### 3.1 Tabla: `fields`
*   **Descripción:** Parcelas o lotes agrícolas georreferenciados del usuario.

| Campo | Tipo de Dato | Modificadores | Descripción / Regla de Negocio |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PK`, `DEFAULT gen_random_uuid()` | Identificador único. |
| `user_id` | `UUID` | `FK (auth.users.id)`, `NOT NULL`, `ON DELETE CASCADE` | Propietario del lote. |
| `name` | `TEXT` | `NOT NULL` | Nombre legible (canonicalizado a *Title Case*). |
| `geom` | `GEOMETRY(Polygon, 4326)` | `NOT NULL` | Polígono WGS84; validado con `ST_IsValid`. |
| `created_at` | `TIMESTAMP` | `DEFAULT now()` | Fecha de creación. |

*   **Restricciones:** `ST_IsValid(geom)` debe ser verdadero; SRID siempre 4326.

### 3.2 Tabla: `ndvi_timeseries`
*   **Descripción:** Serie temporal histórica de índices vegetativos derivados de Sentinel-2. Se persiste **agregada por mes** (un punto por mes, la escena de menor nubosidad), con un **backfill inicial de 5 años** al crear la parcela y refresco **incremental** después.

| Campo | Tipo de Dato | Modificadores | Descripción / Regla de Negocio |
| :--- | :--- | :--- | :--- |
| `id` | `SERIAL` | `PK` | Identificador secuencial. |
| `field_id` | `UUID` | `FK (fields.id)`, `ON DELETE CASCADE` | Lote asociado. |
| `date` | `DATE` | `NOT NULL` | Fecha de la escena satelital. |
| `mean_ndvi` | `FLOAT` | `NOT NULL` | NDVI medio zonal; rango razonable $[-1,1]$. |
| `min_ndvi` / `max_ndvi` | `FLOAT` | — | Extremos zonales. |
| `cloud_cover` | `FLOAT` | — | % de nubes; > 60 % marca baja confianza. |
| `source` | `TEXT` | `DEFAULT 'sentinel2'` | Origen (minúsculas). |

*   **Restricciones:** `UNIQUE (field_id, date)` — una observación por lote y fecha (con agregación mensual, `date` se normaliza al primer día del mes, p. ej. `2026-04-01`); el `UNIQUE` hace **idempotente** el backfill/refresco incremental (`ON CONFLICT DO NOTHING/UPDATE`).

### 3.3 Tabla: `plant_counts` (creada, **inactiva** — Conteo en desarrollo)
*   **Descripción:** Resultados de conteo por dron (inferencia del modelo **agnóstico** `agrovision-plantcount`, vía adaptador onnxruntime/ultralytics). La tabla se crea en la migración inicial pero **no recibe escrituras** hasta activar `COUNTING_ENABLED=true`.

| Campo | Tipo de Dato | Modificadores | Descripción / Regla de Negocio |
| :--- | :--- | :--- | :--- |
| `id` | `SERIAL` | `PK` | Identificador secuencial. |
| `user_id` | `UUID` | `FK (auth.users.id)`, `ON DELETE CASCADE` | Quién ejecutó el conteo. |
| `field_id` | `UUID` | `FK (fields.id)`, `ON DELETE SET NULL` | Lote (opcional). |
| `image_url` | `TEXT` | `NOT NULL` | Ruta en Storage privado (no pública). |
| `count` | `INTEGER` | `NOT NULL` | Conteo total de plantas. |
| `result_json` | `JSONB` | — | `{"boxes":[[x1,y1,x2,y2,conf,cls]],"classes":{...},"model_version":"2.0.0","architecture":"rf-detr-nano"}` |
| `processed_at` | `TIMESTAMP` | `DEFAULT now()` | Momento de la inferencia. |

*   **Restricciones:** `count >= 0`; cada `conf` en `result_json` dentro de $[0,1]$ (validado en la app).

### 3.4 Tabla: `chat_messages`
*   **Descripción:** Memoria conversacional del agente RAG.

| Campo | Tipo de Dato | Modificadores | Descripción / Regla de Negocio |
| :--- | :--- | :--- | :--- |
| `id` | `SERIAL` | `PK` | Identificador secuencial. |
| `user_id` | `UUID` | `FK (auth.users.id)`, `ON DELETE CASCADE` | Dueño de la conversación. |
| `session_id` | `TEXT` | `NOT NULL` | Hilo conversacional. |
| `role` | `TEXT` | `NOT NULL`, `CHECK (role IN ('user','assistant'))` | Emisor del mensaje. |
| `content` | `TEXT` | `NOT NULL` | Texto del turno. |
| `created_at` | `TIMESTAMP` | `DEFAULT now()` | Orden temporal. |

---

## 4. Matriz de Accesos y CRUD por Componente

| Tabla | Gateway (FastAPI) | Worker Asíncrono | UI (Shiny) | Permisos | Notas de Diseño |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `fields` | `ParcelsService` (CRUD) + dispara backfill | *Ninguno* | vía API (módulo *Creación de Parcelas*) | `API: CRUD` | La UI nunca toca la BD directo; pasa por el gateway. Al crear, encola/lanza el backfill NDVI de 5 años. |
| `ndvi_timeseries` | `RemoteSensingService` (write, mensual) | *Ninguno* | lectura vía API (*Teledetección*, *Resumen*) | `API: Read/Write` | Escritura tras estadística zonal + agregación mensual; idempotente por `UNIQUE(field_id,date)`. |
| `plant_counts` | `CountService` (read) | `InferenceWorker` (write) | lectura vía API | `API: Read` <br> `Worker: Write` | **En desarrollo:** sin escrituras hasta `COUNTING_ENABLED=true`. |
| `chat_messages` | `AgentService` | *Ninguno* | lectura vía API (*Asistente*) | `API: Read/Write` | Memoria del agente (Memory Buffer). |
| `pgmq.count_tasks` (cola) | `CountService` (produce) | `InferenceWorker` (consume) | — | `API: send` <br> `Worker: read/archive` | **En desarrollo:** cola creada pero inactiva hasta activar el conteo. |

> **NDVI raster / heatmap:** el endpoint `POST /api/ndvi/raster` genera un PNG colorizado **on-demand** (no escribe en BD ni en Storage; se regenera). No aparece en la matriz por no tocar persistencia.

> **Regla de aislamiento:** la UI Shiny **no** posee credenciales de BD propias; el acceso es siempre mediado por el gateway, que recibe las llaves del usuario por cabecera y las descarta.

---

## 5. Rendimiento, Índices y Concurrencia

### 5.1 Índices Planificados
*   **`fields_geom_gist_idx`** en `fields USING gist (geom)` — acelera operaciones espaciales (intersección, área).
*   **`ndvi_field_date_idx`** en `ndvi_timeseries (field_id, date)` — optimiza filtros de fecha del agente.
*   **`plant_counts_json_gin_idx`** en `plant_counts USING gin (result_json)` — búsquedas/agregaciones sobre el JSONB de detecciones.
*   **`chat_session_history_idx`** en `chat_messages (session_id, created_at)` — recuperación ordenada del historial.

### 5.2 Control de Concurrencia y Seguridad
*   **Row Level Security (RLS):** políticas `auth.uid() = user_id` en todas las tablas para aislar usuarios dentro del mismo proyecto Supabase.
*   **Cola PGMQ:** *visibility timeout* `vt=120` garantiza que un solo worker procese cada tarea; si falla, el mensaje reaparece y se reintenta.
*   **Storage privado:** bucket `drone-images` privado; acceso solo vía **Signed URLs** (`expires_in=600`).

### 5.3 Estrategia de Migraciones y Versionado
*   **Herramienta primaria:** **Supabase CLI** con migraciones SQL versionadas (`supabase/migrations/*.sql`), aplicadas con `supabase db push` (idempotentes).
*   **Alternativa local (dev):** **Alembic** (SQLAlchemy + asyncpg) cuando se trabaja contra el Postgres+PostGIS de `docker-compose`.
*   **Política:** prohibido alterar el esquema manualmente en producción; todo cambio pasa por una migración versionada y revisable.
*   **Orden de bootstrap:** (1) `create extension postgis`; (2) `create extension pgmq` / habilitar Supabase Queues; (3) tablas + índices; (4) políticas RLS; (5) bucket de Storage privado.

---

## Apéndice — Trazabilidad

El esquema deriva directamente de la sección 3 de [`description_proyecto_agrovision.md`](../reference/description_proyecto_agrovision.md) y de las herramientas del agente (sección 5.4). De este documento se derivan las tareas de la **Fase de Persistencia** del [Plan Maestro completo](../plan/plan_agrovision.md).
