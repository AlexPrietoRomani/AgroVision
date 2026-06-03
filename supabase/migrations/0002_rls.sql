-- =====================================================================================
-- AgroVisión — Políticas RLS (Fase 2): aislamiento por usuario (defensa en profundidad).
--
-- IMPORTANTE: con la conexión directa por DATABASE_URL (rol 'postgres', dueño de las
-- tablas) RLS queda BYPASSEADA — es el modo BYOK monousuario actual. Estas políticas se
-- vuelven efectivas si en el futuro se adopta Supabase Auth multiusuario (acceso vía
-- PostgREST con JWT, donde auth.uid() devuelve el usuario). Idempotente.
-- =====================================================================================

alter table fields enable row level security;
alter table ndvi_timeseries enable row level security;
alter table plant_counts enable row level security;
alter table chat_messages enable row level security;

drop policy if exists fields_owner on fields;
create policy fields_owner on fields
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists plant_counts_owner on plant_counts;
create policy plant_counts_owner on plant_counts
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists chat_messages_owner on chat_messages;
create policy chat_messages_owner on chat_messages
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ndvi_timeseries no tiene user_id: la propiedad se hereda de la parcela.
drop policy if exists ndvi_owner on ndvi_timeseries;
create policy ndvi_owner on ndvi_timeseries
  for all using (
    exists (select 1 from fields f where f.id = ndvi_timeseries.field_id and f.user_id = auth.uid())
  );
