# sample_data

Ortomosaicos de ejemplo para probar el conteo localmente (modo **mock**).

- Las imágenes (`*.png`, `*.jpg`, `*.tif`) **no se versionan** (ver `.gitignore`); se regeneran.
- Genera un ortomosaico de **arándano simulado** (hileras de arbustos, huecos de siembra y malezas):

  ```bash
  uv run python scripts/make_sample_orthomosaic.py
  # -> sample_data/blueberry_demo.png  (imprime el conteo real de arbustos/malezas)
  ```

- Con el backend en modo mock (`COUNTING_ENABLED=true`, `MODEL_BACKEND=mock`), sube esta imagen en
  la UI: el mock detecta los arbustos por color y el conteo coincide con el real (datos de prueba).
- El conteo con el **modelo real** se activa con `MODEL_BACKEND=onnx` cuando el repo del modelo
  publique el artefacto en Hugging Face Hub.
