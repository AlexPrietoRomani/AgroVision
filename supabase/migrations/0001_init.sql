-- =====================================================================================
-- AgroVisión — Migración inicial (Fase 2): extensiones, tablas e índices.
-- Idempotente (if not exists). Deriva de docs/db/diseno_db.md.
-- Nota BYOK monousuario: user_id es uuid SIN FK a auth.users (no usamos Supabase Auth;
-- la conexión es directa por DATABASE_URL). plant_counts y la cola PGMQ se crean pero
-- quedan INACTIVAS (módulo de Conteo en desarrollo).
-- =====================================================================================

create extension if not exists postgis;        -- geometría/geografía
create extension if not exists pgmq;            -- cola del conteo (EN DESARROLLO, inactiva)

-- 1. Parcelas / lotes agrícolas
create table if not exists fields (
  id uuid primary key default gen_random_uuid(),
  user_id uuid,                                 -- propietario (sin FK: BYOK monousuario)
  name text not null,
  geom geometry(Polygon, 4326) not null,        -- WGS84
  created_at timestamptz default now()
);
create index if not exists fields_geom_gist_idx on fields using gist (geom);

-- 2. Serie temporal NDVI (Sentinel-2), agregada por mes
create table if not exists ndvi_timeseries (
  id serial primary key,
  field_id uuid references fields(id) on delete cascade,
  date date not null,
  mean_ndvi double precision not null,
  min_ndvi double precision,
  max_ndvi double precision,
  cloud_cover double precision,
  source text default 'sentinel2',
  constraint unique_field_date unique (field_id, date)
);
create index if not exists ndvi_field_date_idx on ndvi_timeseries (field_id, date);

-- 3. Conteos por dron (EN DESARROLLO: sin escrituras hasta COUNTING_ENABLED=true)
create table if not exists plant_counts (
  id serial primary key,
  user_id uuid,
  field_id uuid references fields(id) on delete set null,
  image_url text not null,
  count integer not null check (count >= 0),
  result_json jsonb,
  processed_at timestamptz default now()
);
create index if not exists plant_counts_json_gin_idx on plant_counts using gin (result_json);

-- 4. Memoria conversacional del agente RAG
create table if not exists chat_messages (
  id serial primary key,
  user_id uuid,
  session_id text not null,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  created_at timestamptz default now()
);
create index if not exists chat_session_history_idx on chat_messages (session_id, created_at);
