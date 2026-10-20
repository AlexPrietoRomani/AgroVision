-- ============================================================================
-- Archivo: 0001_initial_schema.sql
-- Fecha de modificación: 20/10/2026
-- Autor: Alex Prieto Romani <alexprieto1997@gmail.com>
--
-- Descripción:
-- Migración inicial idempotente del esquema físico de AgroVisión. Materializa el
-- modelo documentado en docs/db/diseno_db.md §3: parcelas con geometría PostGIS,
-- series de índices espectrales, clima horario, perfiles, conteos y telemetría.
-- Se aplica con `uv run python -m backend.db.migrate` o con `supabase db push`.
--
-- Idempotencia:
-- Todas las sentencias usan IF NOT EXISTS, DROP POLICY IF EXISTS o ENABLE ROW
-- LEVEL SECURITY (idempotente) para que el archivo pueda ejecutarse repetidamente.
--
-- Reversa:
-- El bloque `down` está documentado al final del archivo, comentado, para no ser
-- ejecutado por `backend.db.migrate` (que recorre todos los `*.sql` en orden).
-- ============================================================================

BEGIN;

-- Extensión espacial: tipos GEOMETRY, ST_IsValid, ST_Area e índices GIST.
CREATE EXTENSION IF NOT EXISTS postgis;

-- ----------------------------------------------------------------------------
-- 1. Parcelas agrícolas
--    `user_id` admite NULL porque el modo BYOK monousuario crea parcelas sin
--    identidad de Supabase Auth; el gateway sigue siendo el único escritor.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.fields (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    user_id UUID,
    name TEXT NOT NULL,
    geom GEOMETRY(Polygon, 4326) NOT NULL,
    crop_variety TEXT,
    field_type TEXT,
    soil_type TEXT,
    irrigation_system TEXT,
    pests_diseases TEXT,
    plantation_date DATE,
    num_plants INTEGER,
    historical_yield TEXT,
    target_market TEXT,
    document_metadata TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT pk_fields PRIMARY KEY (id),
    CONSTRAINT chk_fields_geom_valid CHECK (ST_IsValid(geom)),
    CONSTRAINT chk_fields_num_plants_nonnegative CHECK (num_plants IS NULL OR num_plants >= 0)
);

CREATE INDEX IF NOT EXISTS fields_geom_gist_idx
    ON public.fields USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_fields_user_id
    ON public.fields (user_id);

-- ----------------------------------------------------------------------------
-- 2. Serie temporal de índices espectrales (Sentinel-2, agregada por mes)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.vegetation_indices (
    id SERIAL NOT NULL,
    field_id UUID,
    index_type TEXT NOT NULL,
    date DATE NOT NULL,
    mean_value DOUBLE PRECISION NOT NULL,
    min_value DOUBLE PRECISION,
    max_value DOUBLE PRECISION,
    cloud_cover DOUBLE PRECISION,
    source TEXT NOT NULL DEFAULT 'sentinel2',
    CONSTRAINT pk_vegetation_indices PRIMARY KEY (id),
    CONSTRAINT fk_vegetation_indices_fields
        FOREIGN KEY (field_id) REFERENCES public.fields (id) ON DELETE CASCADE,
    CONSTRAINT uq_vegetation_indices_field_type_date
        UNIQUE (field_id, index_type, date),
    CONSTRAINT chk_vegetation_indices_index_type
        CHECK (index_type IN ('ndvi', 'evi', 'savi', 'ndwi', 'ndre')),
    CONSTRAINT chk_vegetation_indices_cloud_cover
        CHECK (cloud_cover IS NULL OR (cloud_cover >= 0 AND cloud_cover <= 100))
);

-- El UNIQUE (field_id, index_type, date) ya crea el índice que cubre las
-- consultas de serie por parcela/índice/fecha (`vegetation_indices_field_type_date_idx`
-- en diseno_db.md §5.1). No se duplica para evitar mantenimiento innecesario.

-- ----------------------------------------------------------------------------
-- 3. Perfiles de usuario y preferencias de sesión
--    `active_field_id` se anula (SET NULL) si se elimina la parcela activa.
--    `session_mode` usa los valores que valida la API: ephemeral|saved|shared.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.user_profiles (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    display_name VARCHAR(100) NOT NULL,
    supabase_url_hash VARCHAR(64) NOT NULL,
    active_field_id UUID,
    preferences JSONB NOT NULL DEFAULT '{}'::JSONB,
    session_mode VARCHAR(20) NOT NULL DEFAULT 'ephemeral',
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT pk_user_profiles PRIMARY KEY (id),
    CONSTRAINT uq_user_profiles_supabase_url_hash UNIQUE (supabase_url_hash),
    CONSTRAINT fk_user_profiles_fields
        FOREIGN KEY (active_field_id) REFERENCES public.fields (id) ON DELETE SET NULL,
    CONSTRAINT chk_user_profiles_session_mode
        CHECK (session_mode IN ('ephemeral', 'saved', 'shared'))
);

CREATE INDEX IF NOT EXISTS idx_user_profiles_active_field_id
    ON public.user_profiles (active_field_id);

-- ----------------------------------------------------------------------------
-- 4. Clima horario por parcela (13 variables de Open-Meteo)
--    UNIQUE (field_id, timestamp) habilita los upserts idempotentes.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.weather_data (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    field_id UUID,
    timestamp TIMESTAMPTZ NOT NULL,
    temperature_2m REAL,
    relative_humidity_2m REAL,
    dewpoint_2m REAL,
    cloud_cover REAL,
    pressure_msl REAL,
    wind_speed_10m REAL,
    wind_direction_10m REAL,
    precipitation REAL,
    shortwave_radiation REAL,
    et0_fao_evapotranspiration REAL,
    vapour_pressure_deficit REAL,
    soil_temperature_0_to_7cm REAL,
    soil_moisture_0_to_7cm REAL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_weather_data PRIMARY KEY (id),
    CONSTRAINT fk_weather_data_fields
        FOREIGN KEY (field_id) REFERENCES public.fields (id) ON DELETE CASCADE,
    CONSTRAINT uq_weather_data_field_timestamp UNIQUE (field_id, timestamp)
);

CREATE INDEX IF NOT EXISTS weather_data_field_timestamp_idx
    ON public.weather_data (field_id, timestamp DESC);

-- ----------------------------------------------------------------------------
-- 5. Conteos por dron (módulo en standby; la tabla se crea pero no se escribe
--    hasta activar COUNTING_ENABLED=true)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.plant_counts (
    id SERIAL NOT NULL,
    user_id UUID,
    field_id UUID,
    image_url TEXT NOT NULL,
    count INTEGER NOT NULL,
    result_json JSONB,
    processed_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT pk_plant_counts PRIMARY KEY (id),
    CONSTRAINT fk_plant_counts_fields
        FOREIGN KEY (field_id) REFERENCES public.fields (id) ON DELETE SET NULL,
    CONSTRAINT chk_plant_counts_count_nonnegative CHECK (count >= 0)
);

CREATE INDEX IF NOT EXISTS plant_counts_json_gin_idx
    ON public.plant_counts USING GIN (result_json);
CREATE INDEX IF NOT EXISTS idx_plant_counts_field_id
    ON public.plant_counts (field_id);
CREATE INDEX IF NOT EXISTS idx_plant_counts_user_id
    ON public.plant_counts (user_id);

-- ----------------------------------------------------------------------------
-- 6. Memoria conversacional del agente RAG
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.chat_messages (
    id SERIAL NOT NULL,
    user_id UUID,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    field_id UUID,
    CONSTRAINT pk_chat_messages PRIMARY KEY (id),
    CONSTRAINT fk_chat_messages_fields
        FOREIGN KEY (field_id) REFERENCES public.fields (id) ON DELETE SET NULL,
    CONSTRAINT chk_chat_messages_role CHECK (role IN ('user', 'assistant'))
);

CREATE INDEX IF NOT EXISTS chat_session_history_idx
    ON public.chat_messages (session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_chat_messages_field_id
    ON public.chat_messages (field_id);

-- ----------------------------------------------------------------------------
-- 7. Telemetría de UI/backend (persistencia opcional con EVENTS_PERSIST=true)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.events (
    id BIGSERIAL NOT NULL,
    action TEXT NOT NULL,
    session_id TEXT NOT NULL,
    meta JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT pk_events PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS events_session_created_idx
    ON public.events (session_id, created_at);

-- ----------------------------------------------------------------------------
-- 8. Row Level Security (defensa en profundidad)
--    El gateway accede con el rol propietario (bypass de RLS); las políticas
--    protegen accesos directos con las llaves anon/authenticated de Supabase.
--    En PostgreSQL local sin esquema `auth` las políticas se omiten sin fallar.
-- ----------------------------------------------------------------------------
ALTER TABLE public.fields ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vegetation_indices ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.weather_data ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.plant_counts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.events ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF to_regprocedure('auth.uid()') IS NOT NULL
       AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        -- Parcelas: cada usuario autenticado solo ve y modifica las suyas.
        DROP POLICY IF EXISTS fields_owner_all ON public.fields;
        CREATE POLICY fields_owner_all ON public.fields
            FOR ALL TO authenticated
            USING (auth.uid() = user_id)
            WITH CHECK (auth.uid() = user_id);

        -- Índices espectrales: acceso derivado del dueño de la parcela.
        DROP POLICY IF EXISTS vegetation_indices_owner_all ON public.vegetation_indices;
        CREATE POLICY vegetation_indices_owner_all ON public.vegetation_indices
            FOR ALL TO authenticated
            USING (
                EXISTS (
                    SELECT 1
                    FROM public.fields AS f
                    WHERE f.id = vegetation_indices.field_id
                      AND f.user_id = auth.uid()
                )
            )
            WITH CHECK (
                EXISTS (
                    SELECT 1
                    FROM public.fields AS f
                    WHERE f.id = vegetation_indices.field_id
                      AND f.user_id = auth.uid()
                )
            );

        -- Clima: acceso derivado del dueño de la parcela.
        DROP POLICY IF EXISTS weather_data_owner_all ON public.weather_data;
        CREATE POLICY weather_data_owner_all ON public.weather_data
            FOR ALL TO authenticated
            USING (
                EXISTS (
                    SELECT 1
                    FROM public.fields AS f
                    WHERE f.id = weather_data.field_id
                      AND f.user_id = auth.uid()
                )
            )
            WITH CHECK (
                EXISTS (
                    SELECT 1
                    FROM public.fields AS f
                    WHERE f.id = weather_data.field_id
                      AND f.user_id = auth.uid()
                )
            );

        -- Conteos: cada usuario autenticado solo ve y crea los suyos.
        DROP POLICY IF EXISTS plant_counts_owner_all ON public.plant_counts;
        CREATE POLICY plant_counts_owner_all ON public.plant_counts
            FOR ALL TO authenticated
            USING (auth.uid() = user_id)
            WITH CHECK (auth.uid() = user_id);

        -- Chat: cada usuario autenticado solo ve y escribe su conversación.
        DROP POLICY IF EXISTS chat_messages_owner_all ON public.chat_messages;
        CREATE POLICY chat_messages_owner_all ON public.chat_messages
            FOR ALL TO authenticated
            USING (auth.uid() = user_id)
            WITH CHECK (auth.uid() = user_id);

        -- `user_profiles` y `events` quedan sin políticas para clientes:
        -- solo el rol propietario (gateway) puede leerlos/escribirlos.
    END IF;
END
$$;

COMMIT;

-- ============================================================================
-- Reversa (down) — ejecutar manualmente solo para deshacer esta migración.
-- Este bloque está comentado a propósito: `backend.db.migrate` ejecuta el
-- archivo completo y no debe borrar el esquema en una re-ejecución.
-- ============================================================================
-- BEGIN;
-- DROP TABLE IF EXISTS public.events CASCADE;
-- DROP TABLE IF EXISTS public.chat_messages CASCADE;
-- DROP TABLE IF EXISTS public.plant_counts CASCADE;
-- DROP TABLE IF EXISTS public.weather_data CASCADE;
-- DROP TABLE IF EXISTS public.user_profiles CASCADE;
-- DROP TABLE IF EXISTS public.vegetation_indices CASCADE;
-- DROP TABLE IF EXISTS public.fields CASCADE;
-- COMMIT;
