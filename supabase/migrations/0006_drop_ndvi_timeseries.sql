-- AgroVisión — Migración 0006: Eliminar tabla ndvi_timeseries (legacy)
-- Datos previamente migrados a vegetation_indices (migración 0005).

-- Eliminar políticas RLS que referencian la tabla
DROP POLICY IF EXISTS ndvi_owner ON ndvi_timeseries;

-- Eliminar la tabla y su índice
DROP TABLE IF EXISTS ndvi_timeseries;
