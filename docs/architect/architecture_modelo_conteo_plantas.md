# Arquitectura — Modelo de Conteo de Plantas (Repo Separado)

> **Audiencia:** Ingenieros de ML/visión, líderes técnicos.
> **Alcance:** Estructura del **repositorio de modelado** (pipeline ML), no de una app productiva. Su salida es **UN artefacto** (`agrovision-plantcount-*.onnx`) publicado en **Hugging Face Hub** y consumido por AgroVisión. Para especificaciones, ver [`description_proyecto_modelo_conteo_plantas.md`](../reference/description_proyecto_modelo_conteo_plantas.md).
> **Modelo (multi-candidato):** se evalúan **YOLO26** (AGPL-3.0, NMS-free), **RF-DETR** (Apache 2.0, NMS-free) y **DINOv3**; se publica **el mejor** (menor MAE). **AGPL aceptada** (app open-source) → YOLO26 usable. **Multi-cultivo** (arándano primero). DeepForest (MIT) para satélite. **Sin BD transaccional** (persistencia = datasets/artefactos versionados).

---

## 1. Visión General del Sistema (C4 – Nivel Contexto)

```mermaid
flowchart TB
    subgraph Actores["Actores Principales"]
        U1["👤 Ingeniero ML / Visión"]
    end

    subgraph Sistema["Sistema Central"]
        APP["Repo de Modelo de Conteo<br/>─────────────────<br/>Notebooks + pipeline .py<br/>Entrena candidatos (YOLO26/RF-DETR), publica el mejor (1 modelo)"]
    end

    subgraph Externos["Dependencias Externas"]
        DATA["Fuentes de Datos<br/>─────────────<br/>Roboflow (COCO) · Kaggle · DeepForest/NEON · MAXAR/Planet"]
        GPU["Cómputo Gratuito<br/>─────────────<br/>Google Colab / Kaggle (GPU T4)"]
        HF["Hugging Face Hub<br/>─────────────<br/>repo de modelos (artefacto versionado)"]
        AV["AgroVisión (consumidor)<br/>─────────────<br/>hf_hub_download en build (solo inferencia)"]
    end

    U1 -->|"experimenta, entrena, exporta"| APP
    APP <-->|"descarga datasets (COCO)"| DATA
    APP <-->|"entrena en GPU"| GPU
    APP -->|"publica 1 artefacto"| HF
    HF -->|"build descarga el modelo"| AV
```

**Decisiones arquitectónicas clave (Nivel Macro):**
- **Notebooks-first:** validar viabilidad en notebooks (Colab/Kaggle) antes de promover a `.py`.
- **1 solo artefacto publicado:** se entrenan varios candidatos, se selecciona el mejor y **solo ese** se sube a HF Hub.
- **RF-DETR (Apache 2.0) NMS-free** como primario (permisivo, CPU) + **DINOv3/DeepForest** (satélite).
- **Nombre desacoplado:** `agrovision-plantcount` (no depende de la arquitectura interna).

---

## 2. Componentes Internos (C4 – Nivel Contenedor)

```mermaid
flowchart LR
    subgraph Exp["Capa de Experimentación"]
        NB["notebooks/<br/>──────────<br/>01 explore · 02 SAM→COCO · 03 RF-DETR · 04 satélite"]
    end

    subgraph Pipe["Capa de Pipeline (.py reproducible)"]
        direction TB
        ING["ingest.py (Roboflow COCO/Kaggle)"]
        ANN["annotate_sam.py (SAM → COCO)"]
        PRE["preprocess.py (tiling/splits/augment COCO)"]
        TRN["train.py (RF-DETR detect/seg)"]
        EVL["evaluate.py (mAP/F1/MAE + selección)"]
        EXP2["export.py (.pth → ONNX + model card)"]
        PUB["publish.py (→ Hugging Face Hub)"]
        SAT["satellite/ (DeepForest + DINOv3)"]
    end

    subgraph Store["Almacenes / Artefactos"]
        RAW[("data/raw")]
        PROC[("data/processed (COCO)")]
        MOD[("models/ (.onnx) + metrics.json")]
    end

    NB -.promueve.-> Pipe
    ING --> RAW --> ANN --> PROC
    PRE --> PROC
    PROC --> TRN --> EVL --> EXP2 --> MOD --> PUB
    SAT --> EVL
```

**Flujo de una interacción típica:**
1. El ingeniero **explora** datos y valida un conteo base en `03_train_rfdetr.ipynb`.
2. Promueve la lógica a `src/*.py`: `ingest` → `annotate_sam` (→ COCO) → `preprocess` → `train` → `evaluate` (**selecciona el mejor**) → `export` → `publish`.
3. `export.py` genera `agrovision-plantcount-vX.Y.Z.onnx`; `publish.py` lo sube a **HF Hub**.
4. El build de AgroVisión lo descarga con `hf_hub_download` como modelo predeterminado.

---

## 3. Lógica Core / Proceso Crítico (Pipeline ML)

```mermaid
flowchart TB
    IN(["Datasets públicos (dron/satélite)"])
    P1["Anotación SAM → formato COCO"]
    P2["Preprocesamiento: tiling por GSD + augmentations + splits COCO"]
    P3["Entrenamiento RF-DETR (transfer, NMS-free)"]
    P4["Evaluación + SELECCIÓN del mejor (MAE/tamaño/latencia)"]
    P5["Exportación ONNX + model card"]
    P6["Publicación en Hugging Face Hub (1 artefacto)"]
    OUT(["agrovision-plantcount-*.onnx (contrato §6)"])
    IN --> P1 --> P2 --> P3 --> P4 --> P5 --> P6 --> OUT
    P4 -.->|"si MAE > umbral"| P2
```

---

## 4. Flujo de Secuencia (Experimentación → Producción → Handoff)

```mermaid
sequenceDiagram
    actor E as Ingeniero ML
    participant NB as Notebook (Colab/Kaggle)
    participant PY as Pipeline .py
    participant GPU as GPU T4 (gratis)
    participant HF as Hugging Face Hub
    participant AV as AgroVisión (build)

    E->>NB: PoC de conteo con dataset COCO público
    NB->>GPU: entrena RFDETRNano (rápido)
    GPU-->>NB: métricas base (mAP/MAE)
    Note over NB,PY: viabilidad validada → promover lógica
    E->>PY: ejecuta pipeline reproducible (seeds fijas)
    PY->>GPU: train + eval completos
    PY->>PY: evaluate.py SELECCIONA el mejor candidato
    PY->>PY: export.py → agrovision-plantcount-v2.0.0.onnx
    PY->>HF: publish.py sube 1 artefacto + model card
    AV->>HF: hf_hub_download en docker build
    AV-->>E: integrado como modelo predeterminado (MODEL_PATH)
```

---

## 5. Modelo de Dominio / Artefactos (no hay BD transaccional)

```mermaid
flowchart TB
    subgraph Datos["Datos"]
        DS["Dataset<br/>─────────<br/>fuente · licencia · clases (COCO)"]
        ANN["Anotaciones COCO<br/>─────────<br/>_annotations.coco.json"]
    end
    subgraph Artefactos["Artefactos de Modelo"]
        RUN["Run de Entrenamiento<br/>─────────<br/>hiperparámetros · seed · métricas"]
        MOD["Modelo publicado (1)<br/>─────────<br/>agrovision-plantcount.onnx · model_version · architecture"]
        CARD["Model Card<br/>─────────<br/>datos · licencia (Apache 2.0) · métricas"]
    end
    DS -->|"se anota"| ANN
    ANN -->|"entrena"| RUN
    RUN -->|"se selecciona el mejor → produce"| MOD
    MOD -->|"documenta"| CARD
```

**Políticas de Datos:**
- **Versionado de datos:** `data/` no se commitea; se versiona el *manifiesto* (fuente, hash, licencia) y opcionalmente con **DVC**.
- **1 artefacto:** solo el modelo seleccionado se publica (HF Hub); su `model_version` (SemVer) enlaza run/dataset/métricas.
- **Reproducibilidad:** semillas fijas y config declarativa.

---

## 6. Arquitectura de Despliegue (Publicación de Artefactos)

```mermaid
flowchart LR
    subgraph Local["Desarrollo"]
        DEV["IDE + notebooks (CPU local)"]
    end
    subgraph Cloud["Cómputo Gratuito"]
        COLAB["Colab / Kaggle (GPU T4)"]
    end
    subgraph CI["CI / Publicación"]
        TEST["pytest (contrato + paridad)"]
        PUB["publish.py → Hugging Face Hub vX.Y.Z"]
        TEST --> PUB
    end
    subgraph Consumo["Consumo"]
        AVB["Build de AgroVisión<br/>hf_hub_download → imagen backend"]
    end

    DEV -->|"PoC"| COLAB
    COLAB -->|"checkpoint_best.pth"| CI
    Local -->|"git push"| CI
    PUB -->|"descarga artefacto"| AVB
```

---

## 7. Decisiones Arquitectónicas Relevantes (ADRs Resumidos)

| Decisión Tomada | Alternativa Descartada | Razón Principal |
| :--- | :--- | :--- |
| **Multi-candidato: YOLO26 + RF-DETR + DINOv3, se publica el mejor** | Fijar un solo modelo de entrada | Gana el de **menor MAE** (tamaño/latencia OK). **AGPL-3.0 aceptada** (app open-source) habilita YOLO26; RF-DETR (Apache) queda como alternativa permisiva. App **agnóstica por contrato**. |
| **Anotar a COCO + YOLO** | Un solo formato | Se anota una vez y se exporta a **COCO** (para RF-DETR) y **YOLO** (para YOLO26), permitiendo entrenar ambos candidatos. |
| **Publicar en Hugging Face Hub** | GitHub Releases / object storage | Hosting de modelos versionado y estándar; `hf_hub_download` integra en el build de AgroVisión. |
| **1 solo artefacto, el mejor** | Publicar todos los tracks | Simplicidad para el consumidor; los tracks son experimentos para elegir al ganador. |
| **Nombre desacoplado** (`agrovision-plantcount`) | Nombre por arquitectura (`rfdetr_nano`) | Permite cambiar de modelo sin tocar la app; el contrato es lo estable. |
| **DINOv3 + DeepForest** (satélite) | Entrenar conteo de árboles desde cero | DeepForest (MIT) preentrenado + DINOv3 satelital sin fine-tuning aceleran el track. |
| **Notebooks-first** | Ir directo a `.py` | Validar viabilidad barato antes de endurecer; cada notebook tiene su par `.py` testeado. |
| **Sin BD transaccional** | Postgres/registro pesado | El dominio son datasets/artefactos versionados (manifiestos + DVC + HF Hub). |
