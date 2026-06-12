-- AgroVisión — Migración 0005: Migrar datos legacy de ndvi_timeseries a vegetation_indices
-- Copia los puntos NDVI de ndvi_timeseries a vegetation_indices para cada parcela
-- que aún no tenga NDVI en vegetation_indices. Idempotente (ON CONFLICT DO NOTHING).
-- Posterior a esta migración, ndvi_timeseries queda como tabla legacy sin escrituras.

insert into vegetation_indices (field_id, index_type, date, mean_value, min_value, max_value, cloud_cover, source)
select
  n.field_id,
  'ndvi' as index_type,
  n.date,
  n.mean_ndvi as mean_value,
  n.min_ndvi as min_value,
  n.max_ndvi as max_value,
  n.cloud_cover,
  coalesce(n.source, 'sentinel2')
from ndvi_timeseries n
left join vegetation_indices v
  on v.field_id = n.field_id
  and v.index_type = 'ndvi'
  and v.date = n.date
where v.id is null
on conflict (field_id, index_type, date) do nothing;
