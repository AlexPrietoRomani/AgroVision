# Listado de Tareas — AgroVisión

> **Fuentes de contexto obligatorias:**
> - Spec funcional/lógico: [`docs/description_proyecto.md`](../description_proyecto.md).
> - Plan maestro (Fases, Sub fases y arquitectura): [`docs/plan/plan_maestro.md`](../plan/plan_maestro.md).
> - Diseño de Base de Datos: [`docs/db/diseno_db.md`](../db/diseno_db.md).
>
> **Persistencia y Aprendizaje de Errores (Bitácora de Incidentes):**
> - **Consulta Obligatoria:** Ante cualquier complicación, error recurrente o bloqueo durante el desarrollo de una tarea, el desarrollador (o agente de IA) debe revisar obligatoriamente [`docs/logs/log.md`](../logs/log.md) para verificar si el incidente ya fue resuelto previamente.
> - **Mapeo de Nuevos Errores:** Si el error no ha sido documentado, se debe abrir un apartado en `docs/logs/log.md` describiendo detalladamente los síntomas y el contexto.
> - **Registro de Solución:** Una vez resuelto, se debe registrar el diagnóstico de causa raíz y la solución implementada para consolidar el conocimiento y evitar reincidir en el mismo error.
>
> **Convenciones de Checkboxes:**
> - `[ ]` Pendiente
> - `[/]` En progreso / En revisión
> - `[X]` Completado
> - **Invariante de progreso:** Una Tarea solo se marca completada (`[X]`) si todas sus Acciones asociadas están en `[X]` y sus Criterios de Aceptación y Tests pasan de forma limpia. Una Sub fase se completa si todas sus Tareas lo están, y una Fase se completa si todas sus Sub fases lo están.
>
> **Convenciones de Identificadores (IDs):**
> - **Fase:** `F{n}` — ej. `F1`
> - **Sub fase:** `SF{f}.{n}` — ej. `SF1.1`
> - **Tarea:** `T{f}.{sf}.{n}` — ej. `T1.1.2` (Fase 1, Sub fase 1, Tarea 2)
> - **Acción:** `A{f}.{sf}.{t}.{n}` — ej. `A1.1.2.3` (Fase 1, Sub fase 1, Tarea 2, Acción 3)
>
> **Reajuste dinámico:** El plan se corrige sobre la marcha. Al cerrar una Sub fase, lo aprendido puede reescribir las Sub fases pendientes de la misma Fase; el trabajo correctivo entra como **Tareas dentro de la Fase en curso**, nunca como una Fase nueva al final. Todo bloque que la ejecución haya corregido lleva `> ⟳ Ajustado en SF{x.y} — <motivo>` al inicio.
>
> **Regla Maestra de Calidad:** Cada Fase, Sub fase, Tarea y Acción debe detallar y ejecutar obligatoriamente **Tests Unitarios** (aislados del sistema) y **Tests de Simulación de Usuario** (comportamiento/E2E/integración que replique la experiencia del usuario interactuando con el entregable). Una Tarea solo se marca completada si todas sus Acciones están en `[X]` y sus AC se cumplen; una Fase solo se marca completada si todas sus sub Fases lo están.
>
> **Estructura obligatoria de cada Tarea (didáctica y reproducible):** además de Objetivo / Entregable / AC / Tests, **toda Tarea debe incluir** dos bloques que la hagan autoexplicativa:
> - **🧠 Explicación:** Qué es cada parte y *por qué* se hace así (concepto + decisión de diseño), en lenguaje claro para cualquier desarrollador o agente de IA.
> - **💡 Cómo hacerlo (ejemplo):** Uno o más bloques de **código o comandos reales y adaptables** que muestren cómo implementar la Tarea.

---

## Índice de Fases y Sub fases

<!-- indice-tareas:inicio -->

> Una Fase por archivo, bajo [`fases/`](fases/). Regenerar con
> `python scripts/tablero.py --indice`; `--verificar` avisa si quedo viejo.

- [ ] [**F8 — Plantilla .env.example Documentada con Ejemplos y Guías Paso a Paso**](fases/F08-plantilla-env-example-guiada-paso-a-paso.md)
  - [ ] SF8.1 — Rediseño Pedagógico de `.env.example` y Tests de Plantilla
- [X] [**F9 — Conexión BYOK Dinámica a Supabase del Usuario y Auto-Migración de Esquema en Backend**](fases/F09-conexion-byok-dinamica-supabase-y-auto-migracion.md)
  - [X] SF9.1 — Sesión Multi-DSN por Usuario y Auto-Bootstrap de Migraciones SQL
- [ ] [**F10 — UI de Credenciales Guiada y Auto-Conexión de Base de Datos BYOK**](fases/F10-ui-credenciales-guiadas-y-autoconexion-bd.md)
  - [ ] SF10.1 — Modal y Panel de Credenciales con `DATABASE_URL`, Guías Paso a Paso y Auto-Carga de Parcelas

<!-- indice-tareas:fin -->

> El bloque de arriba lo genera automáticamente `python scripts/tablero.py --indice` leyendo `fases/`.
