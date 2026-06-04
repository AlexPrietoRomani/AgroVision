-- =====================================================================================
-- AgroVisión — Telemetría de UI (Fase 9, SF9.3): tabla `events`.
-- Persistencia OPCIONAL de eventos de la UI para depurar. Sólo se escribe si
-- EVENTS_PERSIST=true (best-effort: un fallo de BD nunca rompe la UI). Idempotente.
-- NUNCA contiene secretos: el backend redacta `meta` antes de insertar.
-- =====================================================================================

create table if not exists events (
  id bigserial primary key,
  action text not null,                 -- p. ej. 'nav', 'creds_set', 'parcel_create', 'error'
  session_id text not null,             -- correlación por sesión de UI
  meta jsonb not null default '{}'::jsonb,  -- contexto (ya redactado, sin secretos)
  created_at timestamptz default now()
);

-- Consulta típica de depuración: traza de una sesión ordenada por tiempo.
create index if not exists events_session_created_idx on events (session_id, created_at);
