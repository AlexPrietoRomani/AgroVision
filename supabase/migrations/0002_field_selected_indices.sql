-- ============================================================================
-- Archivo: 0002_field_selected_indices.sql
-- Fecha de modificación: 28/10/2026
-- Autor: Alex Prieto Romani <alexprieto1997@gmail.com>
--
-- Descripción:
-- Añade a `public.fields` la columna `selected_indices` (variables satelitales
-- elegidas por cultivo-parcela) y el constraint que restringe sus valores al
-- catálogo de índices espectrales soportados. Materializa el modelo documentado
-- en docs/db/diseno_db.md §3.1 y §5.3 (migración 0002).
--
-- Idempotencia:
-- La columna usa ADD COLUMN IF NOT EXISTS y el constraint se recrea con
-- DROP CONSTRAINT IF EXISTS antes de ADD CONSTRAINT, por lo que el archivo puede
-- ejecutarse repetidamente sin fallar ni duplicar objetos.
--
-- Reversa:
-- El bloque `down` está documentado al final del archivo, comentado, para no ser
-- ejecutado por `backend.db.migrate` (que recorre todos los `*.sql` en orden).
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. Variables satelitales seleccionadas por parcela
--    El default `ARRAY['ndvi']` mantiene compatibles las parcelas preexistentes
--    y el flujo NDVI histórico. El CHECK exige al menos un índice y prohíbe
--    valores fuera del catálogo Sentinel-2 soportado por la aplicación.
-- ----------------------------------------------------------------------------
ALTER TABLE public.fields
    ADD COLUMN IF NOT EXISTS selected_indices TEXT[] NOT NULL
    DEFAULT ARRAY['ndvi']::TEXT[];

ALTER TABLE public.fields
    DROP CONSTRAINT IF EXISTS chk_fields_selected_indices;

ALTER TABLE public.fields
    ADD CONSTRAINT chk_fields_selected_indices
    CHECK (
        cardinality(selected_indices) >= 1
        AND selected_indices <@ ARRAY['ndvi', 'evi', 'savi', 'ndwi', 'ndre']::TEXT[]
    );

COMMIT;

-- ============================================================================
-- Reversa (down) — ejecutar manualmente solo para deshacer esta migración.
-- Este bloque está comentado a propósito: `backend.db.migrate` ejecuta el
-- archivo completo y no debe borrar la columna en una re-ejecución.
-- ============================================================================
-- BEGIN;
-- ALTER TABLE public.fields DROP CONSTRAINT IF EXISTS chk_fields_selected_indices;
-- ALTER TABLE public.fields DROP COLUMN IF EXISTS selected_indices;
-- COMMIT;
