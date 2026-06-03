# Arquitectura — AgroVisión (Plataforma Completa)

> **Audiencia:** Arquitectos de solución, líderes técnicos, desarrolladores.
> **Alcance:** Estructura fundamental del sistema, interacciones de alto nivel (C4), esquema de datos y modelo de despliegue de la **plataforma completa** (5 módulos). Para especificaciones funcionales, ver [`description_proyecto_agrovision.md`](../reference/description_proyecto_agrovision.md). Para el alcance reducido, ver [`architecture_agrovision_mvp.md`](architecture_agrovision_mvp.md).

---

## 1. Visión General del Sistema (C4 – Nivel Contexto)

```mermaid
flowchart TB
    subgraph Actores["Actores Principales"]
        U1["👤 Agrónomo / Productor<br/>(usuario final)"]
        U2["🛠️ Operador / Desplegador<br/>(configura BYOK e infra)"]
    end

    subgraph Sistema["Sistema Central"]
        direction TB
        APP["AgroVisión<br/>─────────────────<br/>Monitoreo agronómico: teledetección NDVI,<br/>conteo de plantas por dron (RF-DETR-Nano)<br/>y agente conversacional (RAG)"]
    end

    subgraph Externos["Dependencias Externas (BYOK)"]
        SB[("Supabase<br/>─────────────<br/>PostgreSQL+PostGIS · Storage · Queues PGMQ")]
        COP["Copernicus CDSE<br/>─────────────<br/>Sentinel-2 L2A (STAC)"]
        NASA["NASA POWER / Open-Meteo<br/>─────────────<br/>Agroclima por coordenadas"]
        GROQ["Groq<br/>─────────────<br/>Llama 3 (LLM, function calling)"]
    end

    U1 -->|"Analiza lotes, sube ortomosaicos, consulta al agente"| APP
    U2 -->|"Configura credenciales y despliegue"| APP
    APP <-->|"Lee/Escribe (datos del usuario)"| SB
    APP <-->|"Descarga reflectancias"| COP
    APP <-->|"Consume clima"| NASA
    APP <-->|"Inferencia conversacional"| GROQ
```

**Decisiones arquitectónicas clave (Nivel Macro):**
- **Open-source, costo cero:** todo el stack vive en capa gratuita (ShinyApps.io + Render + Supabase + Groq + Copernicus).
- **BYOK con cero persistencia de credenciales:** las llaves del usuario se inyectan por sesión y se descartan; nunca se almacenan.
- **Servicios desacoplados:** UI (Shiny) y backend (FastAPI) se despliegan por separado y se comunican vía HTTPS + CORS.
- **Procesamiento asíncrono nativo de Postgres:** colas PGMQ embebidas en Supabase (sin Redis/RabbitMQ).

---

## 2. Componentes Internos (C4 – Nivel Contenedor)

```mermaid
flowchart LR
    subgraph Cliente["Capa de Presentación"]
        UI["UI — Shiny for Python (ASGI)<br/>──────────<br/>5 nav_panel · ipyleaflet · Plotly<br/>Estado efímero en reactive.value<br/>Host: ShinyApps.io"]
    end

    subgraph Backend["Capa de Aplicación"]
        direction TB
        API["API Gateway — FastAPI<br/>──────────<br/>CORS · proxy efímero de llaves<br/>/api/ndvi /count /chat /weather"]
        LOGIC["Servicios de Negocio<br/>──────────<br/>RemoteSensing · Count · Agent · Fields"]
        subgraph Infra["Infraestructura de Soporte"]
            QUEUE["Cola — Supabase Queues (PGMQ)<br/>count_tasks (vt=120)"]
            WORKER["Worker Asíncrono<br/>Inferencia RF-DETR-Nano (CPU)"]
            MODEL["Modelo predeterminado<br/>agrovision-plantcount-v2.0.0.onnx (empaquetado)"]
        end
    end

    subgraph Datos["Capa de Datos (Supabase)"]
        DB[("PostgreSQL + PostGIS<br/>fields · ndvi_timeseries<br/>plant_counts · chat_messages")]
        ST[("Storage privado<br/>drone-images + Signed URLs")]
    end

    UI -->|"HTTPS + X-User-*-Key"| API
    API --> LOGIC
    LOGIC -->|"encola ortomosaico"| QUEUE
    QUEUE --> WORKER
    WORKER -->|"carga pesos"| MODEL
    LOGIC <-->|"asyncpg / SQL"| DB
    WORKER <-->|"persiste conteo"| DB
    WORKER <-->|"lee/escribe imágenes"| ST
```

**Flujo de una interacción típica (conteo por dron):**
1. El agrónomo sube un ortomosaico en la UI (`ui.input_file`); la UI llama `POST /api/count` con las cabeceras BYOK.
2. El gateway sube la imagen a Storage y envía un mensaje a la cola `count_tasks` (PGMQ).
3. El worker lee el mensaje (`vt=120`), carga RF-DETR-Nano y ejecuta la inferencia (con *tiling* si es grande).
4. El worker persiste el resultado en `plant_counts` y genera una **Signed URL** del overlay.
5. La UI sondea `GET /api/count/{id}` y, al estar `done`, renderiza conteo, densidad y overlay.

---

## 3. Lógica Core / Procesos Críticos

AgroVisión tiene tres motores internos relevantes:

### 3.1 Pipeline de Visión (conteo)

```mermaid
flowchart TB
    IN(["Ortomosaico RGB (dron)"])
    P1["Validación + tiling por GSD"]
    P2["Inferencia RF-DETR-Nano (CPU)"]
    P3["Reensamble + NMS entre parches"]
    P4["Conteo, densidad pl/Ha, malezas, fallas"]
    OUT(["plant_counts + overlay (Signed URL)"])
    IN --> P1 --> P2 --> P3 --> P4 --> OUT
```

### 3.2 Estadística Zonal NDVI

```mermaid
flowchart TB
    G(["GeoJSON del polígono + rango fechas"])
    S1["pystac-client: buscar escenas Sentinel-2 L2A"]
    S2["Recortar bandas B08/B04 al polígono"]
    S3["NDVI = (NIR-Red)/(NIR+Red) por píxel"]
    S4["Agregación zonal: mean/min/max + cloud_cover"]
    O(["ndvi_timeseries"])
    G --> S1 --> S2 --> S3 --> S4 --> O
```

### 3.3 Agente RAG (Function Calling)

El agente (Llama 3 vía Groq) traduce la intención en llamadas tipadas: `get_vegetation_index_trend`, `get_weather_context`, `get_field_planting_density`. Plan típico de 3 pasos: verificar caída NDVI → correlacionar con clima → sintetizar diagnóstico.

---

## 4. Flujo de Secuencia (Conteo Asíncrono)

```mermaid
sequenceDiagram
    actor U as Agrónomo
    participant C as UI (Shiny)
    participant S as Gateway (FastAPI)
    participant Q as Cola PGMQ
    participant W as Worker
    participant ST as Storage
    participant DB as PostGIS

    U->>C: Sube ortomosaico + clic "Iniciar Conteo"
    C->>S: POST /api/count (multipart + X-User-*-Key)
    S->>ST: Sube imagen (bucket privado)
    S->>Q: pgmq.send(count_tasks, {image_path, model})
    S-->>C: {task_id, status: "queued"}

    rect rgb(240, 248, 255)
        note over W,DB: Procesamiento asíncrono (tolerante a fallos)
        W->>Q: pgmq.read(vt=120)
        W->>ST: Descarga imagen
        W->>W: Inferencia RF-DETR-Nano + tiling
        W->>DB: INSERT plant_counts
        W->>ST: Sube overlay + create_signed_url(600s)
        W->>Q: pgmq.archive(msg_id)
    end

    loop Polling (reactive.invalidate_later)
        C->>S: GET /api/count/{task_id}
        S->>DB: SELECT estado/resultado
        S-->>C: {status, count, density, overlay_url}
    end
    C-->>U: Render conteo, densidad y overlay
```

---

## 5. Modelo de Dominio / Entidad-Relación

El detalle completo (diccionario, índices, RLS, migraciones) vive en [`docs/db/diseno_db.md`](../db/diseno_db.md). Resumen:

```mermaid
flowchart TB
    subgraph Geo["Dominio Geoespacial"]
        FIELDS["fields<br/>─────────<br/>id (PK) · user_id (FK)<br/>geom (Polygon 4326)"]
    end
    subgraph Series["Dominio Analítico"]
        NDVI["ndvi_timeseries<br/>─────────<br/>id (PK) · field_id (FK)<br/>mean_ndvi · date"]
        COUNTS["plant_counts<br/>─────────<br/>id (PK) · field_id (FK)<br/>count · result_json (JSONB)"]
    end
    subgraph Chat["Dominio Conversacional"]
        MSG["chat_messages<br/>─────────<br/>id (PK) · session_id<br/>role · content"]
    end
    FIELDS -->|"1:N"| NDVI
    FIELDS -->|"1:N"| COUNTS
```

**Políticas de Datos:**
- **RLS por usuario:** `auth.uid() = user_id` en todas las tablas.
- **Storage privado + Signed URLs:** nunca exposición pública directa.
- **JSONB indexado (GIN):** detecciones de YOLO consultables sin esquema rígido.

---

## 6. Arquitectura de Despliegue (Infraestructura)

```mermaid
flowchart LR
    subgraph Local["Entorno de Desarrollo"]
        direction TB
        DEV["docker-compose<br/>ui · api · worker"]
        DEV_DB[("postgis/postgis + MinIO")]
        DEV --- DEV_DB
    end

    subgraph Pipeline["CI/CD"]
        direction TB
        LINT["Ruff + pytest + Playwright"]
        BUILD["Build Docker images<br/>(modelo empaquetado)"]
        LINT --> BUILD
    end

    subgraph Prod["Producción (Capa Gratuita)"]
        direction TB
        SHINY["ShinyApps.io<br/>(UI Shiny)"]
        RENDER["Render<br/>(FastAPI + Worker)"]
        SUPA[("Supabase<br/>PostGIS · Storage · PGMQ")]
        SHINY -->|"HTTPS + CORS"| RENDER
        RENDER <--> SUPA
    end

    Local -->|"git push"| Pipeline
    Pipeline -->|"rsconnect deploy / Render deploy"| Prod
```

**Notas de despliegue:**
- La UI Shiny se despliega con `rsconnect deploy shiny` (ASGI nativo en ShinyApps.io); **no aplica** el problema de slugs SPA de Astro del plan de replicación.
- El backend en Render *duerme a los 15 min* (cold start 30–60 s); el modelo de conteo (`agrovision-plantcount`, ONNX ligero) cabe en 512 MB. El **módulo de conteo arranca en standby** (`COUNTING_ENABLED=false`) hasta que el repo del modelo publique el artefacto.
- Supabase Free **se pausa a los 7 días** sin actividad → keep-alive con cron ligero.

---

## 7. Decisiones Arquitectónicas Relevantes (ADRs Resumidos)

| Decisión Tomada | Alternativa Descartada | Razón Principal |
| :--- | :--- | :--- |
| **UI en Shiny for Python** | Streamlit (Plan Detallado) / Astro (plan de replicación) | Se requiere UI analítica en Python con estado reactivo por sesión; Shiny es ASGI nativo y despliega directo en ShinyApps.io sin el problema de enrutamiento SPA de Astro. |
| **UI y backend como servicios separados** | Monolito unificado Starlette | Aísla el cómputo pesado (visión/satélite) de la presentación; permite escalar/desplegar cada uno en su host gratuito. |
| **Colas PGMQ en Supabase** | Redis / RabbitMQ | Mensajería transaccional ACID embebida en Postgres; **cero costo** y sin infraestructura extra. |
| **Credenciales efímeras (BYOK, solo memoria)** | Persistencia en `localStorage` (mockup) o servidor | Elimina todo vector de fuga de secretos; refrescar borra todo (requisito del usuario). |
| **Modelo agnóstico (multi-candidato) desde repo separado, en HF Hub; AGPL-3.0 aceptada** | Entrenar dentro de AgroVisión / fijar un solo modelo | Desacopla el ML de la app; **AGPL-3.0 aceptada** (AgroVisión open-source) habilita **YOLO26**; la app descarga `agrovision-plantcount` y lo infiere vía **adaptador** (onnxruntime o `ultralytics` según la arquitectura). El **módulo de conteo arranca en standby** hasta la publicación del modelo. |
| **PostgreSQL + PostGIS** | NoSQL documental | El dominio es geoespacial y relacional (joins del agente, integridad referencial); JSONB cubre la parte flexible. |
| **Hosting gratuito (ShinyApps.io+Render+Supabase)** | Cloud administrado de pago (AWS/GCP) | Objetivo de costo cero y reproducibilidad; se asumen *caveats* (cold start, pausa, horas activas). |
