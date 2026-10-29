# AgroVisión — Plan Maestro de Implementación

> **Propósito.** Este documento rige la estabilización, persistencia y refactorización arquitectónica de **AgroVisión** a partir de las especificaciones funcionales y técnicas del proyecto (`docs/description_proyecto.md`, `docs/architecture/architecture.md` y `docs/db/diseno_db.md`).
>
> **Persistencia:** Supabase (PostgreSQL 15+ con extensión PostGIS, RLS y PGMQ) como persistencia central en nube y local con soporte BYOK.
>
> **Tooling:** Python 3.11+ / uv (gestión de dependencias backend y linters), Node 22 / pnpm (Astro 5 y Tailwind 4 frontend), Docker (despliegue en Hugging Face Spaces / Render).
>
> **Cómo leer este documento:**
> - Cada **Fase** resuelve un macro-problema y tiene objetivos de alto nivel.
> - Cada Fase se divide en **Sub fases** (micro objetivos).
> - Cada Sub fase se divide en **Tareas** (micro procesos).
> - En este Plan Maestro **solo se llega hasta el nivel de Tarea** (las acciones atómicas se definen en el tablero `tareas.md` y archivos `fases/FNN-*.md`).
> - **Regla de Oro de Calidad:** Cada Fase, Sub fase y Tarea especifica claramente sus **Tests Unitarios** y **Tests de Simulación de Usuario**.

## Índice
1. [Convenciones y Nomenclatura](#1-convenciones-y-nomenclatura)
2. [Stack Tecnológico Definitivo](#2-stack-tecnologico-definitivo)
3. [Estructura Objetivo del Repositorio](#3-estructura-objetivo-del-repositorio)
4. [Datos de Referencia (Fixtures)](#4-datos-de-referencia-fixtures)
5. [Estrategia, Selección y Diseño de Base de Datos](#5-estrategia-seleccion-y-diseno-de-base-de-datos)
6. [Fases de Ejecución (Plan Maestro)](#6-fases-de-ejecucion-plan-maestro)
7. [Apéndices](#7-apendices)

---

## 1. Convenciones y Nomenclatura

- **Terminología de Negocio:**
  - *Parcela / Field:* Unidad de tierra agrícola delimitada geométricamente por un polígono en coordenadas geográficas WGS84 (EPSG:4326).
  - *Índices Espectrales:* Métricas de vegetación derivadas de bandas satelitales Sentinel-2 (NDVI, EVI, SAVI, NDWI, NDRE).
  - *Clima Horario:* Registros meteorológicos históricos de 13 variables obtenidos de Open-Meteo persistidos localmente.
  - *BYOK (Bring Your Own Key):* Modo de operación donde las credenciales externas (Supabase, Copernicus, Groq) se inyectan dinámicamente y no se persisten en disco de forma insegura.
- **Identificadores y Código:**
  - Backend: `snake_case` para funciones, métodos y variables; `PascalCase` para clases y esquemas Pydantic; `UPPER_CASE` para constantes.
  - Frontend: `PascalCase` para componentes Astro (`.astro`); `kebab-case` para carpetas y estilos; `camelCase` para variables y funciones JavaScript.
- **Reglas Arquitectónicas de Diseño:**
  - Monolito modular desacoplado: capa API (`backend/api`) delgada, lógica de negocio en servicios (`backend/services`), dominio puro y utilidades en core (`backend/core`), acceso a datos en repositorios (`backend/db/repositories.py`).
  - Idempotencia en migraciones: scripts DDL con `IF NOT EXISTS` / `DROP POLICY IF EXISTS`.
- **Convenciones Operativas:**
  - Linter Ruff sin advertencias con longitud máxima de línea de 100 caracteres.
  - Cobertura de tests unitarios y de simulación obligatoria en cada tarea.

---

## 2. Stack Tecnológico Definitivo

| Capa / Dominio | Tecnología | Versión | Justificación / Notas Técnicas |
|---|---|---|---|
| Lenguaje Core Backend | Python | 3.11+ (activo 3.14/3.13) | Ecosistema científico, soporte geoespacial (Shapely) y visión por computador. |
| Gestor de Paquetes Backend | uv | Latest | Resolución determinista ultrarrápida vía `uv.lock`. |
| API / Host Framework | FastAPI / Starlette | 0.115+ | Arquitectura asíncrona, validación OpenAPI estricta con Pydantic. |
| Persistencia y ORM | SQLAlchemy / asyncpg | 2.0+ | Consultas asíncronas de alto rendimiento y soporte PostGIS nativo. |
| Base de Datos | Supabase (PostgreSQL + PostGIS) | 15+ | Soporte geoespacial estándar, auth y extensiones vectoriales/PGMQ. |
| Framework UI / Frontend | Astro | 5.6+ | Arquitectura zero-JS por defecto, generación estática óptima para el gateway FastAPI. |
| Styling / Design System | Tailwind CSS | 4.0+ | Estilos atómicos integrados vía Vite plugin con paleta agronómica. |
| Testing Suite | pytest / Playwright | 8.0+ / 1.40+ | Pytest para unit/integración; Playwright para pruebas E2E y simulación de usuario. |

---

## 3. Estructura Objetivo del Repositorio

```text
AgroVision/
├── backend/
│   ├── api/                     # Routers FastAPI por dominio
│   ├── core/                    # Dominio puro, algoritmos espectrales y esquemas
│   ├── db/                      # Sesión asyncpg, repositorios y migrador
│   ├── services/                # Servicios de negocio (Copernicus, Clima, RAG, Parcelas)
│   ├── static/                  # Build estático de la UI Astro
│   └── main.py                  # Gateway FastAPI unificado
├── frontend/
│   ├── src/
│   │   ├── components/          # Componentes Astro modulares (layout, ui, modules)
│   │   │   ├── layout/          # Cabecera, sidebar, contenedor principal
│   │   │   ├── map/             # Visor Leaflet y controles de dibujo
│   │   │   ├── modules/         # Vistas de los 8 módulos desacopladas
│   │   │   └── ui/              # Modales, botones, badges, selectores
│   │   ├── pages/
│   │   │   └── index.astro      # Punto de entrada orquestador limpio
│   │   └── styles/              # Tailwind CSS 4 y variables globales
│   ├── package.json
│   └── astro.config.mjs
├── supabase/
│   └── migrations/              # Migraciones DDL SQL versionadas
├── docs/                        # Especificación, arquitectura, DB y planes
│   ├── plan/                    # Plan Maestro de implementación
│   ├── task/                    # Tablero tareas.md y fases/
│   └── logs/                    # Bitácora de incidentes
├── scripts/                     # Scripts de desarrollo, build y despliegue (sh + ps1)
├── tests/
│   ├── unit/                    # Tests unitarios rápidos sin dependencias externas
│   ├── integration/             # Tests con base de datos o mocks de servicios
│   └── e2e/                     # Tests de simulación de usuario Playwright
├── Dockerfile                   # Build multi-stage para Hugging Face Spaces
└── pyproject.toml               # Dependencias Python y configuración Ruff/pytest
```

---

## 4. Datos de Referencia (Fixtures)

**Escenario Canónico (Parcela Demo):**
- Polígono: Bounding Box en Ica, Perú `[-14.0678, -75.7286]` (polígono cerrado de 4 vértices).
- Superficie aproximada: 2.5 hectáreas.
- Banda Sentinel-2 canónica: B04 (Red: 0.12), B08 (NIR: 0.48).
- NDVI esperado: `(0.48 - 0.12) / (0.48 + 0.12) = 0.36 / 0.60 = 0.60` (vigor vegetal medio-alto).

---

## 5. Estrategia, Selección y Diseño de Base de Datos

La persistencia detallada se documenta en `docs/db/diseno_db.md`.
- **Estrategia DDL:** Migraciones SQL secuenciales e idempotentes bajo `supabase/migrations/` aplicables mediante `uv run python -m backend.db.migrate`.
- **Tablas Principales:**
  - `fields`: Almacena geometrías en columna `geom` tipo `geometry(Polygon, 4326)`.
  - `vegetation_indices`: Índices espectrales históricos por parcela y fecha.
  - `weather_data`: Historial climático horario por parcela.
  - `user_profiles`: Preferencias de sesión y perfiles agronómicos.
  - `plant_counts`: Resultados de conteo por dron (módulo en standby).
  - `chat_messages`: Memoria conversacional del agente.
  - `events`: Telemetría operativa.

---

## 6. Fases de Ejecución (Plan Maestro)

### Fase 1 — Estabilización Backend, Robustez de Tests y Tooling Cross-Platform
- **Macro-objetivo:** Eliminar los 11 errores del linter Ruff, resolver las fallas de `DATABASE_URL` en las pruebas unitarias alcanzando 100% pass, e incorporar scripts de ejecución bash para entornos Linux/macOS.
- **Entregable global:** Suite de tests unitarios al 100% en verde, `ruff check .` con 0 errores, y scripts `.sh` funcionales.
- **AC global de la Fase:**
  - `uv run ruff check .` retorna código 0 sin advertencias.
  - `uv run python -m pytest tests/unit -q` pasa 100% sin omitir ni fallar tests.
  - Los scripts `.sh` en `scripts/` se ejecutan correctamente en entornos POSIX.
- **Estrategia de Pruebas:**
  - **Tests Unitarios:** Verificación estática con Ruff y suite completa de tests en `tests/unit/`.
  - **Test de Simulación de Usuario:** Ejecución completa del ciclo `./scripts/build.sh` y ejecución de tests en terminal limpia.

#### Subfase 1.1 — Corrección de Linters y Conformidad Python
- **Micro-objetivo:** Corregir imports desordenados (E402) y líneas largas (E501).
- **Tarea T1.1.1:** Refactorizar imports y formatear cadenas largas en `backend/services/weather.py` y `backend/db/repositories.py`.
  - *AC:* Ruff pasa con 0 errores en todos los archivos.
  - *Test Unitario:* `uv run ruff check backend/`.
  - *Test Simulación Usuario:* Ejecución del hook de pre-commit o linter global sobre el workspace.

#### Subfase 1.2 — Aislamiento y Robustez de Pruebas Unitarias
- **Micro-objetivo:** Desacoplar los tests unitarios de perfiles de la variable `DATABASE_URL`.
- **Tarea T1.2.1:** Inyectar mock o dependency override para `get_db` en `tests/unit/test_profiles.py` o proveer fallback seguro en `backend/db/session.py`.
  - *AC:* `tests/unit/test_profiles.py` pasa completamente sin requerir conexión a base de datos.
  - *Test Unitario:* `uv run python -m pytest tests/unit/test_profiles.py`.
  - *Test Simulación Usuario:* `uv run python -m pytest tests/unit -q` con 0 fallas en entorno limpio sin `.env`.

#### Subfase 1.3 — Tooling y Scripts de Automatización Cross-Platform
- **Micro-objetivo:** Habilitar flujo de desarrollo sin dependencia exclusiva de PowerShell.
- **Tarea T1.3.1:** Crear scripts bash con permisos de ejecución (`scripts/build.sh`, `scripts/dev.sh`, `scripts/run_backend.sh`).
  - *AC:* Scripts ejecutables con validación de herramientas instaladas (`uv`, `pnpm`).
  - *Test Unitario:* Sintaxis de shell válida (`bash -n scripts/*.sh`).
  - *Test Simulación Usuario:* Ejecutar `./scripts/build.sh` y validar que genere los artefactos estáticos en `backend/static/`.

---

### Fase 2 — Esquema, DDL y Migraciones Versionadas de Base de Datos
- **Macro-objetivo:** Materializar las migraciones SQL formales en `supabase/migrations/` requeridas por `backend.db.migrate`, documentadas en `docs/db/diseno_db.md`, y configurar el control de versiones para evitar que git las ignore.
- **Entregable global:** Directorio `supabase/migrations/` con scripts DDL idempotentes y regla de excepción en `.gitignore`.
- **AC global de la Fase:**
  - Existe el archivo de migración `0001_initial_schema.sql` con PostGIS, tablas y RLS.
  - `.gitignore` permite trackear `supabase/migrations/*.sql`.
  - `apply_migrations` en `backend/db/migrate.py` localiza y valida los archivos de migración.
- **Estrategia de Pruebas:**
  - **Tests Unitarios:** Verificación de sintaxis SQL y existencia física de archivos.
  - **Test de Simulación de Usuario:** Ejecución de dry-run o migración contra base de datos de test/mock verificando creación de tablas e idempotencia en re-ejecución.

#### Subfase 2.1 — Estructura de Migraciones y Reglas Git
- **Micro-objetivo:** Configurar el directorio de migraciones y exceptuarlo en `.gitignore`.
- **Tarea T2.1.1:** Ajustar `.gitignore` con `!supabase/migrations/*.sql` y crear la carpeta `supabase/migrations/`.
  - *AC:* Git reconoce los archivos `.sql` dentro de `supabase/migrations/` como versionables.
  - *Test Unitario:* `git check-ignore supabase/migrations/0001_initial_schema.sql` retorna no ignorado.
  - *Test Simulación Usuario:* Inspección con `git status` detectando el archivo SQL.

#### Subfase 2.2 — Generación y Verificación de Migraciones SQL Idempotentes
- **Micro-objetivo:** Escribir el DDL canónico de AgroVisión en `supabase/migrations/0001_initial_schema.sql`.
- **Tarea T2.2.1:** Escribir el esquema completo (extensión postgis, tablas fields, vegetation_indices, weather_data, user_profiles, plant_counts, chat_messages, events, índices y políticas RLS).
  - *AC:* El script es 100% idempotente (`IF NOT EXISTS`).
  - *Test Unitario:* Validación sintáctica de las sentencias SQL.
  - *Test Simulación Usuario:* Ejecución de `backend.db.migrate.apply_migrations` y confirmación de que retorna los nombres de los scripts aplicados.

---

### Fase 3 — Refactorización y Modularización de la UI (Astro 5)
- **Macro-objetivo:** Descomponer el megamonolito de 3,299 líneas de `frontend/src/pages/index.astro` en componentes modulares limpios siguiendo `astro-standards` y `frontend-standards`, manteniendo intacta la funcionalidad y añadiendo comprobación de tipos.
- **Entregable global:** Estructura modular de componentes Astro en `frontend/src/components/`, `index.astro` reducido a orquestador (< 200 líneas), y script `check` en `package.json`.
- **AC global de la Fase:**
  - `frontend/src/pages/index.astro` tiene menos de 250 líneas.
  - El build `pnpm run build` en `frontend/` compila limpiamente a `backend/static/`.
  - Todos los 8 módulos funcionan visual e interactivamente igual que en la versión monolítica.
- **Estrategia de Pruebas:**
  - **Tests Unitarios:** Verificación de build de Astro y chequeo con `astro check`.
  - **Test de Simulación de Usuario:** Smoke test E2E (`tests/e2e/test_ui_smoke.py`) validando carga del mapa, modales y panel de control.

#### Subfase 3.1 — Tooling y Verificación Frontend
- **Micro-objetivo:** Incorporar herramientas de validación estática en el frontend.
- **Tarea T3.1.1:** Agregar script `"check": "astro check"` y dependencias requeridas en `frontend/package.json`.
  - *AC:* `pnpm run check` ejecuta la validación de sintaxis y tipos sin errores.
  - *Test Unitario:* Ejecución de `pnpm run check`.
  - *Test Simulación Usuario:* Build completo ejecutado desde pipeline local.

#### Subfase 3.2 — Extracción de Layout, Controles y Modales Base
- **Micro-objetivo:** Extraer elementos estructurales y de interfaz transversal.
- **Tarea T3.2.1:** Crear `Header.astro`, `Sidebar.astro`, `CredentialsModal.astro` y `TelemetryModal.astro` bajo `frontend/src/components/`.
  - *AC:* Componentes visuales desacoplados con props tipadas y slots según aplique.
  - *Test Unitario:* Renderizado aislado de componentes en Astro build.
  - *Test Simulación Usuario:* Apertura y cierre de modales de credenciales y telemetría en el navegador.

#### Subfase 3.3 — Modularización de Vistas de Dominio y Ensamblado de `index.astro`
- **Micro-objetivo:** Extraer los 8 módulos de negocio a `frontend/src/components/modules/` y simplificar `index.astro`.
- **Tarea T3.3.1:** Modularizar `ResumenCampo.astro`, `CreacionParcelas.astro`, `Teledeteccion.astro`, `ConteoDron.astro`, `AsistenteRAG.astro`, `ExploradorDatos.astro`.
  - *AC:* Cada módulo reside en su propio archivo autocontenido; `index.astro` solo orquesta.
  - *Test Unitario:* `pnpm run build` exitoso sin advertencias de componentes no encontrados.
  - *Test Simulación Usuario:* Recorrido de los 8 módulos en la interfaz verificando que todas las interacciones (dibujo en mapa, consultas, chat) se mantengan idénticas.

---

### Fase 4 — Persistencia de Índices Satelitales por Parcela
- **Macro-objetivo:** Extender el esquema de base de datos (`public.fields`) y la capa de repositorios (`backend/db/repositories.py`) para almacenar las variables satelitales seleccionadas por cada cultivo-parcela (`selected_indices`) y consultar qué variables ya poseen serie calculada en `vegetation_indices`, habilitando tanto la elección inicial como la expansión futura de variables.
- **Entregable global:** Migración idempotente `supabase/migrations/0002_field_selected_indices.sql`, actualización de `backend/db/repositories.py`, sincronización de `docs/db/diseno_db.md` y suite de tests unitarios de repositorio (`tests/unit/test_field_indices_repo.py`).
- **AC global de la Fase:**
  - `public.fields` cuenta con la columna `selected_indices TEXT[] NOT NULL DEFAULT ARRAY['ndvi']::TEXT[]` y constraint `chk_fields_selected_indices` que exige al menos un índice válido dentro de `('ndvi', 'evi', 'savi', 'ndwi', 'ndre')`.
  - `create_field`, `get_field`, `list_fields` y `update_field_attributes` en `backend/db/repositories.py` soportan `crop_variety` y `selected_indices`.
  - Nueva función `get_calculated_indices(session, field_id) -> list[str]` devuelve los `index_type` distintos presentes en `vegetation_indices` para la parcela.
  - `docs/db/diseno_db.md` refleja la columna `selected_indices` y la nueva migración `0002`.
- **Estrategia de Pruebas:**
  - **Tests Unitarios:** Validación de DDL en `0002_field_selected_indices.sql` y pruebas unitarias con sesión mockeada en `tests/unit/test_field_indices_repo.py`.
  - **Test de Simulación de Usuario:** Simulación de flujo de creación de parcela con `selected_indices=['ndvi', 'ndre']` y posterior ampliación a `['ndvi', 'ndre', 'ndwi']` verificando persistencia y lectura de índices calculados.

#### Subfase 4.1 — Migración DDL Idempotente y Documentación de BD
- **Micro-objetivo:** Añadir `selected_indices` a `public.fields` de forma idempotente y documentarlo en `docs/db/diseno_db.md`.
- **Tarea T4.1.1:** Crear `supabase/migrations/0002_field_selected_indices.sql` con `ADD COLUMN IF NOT EXISTS selected_indices` y constraint `chk_fields_selected_indices`, y actualizar `docs/db/diseno_db.md`.
  - *AC:* La migración es 100% idempotente y valida que `selected_indices <@ ARRAY['ndvi','evi','savi','ndwi','ndre']::TEXT[]` y `cardinality(selected_indices) >= 1`.
  - *Test Unitario:* Test que verifica existencia y estructura de `0002_field_selected_indices.sql`.
  - *Test Simulación Usuario:* Descubrimiento automático de ambas migraciones (`0001` y `0002`) por `backend.db.migrate`.

#### Subfase 4.2 — Extensión del Repositorio de Parcelas e Índices Calculados
- **Micro-objetivo:** Soportar lectura/escritura de `selected_indices` y consulta de índices ya calculados en `backend/db/repositories.py`.
- **Tarea T4.2.1:** Actualizar `create_field`, `get_field`, `list_fields`, `update_field_attributes` y añadir `get_calculated_indices` en `backend/db/repositories.py`, con su test suite en `tests/unit/test_field_indices_repo.py`.
  - *AC:* `create_field` acepta `crop_variety: str | None = None` y `selected_indices: list[str] | None = None` (default `["ndvi"]`); `update_field_attributes` permite actualizar `selected_indices`; `get_calculated_indices` retorna `list[str]`.
  - *Test Unitario:* `uv run python -m pytest tests/unit/test_field_indices_repo.py -q`.
  - *Test Simulación Usuario:* Flujo completo de alta y actualización incremental de `selected_indices` en el repositorio.

---

### Fase 5 — API y Backfill Selectivo/Incremental de Índices
- **Macro-objetivo:** Actualizar los esquemas de dominio (`FieldIn`, `FieldUpdate`, `ReprocessRequest`), el servicio de parcelas (`backend/services/parcels.py`) y los endpoints REST (`backend/api/fields.py`, `backend/api/vegetation.py`) para calcular al crear una parcela únicamente las variables satelitales elegidas por el usuario, y permitir en cualquier momento agregar más variables satelitales a una parcela existente disparando el backfill incremental solo de los nuevos índices.
- **Entregable global:** Esquemas actualizados en `backend/core/schemas.py`, `run_indices_backfill` en `backend/services/parcels.py`, endpoints extendidos en `backend/api/fields.py` y `backend/api/vegetation.py`, documentación en `docs/architect/architecture_agrovision.md` y tests en `tests/unit/test_parcel_indices_api.py`.
- **AC global de la Fase:**
  - `FieldIn` acepta `crop_variety: str | None = None` y `selected_indices: list[str] = ["ndvi"]` validando contra `{"ndvi", "evi", "savi", "ndwi", "ndre"}`.
  - `FieldUpdate` acepta `selected_indices: list[str] | None = None`.
  - `parcels.run_indices_backfill` calcula y guarda la serie de cada índice solicitado y mantiene `run_ndvi_backfill` como alias retrocompatible.
  - `POST /api/fields` persiste `crop_variety` y `selected_indices`, y agenda `run_indices_backfill` solo para los índices elegidos.
  - `PATCH /api/fields/{field_id}` detecta cuando se agregan nuevos índices en `selected_indices` y agenda en `BackgroundTasks` el cálculo incremental de los índices faltantes.
  - `POST /api/vegetation/reprocess` acepta `indices: list[str] | None = None` para calcular/reprocesar índices específicos y anexarlos a `selected_indices` de la parcela.
- **Estrategia de Pruebas:**
  - **Tests Unitarios:** Validación de esquemas Pydantic y pruebas de servicio/endpoints en `tests/unit/test_parcel_indices_api.py`.
  - **Test de Simulación de Usuario:** Simulación vía `TestClient` donde el usuario crea un campo de Arándanos eligiendo `["ndvi", "ndwi"]`, y posteriormente edita la parcela para añadir `"ndre"`, verificando que el backfill incremental se dispare únicamente para `"ndre"`.

#### Subfase 5.1 — Esquemas de Dominio y Backfill Multivariable en Servicio
- **Micro-objetivo:** Validar `selected_indices` en `FieldIn`/`FieldUpdate` e implementar `run_indices_backfill` en `backend/services/parcels.py`.
- **Tarea T5.1.1:** Extender `backend/core/schemas.py` y `backend/services/parcels.py` con soporte multivariable y retrocompatibilidad.
  - *AC:* Índices inválidos o listas vacías retornan error de validación 422; `run_indices_backfill` itera sobre los índices indicados y persiste cada serie.
  - *Test Unitario:* Pruebas unitarias de `FieldIn`, `FieldUpdate` y `run_indices_backfill`.
  - *Test Simulación Usuario:* Ejecución del servicio de creación y backfill con múltiples índices seleccionados.

#### Subfase 5.2 — Endpoints de Creación, Expansión Incremental y Reproceso Selectivo
- **Micro-objetivo:** Exponer la selección y adición futura de variables satelitales en `/api/fields` y `/api/vegetation/reprocess`.
- **Tarea T5.2.1:** Actualizar `backend/api/fields.py`, `backend/api/vegetation.py`, documentar en `docs/architect/architecture_agrovision.md` y crear `tests/unit/test_parcel_indices_api.py`.
  - *AC:* `GET /api/fields` y `GET /api/fields/{id}` incluyen `selected_indices` (y `calculated_indices` en el detalle); `PATCH /api/fields/{id}` dispara backfill en background para nuevos índices añadidos; `POST /api/vegetation/reprocess` soporta `indices: list[str] | None`.
  - *Test Unitario:* `uv run python -m pytest tests/unit/test_parcel_indices_api.py -q`.
  - *Test Simulación Usuario:* Flujo E2E de API (POST creación con 2 índices -> GET detalle -> PATCH agregando 1 índice adicional -> POST reprocess selectivo).

---

### Fase 6 — UI de Selección y Expansión de Variables Satelitales
- **Macro-objetivo:** Incorporar en el asistente de creación de parcelas (`CreacionParcelas.astro`) la selección de variables satelitales obtenidas desde Sentinel-2 (con sugerencia inteligente según el cultivo elegido), y permitir en una parcela ya creada (`AjustesParcela.astro`, `Teledeteccion.astro` y `ReprocessModal.astro`) agregar más variables satelitales en el futuro y disparar su cálculo sin perder las anteriores.
- **Entregable global:** Componentes Astro actualizados (`CreacionParcelas.astro`, `AjustesParcela.astro`, `Teledeteccion.astro`, `ReprocessModal.astro`), lógica cliente en `frontend/src/scripts/app.js` y pruebas de humo actualizadas en `tests/e2e/test_ui_smoke.py`.
- **AC global de la Fase:**
  - En `CreacionParcelas.astro`, al elegir el cultivo se muestra el selector de checkboxes de variables satelitales (`NDVI`, `EVI`, `SAVI`, `NDWI`, `NDRE`) con recomendación automática por cultivo pero editable por el usuario.
  - Al guardar la nueva parcela en `app.js`, se envían `crop_variety` y `selected_indices` al backend.
  - En `AjustesParcela.astro`, el usuario visualiza las variables satelitales activas de la parcela y puede marcar nuevas variables satelitales para agregarlas y calcularlas.
  - En `Teledeteccion.astro` y `ReprocessModal.astro`, se distinguen las variables activas/calculadas de la parcela y se permite añadir/calcular variables adicionales bajo demanda.
  - `pnpm run check` y `./scripts/build.sh` compilan con 0 errores ni advertencias.
- **Estrategia de Pruebas:**
  - **Tests Unitarios:** Diagnóstico estático `pnpm run check` y compilación `pnpm run build`.
  - **Test de Simulación de Usuario:** Pruebas en `tests/e2e/test_ui_smoke.py` verificando la presencia e interactividad de los selectores de variables satelitales en creación, ajustes y reproceso.

#### Subfase 6.1 — Selección de Variables Satelitales en el Alta de Parcela
- **Micro-objetivo:** Añadir la matriz de checkboxes de variables satelitales en `CreacionParcelas.astro` con preselección sugerida según cultivo.
- **Tarea T6.1.1:** Actualizar `frontend/src/components/modules/CreacionParcelas.astro` y la lógica de alta en `frontend/src/scripts/app.js`.
  - *AC:* El usuario puede elegir qué índices satelitales calcular al crear el lote; exige al menos 1 índice marcado; al cambiar el cultivo sugiere índices recomendados (ej. Arándanos -> NDVI + NDWI + NDRE, Paltos/Cítricos -> NDVI + EVI + NDRE, etc.).
  - *Test Unitario:* `cd frontend && pnpm run check`.
  - *Test Simulación Usuario:* Verificación del DOM compilado y flujo de envío de `selected_indices` en `POST /api/fields`.

#### Subfase 6.2 — Expansión Futura de Variables en Ajustes, Teledetección y Reproceso
- **Micro-objetivo:** Permitir que a cualquier cultivo-parcela existente se le puedan agregar más variables satelitales después de haber sido creada.
- **Tarea T6.2.1:** Actualizar `AjustesParcela.astro`, `Teledeteccion.astro`, `ReprocessModal.astro`, `frontend/src/scripts/app.js` y `tests/e2e/test_ui_smoke.py`.
  - *AC:* Desde `AjustesParcela` o `ReprocessModal` el usuario puede activar variables satelitales adicionales para la parcela activa y disparar su cálculo incremental; el selector `#select-index` en `Teledeteccion.astro` indica qué variables están activas y permite solicitar el cálculo si el usuario elige una variable aún no agregada.
  - *Test Unitario:* `./scripts/build.sh` y `cd frontend && pnpm run check`.
  - *Test Simulación Usuario:* `uv run python -m pytest tests/e2e/test_ui_smoke.py -q`.

---

### Fase 7 — Despliegue POSIX a Hugging Face Spaces
- **Estado:** [X] Fase 7 completada — Subfase 7.1 y Tarea 7.1.1 en verde (2026-10-28).
- **Macro-objetivo:** Proveer el script de despliegue en Bash (`scripts/deploy_hf.sh`) equivalente a `scripts/deploy_hf.ps1` para publicar el contenedor unificado (Frontend Astro + Backend FastAPI) en Hugging Face Spaces desde Linux/macOS, manteniendo limpio el contexto Docker (`.dockerignore`) y actualizada la guía de ejecución (`docs/ejecucion.md`).
- **Entregable global:** `scripts/deploy_hf.sh` ejecutable, `.dockerignore` actualizado, `docs/ejecucion.md` sincronizado y suite de tests `tests/unit/test_deploy_script.py`.
- **AC global de la Fase:**
  - `scripts/deploy_hf.sh` soporta `--force` y `--space <usuario/space>` (default `HF_SPACE_ID` o `alexp97/agrovision`), lee `HF_TOKEN` desde el entorno o `.env` sin exponerlo en logs, inyecta temporalmente `.huggingface_frontmatter` en `README.md` y lo restaura con `trap EXIT`.
  - `.dockerignore` excluye `.opencode/` y `.project-suite/`.
  - `docs/ejecucion.md` documenta el uso de `./scripts/deploy_hf.sh`.
  - `tests/unit/test_deploy_script.py` verifica permisos, sintaxis (`bash -n`) y validaciones del script.
- **Estrategia de Pruebas:**
  - **Tests Unitarios:** `uv run python -m pytest tests/unit/test_deploy_script.py -q` y `bash -n scripts/deploy_hf.sh`.
  - **Test de Simulación de Usuario:** Ejecución en seco / validación de argumentos y variables de `scripts/deploy_hf.sh`.

#### Subfase 7.1 — Script Bash `deploy_hf.sh`, Contexto Docker y Tests
- **Micro-objetivo:** Implementar `scripts/deploy_hf.sh`, limpiar `.dockerignore`, documentar en `docs/ejecucion.md` y cubrir con pruebas unitarias.
- **Tarea T7.1.1:** Crear `scripts/deploy_hf.sh`, actualizar `.dockerignore` y `docs/ejecucion.md`, y añadir `tests/unit/test_deploy_script.py`.
  - *AC:* `bash -n scripts/deploy_hf.sh` retorna 0; el script restaura `README.md` ante cualquier salida; `pytest tests/unit/test_deploy_script.py` pasa en verde.
  - *Test Unitario:* `uv run python -m pytest tests/unit/test_deploy_script.py -q`.
  - *Test Simulación Usuario:* Prueba de invocación sin token verificando mensaje de error controlado sin ensuciar `README.md`.

---

### Fase 8 — Plantilla .env.example Documentada con Ejemplos y Guías Paso a Paso
- **Estado:** [X] Fase 8 completada — Subfase 8.1 y Tarea 8.1.1 en verde (2026-10-28).
- **Macro-objetivo:** Mejorar `.env.example` y `docs/ejecucion.md` para explicar qué credenciales se necesitan realmente en cada escenario (uso BYOK en `https://alexp97-agrovision.hf.space` vs desarrollo local), incluyendo para cada variable un ejemplo de formato realista (dummy seguro) y la ruta exacta clic por clic dentro de cada plataforma (Supabase, Copernicus CDSE, Groq, Hugging Face) para obtenerla.
- **Entregable global:** `.env.example` rediseñado con ejemplos y rutas paso a paso, actualización de `docs/ejecucion.md` y suite de validación `tests/unit/test_env_example.py`.
- **AC global de la Fase:**
  - `.env.example` documenta en detalle cómo obtener `DATABASE_URL` en Supabase (botón superior **Connect** -> pestaña **Connection String** -> **Transaction pooler** o **Session pooler** -> copiar URI y anteponer `postgresql+asyncpg://`), junto con `SUPABASE_URL`, `SUPABASE_ANON_KEY` y `SUPABASE_SERVICE_ROLE_KEY` (**Project Settings -> Data API / API Keys**).
  - Cada variable de Supabase, Copernicus CDSE, Groq y Hugging Face incluye un ejemplo de formato explícito en comentarios y los pasos exactos para llegar al valor en la web oficial.
  - `tests/unit/test_env_example.py` valida que todas las claves requeridas, ejemplos de formato y guías paso a paso existan en `.env.example` sin exponer secretos reales.
- **Estrategia de Pruebas:**
  - **Tests Unitarios:** `uv run python -m pytest tests/unit/test_env_example.py -q`.
  - **Test de Simulación de Usuario:** Verificación de carga de `.env.example` con `dotenv_values` comprobando que ninguna clave tenga secretos reales y que todas las secciones estén documentadas.

#### Subfase 8.1 — Rediseño Pedagógico de `.env.example` y Tests de Plantilla
- **Micro-objetivo:** Documentar exhaustivamente `.env.example` y `docs/ejecucion.md` con ejemplos de formato y rutas de navegación en cada consola cloud.
- **Tarea T8.1.1:** Documentar paso a paso con ejemplos de formato `.env.example` y crear `tests/unit/test_env_example.py`.
  - *AC:* `.env.example` incluye instrucciones paso a paso y ejemplos de formato para Supabase, Copernicus, Groq y Hugging Face; `tests/unit/test_env_example.py` pasa al 100%.
  - *Test Unitario:* `uv run python -m pytest tests/unit/test_env_example.py -q`.
  - *Test Simulación Usuario:* `uv run ruff check .`.

---

### Fase 9 — Conexión BYOK Dinámica a Supabase del Usuario y Auto-Migración de Esquema en Backend
- **Macro-objetivo:** Lograr que AgroVisión en `https://alexp97-agrovision.hf.space` no dependa de ninguna base de datos global en el servidor: cada usuario se conecta con su propia base de datos Supabase por sesión (`X-User-Database-Url`), y si su base de datos está totalmente vacía, el backend ejecuta automáticamente las migraciones idempotentes (`0001_initial_schema.sql` + `0002_field_selected_indices.sql`) para construir toda la arquitectura PostGIS; si ya tiene la arquitectura y datos, los detecta y devuelve sus parcelas existentes.
- **Entregable global:** `backend/db/session.py` multi-DSN con `ensure_schema_initialized(dsn)`, `backend/api/deps.py` leyendo `X-User-Database-Url`, `backend/api/credentials.py` con `POST /api/credentials/connect-db` y `GET /api/credentials/status` consciente de headers BYOK, `backend/services/parcels.py` propagando el DSN del usuario al backfill en segundo plano, y suite de pruebas `tests/unit/test_byok_db_session.py`.
- **AC global de la Fase:**
  - `UserKeys` en `backend/api/deps.py` incluye `database_url: str | None` resuelto desde la cabecera `X-User-Database-Url` (con fallback a `DATABASE_URL` del entorno únicamente si no es el placeholder `<pwd>@<host>`).
  - `backend/db/session.py` cachea motores `AsyncEngine` y `async_sessionmaker` por DSN (`get_engine(dsn)` y `get_sessionmaker(dsn)`) y provee `ensure_schema_initialized(dsn: str) -> list[str]` que ejecuta `apply_migrations(dsn)` automáticamente una vez por DSN en memoria.
  - `get_db` en `backend/api/deps.py` usa el DSN del usuario (`keys.database_url`), ejecuta `await ensure_schema_initialized(dsn)` antes de abrir la primera sesión de ese DSN, y si no hay ningún DSN configurado lanza `HTTPException(status_code=503)` claro indicando que conecte su base de datos Supabase en Credenciales.
  - `POST /api/credentials/connect-db` valida la conexión al DSN provisto, ejecuta `ensure_schema_initialized(dsn)` para crear la arquitectura si la BD está vacía, cuenta cuántas parcelas existen en `public.fields` y retorna `{"connected": True, "schema_ready": True, "migrations_applied": [...], "existing_parcels": N}`.
  - `run_indices_backfill` en `backend/services/parcels.py` abre su sesión con `get_sessionmaker(keys.database_url)()`.
- **Estrategia de Pruebas:**
  - **Tests Unitarios:** `uv run python -m pytest tests/unit/test_byok_db_session.py -q`.
  - **Test de Simulación de Usuario:** Simulación con `TestClient` de dos usuarios con distintos `X-User-Database-Url`, verificando auto-migración en primera conexión, aislamiento de sesiones y respuesta de `POST /api/credentials/connect-db`.

#### Subfase 9.1 — Sesión Multi-DSN por Usuario y Auto-Bootstrap de Migraciones SQL
- **Micro-objetivo:** Implementar el enrutamiento dinámico de base de datos por usuario (`X-User-Database-Url`), la inicialización automática del esquema PostGIS cuando la BD del usuario es nueva y el endpoint de verificación/conexión `POST /api/credentials/connect-db`.
- **Tarea T9.1.1:** Soportar `X-User-Database-Url` dinámico, auto-migración idempotente y endpoint `POST /api/credentials/connect-db`.
  - *AC:* `get_engine(dsn)` y `get_sessionmaker(dsn)` soportan múltiples DSN por proceso; `ensure_schema_initialized(dsn)` aplica `0001` y `0002` una vez por DSN; `POST /api/credentials/connect-db` y `GET /api/credentials/status` funcionan con `X-User-Database-Url`.
  - *Test Unitario:* `uv run python -m pytest tests/unit/test_byok_db_session.py -q`.
  - *Test Simulación Usuario:* `uv run python -m pytest tests/unit -q && uv run ruff check .`.

---

### Fase 10 — UI de Credenciales Guiada y Auto-Conexión de Base de Datos BYOK
- **Macro-objetivo:** Actualizar el modal de credenciales (`CredentialsModal.astro`), la pestaña de ajustes (`AjustesPerfil.astro`) y la lógica cliente (`frontend/src/scripts/app.js`) para que el usuario pueda ingresar la URI de conexión PostgreSQL de su propio Supabase (`DATABASE_URL` — Direct / Transaction o Session Pooler) con instrucciones desplegables paso a paso y ejemplos claros para cada credencial (Supabase, Copernicus, Groq), enviando `X-User-Database-Url` en cada petición y disparando al guardar la conexión/auto-migración (`POST /api/credentials/connect-db`) y la recarga inmediata de sus parcelas (`loadParcels()`).
- **Entregable global:** `CredentialsModal.astro`, `AjustesPerfil.astro`, `frontend/src/scripts/app.js` y `tests/e2e/test_ui_smoke.py` actualizados, con compilación limpia en `./scripts/build.sh`.
- **AC global de la Fase:**
  - `CredentialsModal.astro` y `AjustesPerfil.astro` incluyen el campo **Supabase Database URI (`DATABASE_URL` — Transaction / Session Pooler)** (`#cred-db-url` / `#cfg-db-url`) además de los campos opcionales de Supabase, Copernicus y Groq, con un bloque de ayuda (`<details>`) que explica paso a paso cómo obtener cada valor y muestra un ejemplo del formato.
  - `authHeaders()` en `frontend/src/scripts/app.js` envía `X-User-Database-Url` cuando el usuario ingresó su URI de base de datos, y `updateStatus()` envía `authHeaders()` a `./api/credentials/status` para reflejar en verde las llaves activas de la sesión.
  - Al hacer clic en **"Usar en esta sesión"** en el modal de credenciales (o guardar en Ajustes), si el usuario ingresó su `DATABASE_URL`, `app.js` invoca `POST /api/credentials/connect-db` e inmediatamente recarga `loadParcels()` y el perfil.
  - `pnpm run check`, `./scripts/build.sh` y `tests/e2e/test_ui_smoke.py` pasan con 0 errores.
- **Estrategia de Pruebas:**
  - **Tests Unitarios:** `cd frontend && pnpm run check` y `./scripts/build.sh`.
  - **Test de Simulación de Usuario:** `uv run python -m pytest tests/e2e/test_ui_smoke.py -q`.

#### Subfase 10.1 — Modal y Panel de Credenciales con `DATABASE_URL`, Guías Paso a Paso y Auto-Carga de Parcelas
- **Micro-objetivo:** Incorporar el campo de conexión directa a la BD de Supabase del usuario (`#cred-db-url` / `#cfg-db-url`), las ayudas paso a paso con ejemplos en la UI, y el flujo de auto-conexión y recarga de datos en `app.js`.
- **Tarea T10.1.1:** Actualizar `CredentialsModal.astro`, `AjustesPerfil.astro`, `app.js` y `test_ui_smoke.py`.
  - *AC:* Existen `#cred-db-url` y `#cfg-db-url` con ejemplos y guía paso a paso; `app.js` envía `X-User-Database-Url`, invoca `./api/credentials/connect-db` y recarga `loadParcels()`.
  - *Test Unitario:* `cd frontend && pnpm run check && cd .. && ./scripts/build.sh`.
  - *Test Simulación Usuario:* `uv run python -m pytest tests/e2e/test_ui_smoke.py -q`.

---

## 7. Apéndices

### Apéndice A — Definition of Done (DoD) Global
Para marcar como completada (`[X]`) cualquier Tarea, se debe cumplir obligatoriamente:
1. **Tests Unitarios:** Pasando en verde sin advertencias ni omisiones no justificadas.
2. **Tests de Simulación de Usuario:** Pasando y validando el flujo del usuario.
3. **Calidad de Código / Linting:** `uv run ruff check .` limpio (código 0) y `pnpm run build` exitoso.
4. **Documentación:** Cualquier modificación de API o esquema debe reflejarse en `docs/architecture/architecture.md` o `docs/db/diseno_db.md`.
5. **Bitácora:** Ante cualquier anomalía surgida durante la ejecución, debe quedar registrada en `docs/logs/log.md`.
