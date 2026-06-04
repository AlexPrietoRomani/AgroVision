# Arquitectura — AgroVisión (Plataforma Completa)

> **Audiencia:** Arquitectos de solución, líderes técnicos, desarrolladores.
> **Alcance:** Estructura fundamental del sistema, interacciones de alto nivel (C4), esquema de datos y modelo de despliegue de la **plataforma completa** (**6 módulos**). Para especificaciones funcionales, ver [`description_proyecto_agrovision.md`](../reference/description_proyecto_agrovision.md).
>
> **Estilo arquitectónico:** **monolito modular** (un solo backend FastAPI con límites por dominio bien aislados — `api/` HTTP + `services/` negocio), **microservices-ready**: cada dominio puede extraerse a un servicio propio sin reescribir la UI. Elegido sobre microservicios reales por la realidad de la **capa gratuita** (Render free duerme a 15 min y multiplica cold-starts/CORS por servicio). Ver ADR en §7.
>
> **Módulos de UI (6):** Resumen de Campo · **Creación de Parcelas** (nuevo: dibujo del polígono) · Teledetección (solo gráficos + heatmap NDVI) · Conteo por Dron (**en desarrollo / standby**) · Asistente Agéntico · Credenciales.
>
> **Frontend (Astro — Fase 8, consolidado en Fase 10):** la UI es **Astro + Tailwind** (SPA estática, hash-routing, responsive, sidebar/footer plegables) que replica el [mockup](../investigation/agrovisi_n_spa_prototype.html) y consume `/api/*` directo (Leaflet-draw para el mapa, Chart.js para NDVI/clima). El gateway **FastAPI sirve el build estático en `/`** y mantiene `/api`. **Shiny fue eliminado por completo en la Fase 10** (ya no hay UI Python ni `/shiny`). Sigue la "Regla de Oro" de [`plan_replication.md`](../doc_guia/plan_replication.md) (una página, hash, rutas relativas, CSS inline).
>
> **Despliegue (Fase 10):** un **único contenedor Docker en Hugging Face Spaces** (SDK Docker) construido desde el `Dockerfile` de la raíz; el gateway sirve UI + API en el mismo origen. Alternativa: Render (Docker). *(shinyapps.io quedó descartado: solo hospeda apps Shiny, no FastAPI.)*
>
> **Seguridad (Fase 10):** rate limiting en `/api` + cabeceras de hardening; modelo BYOK (sin secretos en el server). Ver §8.
>
> **Estado del Conteo:** el módulo de visión arranca **en desarrollo** (`COUNTING_ENABLED=false`); se construye **todo lo demás** ahora. La tabla `plant_counts`, la cola PGMQ y el worker se crean pero quedan inactivos hasta publicar el modelo.

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
        APP["AgroVisión<br/>─────────────────<br/>Monitoreo agronómico: gestión de parcelas,<br/>teledetección NDVI (Sentinel-2, 5 años),<br/>agente conversacional (RAG)<br/>· conteo por dron EN DESARROLLO"]
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
- **Open-source, costo cero:** todo el stack vive en capa gratuita (Hugging Face Spaces + Supabase + Groq + Copernicus; Render como alternativa).
- **BYOK con cero persistencia de credenciales:** las llaves del usuario se inyectan por sesión y se descartan; nunca se almacenan.
- **Servicio único (gateway):** un solo FastAPI sirve la UI Astro estática en `/` y la API en `/api` (mismo origen) — no hay servicio de UI aparte.
- **Procesamiento asíncrono nativo de Postgres:** colas PGMQ embebidas en Supabase (sin Redis/RabbitMQ).

---

## 2. Componentes Internos (C4 – Nivel Contenedor)

```mermaid
flowchart LR
    subgraph Cliente["Capa de Presentación"]
        UI["UI — Astro + Tailwind (SPA estática)<br/>──────────<br/>6 vistas · Leaflet-draw · Chart.js<br/>Estado efímero en memoria del navegador<br/>Servida por el gateway en /"]
    end

    subgraph Backend["Capa de Aplicación — Monolito Modular (FastAPI)"]
        direction TB
        API["API (routers por dominio)<br/>──────────<br/>CORS · proxy efímero de llaves<br/>/fields /ndvi /ndvi/raster /weather /chat<br/>/count (en desarrollo)"]
        LOGIC["services/ (negocio por dominio)<br/>──────────<br/>Parcels · RemoteSensing · Weather · Agent<br/>· Count (en desarrollo)"]
        subgraph Infra["Infraestructura de Soporte (inactiva hasta activar conteo)"]
            QUEUE["Cola — Supabase Queues (PGMQ)<br/>count_tasks (vt=120)"]
            WORKER["Worker Asíncrono<br/>Inferencia del modelo agnóstico (CPU)"]
            MODEL["Modelo predeterminado<br/>agrovision-plantcount (ONNX, HF Hub)"]
        end
    end

    subgraph Datos["Capa de Datos (Supabase)"]
        DB[("PostgreSQL + PostGIS<br/>fields · ndvi_timeseries<br/>plant_counts · chat_messages")]
        ST[("Storage privado<br/>drone-images + Signed URLs")]
    end

    UI -->|"fetch /api + X-User-*-Key (mismo origen)"| API
    API --> LOGIC
    LOGIC -->|"encola ortomosaico"| QUEUE
    QUEUE --> WORKER
    WORKER -->|"carga pesos"| MODEL
    LOGIC <-->|"asyncpg / SQL"| DB
    WORKER <-->|"persiste conteo"| DB
    WORKER <-->|"lee/escribe imágenes"| ST
```

**Flujo principal (crear parcela → teledetección), el que se construye ahora:**
1. En **Creación de Parcelas** el agrónomo dibuja el polígono (**Leaflet-draw**), lo nombra y guarda: `POST /api/fields` (con cabeceras BYOK) → `RemoteSensing`/`Parcels` persisten en `fields` (Supabase del usuario).
2. Al guardar, se dispara un **backfill** (background task) que consulta los **últimos 5 años** de NDVI (Sentinel-2, **agregado mensual**) y los persiste en `ndvi_timeseries`.
3. En **Teledetección** el usuario elige la parcela; la UI pide `POST /api/ndvi` (serie persistida + fechas nuevas) y `POST /api/weather` (Open-Meteo, on-demand) y los grafica (**Chart.js** doble eje). No se dibuja aquí.
4. Opcional: `POST /api/ndvi/raster` devuelve un PNG colorizado del **heatmap NDVI** (~10 m/px, Sentinel-2) recortado a la parcela; la UI lo pinta como `ImageOverlay` (read-only).
5. En **Resumen de Campo** los KPIs por parcela se leen de lo persistido; el **Asistente** consulta esas mismas tablas vía function calling.

**Flujo diferido (conteo por dron) — EN DESARROLLO, no se activa todavía:**
1. El agrónomo sube un ortomosaico (`ui.input_file`); la UI llama `POST /api/count` con cabeceras BYOK.
2. El gateway sube la imagen a Storage y envía un mensaje a la cola `count_tasks` (PGMQ).
3. El worker lee el mensaje (`vt=120`), carga el modelo agnóstico (`agrovision-plantcount`) y ejecuta la inferencia (con *tiling* si es grande).
4. El worker persiste el resultado en `plant_counts` y genera una **Signed URL** del overlay.
5. La UI sondea `GET /api/count/{id}` y, al estar `done`, renderiza conteo, densidad y overlay.
> Mientras `COUNTING_ENABLED=false`, la pestaña muestra "Módulo en preparación"; toda la infraestructura (cola/worker/tabla) existe pero está inactiva.

---

## 3. Lógica Core / Procesos Críticos

AgroVisión tiene tres motores internos relevantes (el de visión queda **en desarrollo**):

### 3.1 Pipeline de Visión (conteo) — EN DESARROLLO

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

### 3.2 Estadística Zonal NDVI (con default de 5 años y agregación mensual)

```mermaid
flowchart TB
    G(["GeoJSON del polígono + rango (default: últimos 5 años)"])
    S1["pystac-client: buscar escenas Sentinel-2 L2A<br/>(filtro eo:cloud_cover)"]
    S2["Recortar bandas B08/B04 al polígono"]
    S3["NDVI = (NIR-Red)/(NIR+Red) por píxel"]
    S4["Agregación zonal por escena: mean/min/max + cloud_cover"]
    S5["Agregación temporal MENSUAL (1 punto/mes, menor % nubes)"]
    O(["ndvi_timeseries (persistido)"])
    R(["/api/ndvi/raster → PNG heatmap NDVI<br/>~10 m/px, recortado a la parcela (no se persiste)"])
    G --> S1 --> S2 --> S3 --> S4 --> S5 --> O
    S3 --> R
```

> **Default de rango:** si la petición no trae fechas, el motor usa `[hoy − 5 años, última escena disponible]`. La **agregación mensual** mantiene 5 años por debajo del límite de Supabase Free (500 MB) y produce gráficos legibles. El **backfill** se ejecuta una vez al crear la parcela (background task); luego solo se añaden meses nuevos (incremental por `UNIQUE(field_id, date)`).
>
> **Heatmap NDVI:** la rama `/api/ndvi/raster` coloriza el array NDVI de una escena y lo devuelve como imagen para `ImageOverlay`. Resolución **satelital ~10 m/px** (Sentinel-2); el detalle cm/px solo es posible con dron **multiespectral** y queda ligado al módulo de Conteo (en desarrollo).

### 3.3 Agente RAG (Function Calling)

El agente (Llama 3 vía Groq) traduce la intención en llamadas tipadas: `get_vegetation_index_trend`, `get_weather_context`, `get_field_planting_density`. Plan típico de 3 pasos: verificar caída NDVI → correlacionar con clima → sintetizar diagnóstico.

---

## 4. Flujo de Secuencia (Conteo Asíncrono)

```mermaid
sequenceDiagram
    actor U as Agrónomo
    participant C as UI (Astro, en el navegador)
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
        HF["Hugging Face Spaces<br/>(1 contenedor Docker)<br/>gateway FastAPI: UI / + API /api"]
        SUPA[("Supabase<br/>PostGIS · Storage · PGMQ")]
        HF <-->|"asyncpg / HTTPS (BYOK)"| SUPA
    end

    Local -->|"git push al Space"| Pipeline
    Pipeline -->|"HF construye el Dockerfile"| Prod
```

**Notas de despliegue:**
- **Un solo servicio**: el `Dockerfile` de la raíz compila Astro (Node) y corre el gateway FastAPI que sirve UI + API en el mismo origen. Se publica con `git push` al repo del Space (`scripts/deploy_hf.ps1`); HF construye la imagen. Corre como **usuario no-root (1000)**.
- HF Spaces CPU básica da **16 GB RAM** (holgado para las deps); el Space **se duerme a las 48 h** sin uso (cold start 30–60 s). El **módulo de conteo arranca en standby** (`COUNTING_ENABLED=false`).
- **Alternativa: Render** (Docker, `backend/Dockerfile` + `render.yaml`); duerme a 15 min, 512 MB.
- Supabase Free **se pausa a los 7 días** sin actividad → keep-alive con cron ligero.
- *(shinyapps.io quedó descartado: solo hospeda Shiny, no FastAPI — ver ADR §7.)*

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
| **Hosting gratuito (Hugging Face Spaces + Supabase; Render alt.)** | Cloud administrado de pago (AWS/GCP) | Objetivo de costo cero y reproducibilidad; se asumen *caveats* (cold start, pausa, horas activas). |
| **Monolito modular (un FastAPI, `api/` + `services/`), microservices-ready** | Microservicios reales (un servicio por dominio) | En Render free cada servicio extra duerme a 15 min, suma cold-starts y complica CORS/operación. Un solo proceso con límites por dominio da la misma separación lógica ("cada uno específico") y se puede dividir luego sin tocar la UI. |
| **Creación de Parcelas como módulo propio (separado de Teledetección)** | Dibujar el polígono dentro de Teledetección (diseño previo, 5 módulos) | Separa responsabilidades: *delimitar* (escribe `fields`) vs *analizar* (solo lee/grafica). Teledetección queda read-only y enfocada en gráficos + heatmap. Pasa la UI a **6 módulos**. |
| **NDVI por defecto a 5 años con agregación mensual** | Rango corto fijo / sin agregación (todas las escenas) | Da histórico útil para "Resumen de campo" y el agente, y mantiene el volumen bajo el límite de Supabase Free; el backfill incremental evita recalcular. |
| **Heatmap NDVI satelital (~10 m/px) on-demand, sin persistir** | Persistir rásters NDVI / heatmap cm/px desde RGB | El ráster es pesado y efímero (se regenera); cm/px exige dron multiespectral (NIR), no disponible con RGB → se difiere con el módulo de Conteo. |
| **Conteo por dron arranca EN DESARROLLO (toda la infra creada, inactiva)** | Bloquear la plataforma hasta tener el modelo | Permite entregar parcelas/teledetección/agente ya; la cola/worker/tabla existen para activarse con solo `COUNTING_ENABLED=true` cuando el repo del modelo publique el artefacto. |
| **(Fase 8) UI migra a Astro + Tailwind (Agro-Stack); Shiny → legacy** | Mantener Shiny como UI principal / shell híbrido con iframe | La UI Shiny por defecto se ve básica; el objetivo es replicar el mockup (estética, **responsive**, plegables). Astro+Tailwind+JS (Leaflet/Chart.js) consumiendo `/api` da control total del look y deploy estático. El problema de enrutamiento SPA se mitiga con la **Regla de Oro** (una página, hash-routing, rutas relativas, CSS inline). |
| **(Fase 10) Eliminar Shiny por completo; UI = solo Astro** | Conservar Shiny como *legacy* en `/shiny` | El gateway ya servía Astro en `/`; mantener el dashboard Shiny solo sumaba dependencias pesadas (shiny/shinywidgets/ipyleaflet/plotly) y confusión. Se borró `backend/dashboard.py`, `run_ui.ps1` y esas deps → imagen más ligera y un solo camino de UI. |
| **(Fase 10) Despliegue a Hugging Face Spaces (Docker); descartado shinyapps.io** | shinyapps.io / Posit Connect (rsconnect) | **shinyapps.io solo hospeda apps Shiny, no FastAPI/ASGI** (verificado en su doc oficial); `rsconnect deploy fastapi` apunta a Posit Connect (de pago). HF Spaces (SDK Docker) es **gratis, FastAPI-nativo y con 16 GB RAM**: un `git push` y HF construye el `Dockerfile`. Render queda como alternativa Docker. Se eliminó `deploy_prod.ps1`/`.rscignore`/`rsconnect-python`. |

---

## 8. Seguridad — Modelo de Amenazas y Mitigaciones (Fase 10)

La nueva arquitectura es **un servicio público de un solo origen** (gateway en HF Spaces) bajo **BYOK**. Eso simplifica el modelo: **el servidor no guarda secretos de datos** (los pone cada usuario por sesión), así que un atacante no obtiene credenciales aunque comprometa la instancia.

### 8.1 Superficie de ataque y mitigaciones

| Amenaza | Riesgo | Mitigación (estado) |
| :--- | :--- | :--- |
| **DDoS / flood de la API** | Saturar la única instancia o agotar cuotas de APIs externas (BYOK) | **Rate limiting** en `/api` por IP (ventana deslizante en memoria, `RATE_LIMIT_PER_MIN`, 429 + `Retry-After`) ✅. Borde del host (HF) aporta protección de red volumétrica. *App-level mitiga abuso, no DDoS volumétrico de red.* |
| **Abuso del ingest de telemetría** (`POST /api/events`) | Spam de eventos | Buffer **acotado** (`deque(maxlen=500)`) ✅; persistencia **off por defecto** (`EVENTS_PERSIST=false`) ✅; cubierto por el rate limiting ✅. |
| **Fuga de secretos** | Exponer llaves BYOK | Nunca se persisten; viajan en cabeceras `X-User-*` y se descartan ✅. La telemetría **redacta** claves sensibles ✅. No se loguean cabeceras ✅. `.env` fuera del bundle (`.gitignore`) ✅. |
| **SSRF** (URLs de datos controladas por el usuario, p. ej. `X-User-Supabase-Url`) | Forzar al server a conectar a hosts internos | El usuario solo apunta a **su propia** BD; aun así, conviene **validar esquema/host** de `DATABASE_URL`/Supabase URL (📋 pendiente: allowlist de hosts `*.supabase.co`/`*.pooler.supabase.com`). |
| **Inyección de prompt** (agente RAG) | Manipular al LLM | El agente solo expone **3 herramientas tipadas de solo-lectura** sobre la BD; no ejecuta acciones destructivas ✅. (📋 reforzar con validación de argumentos.) |
| **Agotamiento de recursos** (polígonos enormes, heatmap) | OOM/CPU | `resx/resy` fijos y rango acotado en NDVI ✅; `MAX_UPLOAD_MB` en subidas ✅. (📋 validar área máx. de polígono.) |
| **Clickjacking / MIME sniffing / XSS heredado** | Embeber la app, sniffing | Cabeceras `X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff`, `Referrer-Policy` ✅. (📋 añadir `Content-Security-Policy` afinada para los CDNs usados.) |
| **CORS demasiado abierto** | Peticiones cross-site con credenciales | UI y API son **mismo origen** en HF (no requiere CORS). `ALLOWED_ORIGINS` se restringe por entorno ✅. |
| **Contenedor con privilegios** | Escalada si hay RCE | La imagen corre como **usuario no-root (1000)** ✅. |
| **Vulnerabilidades en dependencias** | CVEs transitivas | (📋 añadir escaneo `pip-audit`/Dependabot en CI). Se redujo superficie al **eliminar Shiny** y su árbol ✅. |

### 8.2 Defensa en profundidad (capas)

1. **Borde del host (HF Spaces):** TLS y protección de red base.
2. **Gateway:** rate limiting + cabeceras de hardening + tamaños de subida acotados.
3. **Datos (Supabase):** RLS por usuario (efectiva si se adopta Auth multiusuario), Storage privado + Signed URLs.
4. **BYOK:** sin secretos en el server → el impacto de un compromiso es mínimo.

> **Honestidad operativa:** el rate limiting es **por proceso/en memoria** (sirve para una sola instancia HF). Un DDoS volumétrico real se contrarresta en el **borde de red** del host, no a nivel de app. Los ítems 📋 quedan como trabajo de endurecimiento futuro (sub fase 10.4).
