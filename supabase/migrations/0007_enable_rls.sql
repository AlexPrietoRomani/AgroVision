-- =====================================================================================
-- AgroVisión — Políticas RLS (Fase 14): Seguridad en tablas públicas sin RLS.
-- Resuelve las alertas críticas de Supabase Linter (rls_disabled_in_public, sensitive_columns_exposed)
-- para las tablas de la aplicación.
--
-- NOTA: No es posible habilitar RLS en public.spatial_ref_sys debido a restricciones de
-- privilegios (es propiedad de 'supabase_admin').
--
-- Conexión directa por DATABASE_URL (rol 'postgres') evade RLS.
-- Estas políticas aseguran que el acceso mediante la API REST de Supabase (PostgREST)
-- con la clave 'anon' o 'authenticated' esté protegido.
-- =====================================================================================

-- 1. Habilitar RLS en las tablas del dominio
ALTER TABLE public.events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vegetation_indices ENABLE ROW LEVEL SECURITY;

-- 2. Políticas para vegetation_indices
-- Aislamiento por usuario a nivel de fila (propietario de la parcela).
-- Como vegetation_indices no tiene column user_id directa, validamos contra la parcela asociada en 'fields'.
DROP POLICY IF EXISTS vegetation_indices_owner ON public.vegetation_indices;
CREATE POLICY vegetation_indices_owner ON public.vegetation_indices
  FOR ALL USING (
    EXISTS (
      SELECT 1 FROM public.fields f
      WHERE f.id = vegetation_indices.field_id
        AND f.user_id = auth.uid()
    )
  ) WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.fields f
      WHERE f.id = vegetation_indices.field_id
        AND f.user_id = auth.uid()
    )
  );

-- 3. Políticas para events (Telemetría de UI)
-- Dado que la persistencia de eventos se realiza exclusivamente a través del backend
-- y no directamente por la API de cliente de Supabase (PostgREST), por seguridad
-- no definimos ninguna política de lectura/escritura pública (anon/authenticated).
-- Esto bloquea por completo el acceso API externo a esta tabla (evitando la exposición de session_id).
