-- AgroVisión — Migración 0004: Índices espectrales adicionales (Fase 13)
-- Tabla genérica para EVI, SAVI, NDWI, NDRE + heatmaps cacheados.
-- Idempotente (if not exists).

create table if not exists vegetation_indices (
  id serial primary key,
  field_id uuid references fields(id) on delete cascade,
  index_type text not null check (index_type in ('ndvi', 'evi', 'savi', 'ndwi', 'ndre')),
  date date not null,
  mean_value double precision not null,
  min_value double precision,
  max_value double precision,
  cloud_cover double precision,
  source text default 'sentinel2',
  constraint unique_field_index_date unique (field_id, index_type, date)
);

create index if not exists veg_idx_field_type_date on vegetation_indices (field_id, index_type, date);
