#!/usr/bin/env bash
# ============================================================================
# Archivo: deploy_hf.sh
# Fecha de modificación: 28/10/2026
# Autor: Alex Prieto Romani <alexprieto1997@gmail.com>
#
# Descripción:
# Despliegue POSIX (Linux/macOS) de AgroVisión a Hugging Face Spaces (SDK Docker).
# Equivalente a scripts/deploy_hf.ps1: compila la UI con scripts/build.sh, inyecta
# temporalmente el frontmatter YAML en README.md, crea un commit de despliegue y
# hace push al repositorio del Space. El README original y el commit temporal se
# restauran siempre mediante un trap EXIT, incluso si el build o el push fallan.
#
# Requisitos (.env, no versionado):
#   HF_TOKEN=hf_xxx                    token write de Hugging Face
#   HF_SPACE_ID=<usuario>/<space>      por defecto alexp97/agrovision
#
# Uso:
#   ./scripts/deploy_hf.sh [--dry-run] [--force] [--space <usuario>/<space>]
#
# Opciones:
#   --dry-run   Valida argumentos/entorno y muestra el plan sin compilar ni push.
#   --force     Fuerza el push (primer deploy: sobrescribe el commit inicial).
#   --space     Space destino; prevalece sobre HF_SPACE_ID.
#   -h, --help  Muestra esta ayuda.
# ============================================================================

set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

DEFAULT_SPACE_ID="alexp97/agrovision"
LEGACY_SPACE_ID="alexprieto/agrovision"

usage() {
    cat <<'EOF'
Uso: ./scripts/deploy_hf.sh [--dry-run] [--force] [--space <usuario>/<space>]

  --dry-run   Valida el entorno y muestra el plan sin compilar ni hacer push.
  --force     Fuerza el push (necesario en el primer deploy).
  --space     Space destino (<usuario>/<space>); prevalece sobre HF_SPACE_ID.
  -h, --help  Muestra esta ayuda.
EOF
}

dry_run=0
force=0
space_arg=""

while (($# > 0)); do
    case "$1" in
        --dry-run)
            dry_run=1
            ;;
        --force)
            force=1
            ;;
        --space)
            if (($# < 2)) || [[ -z "${2:-}" ]]; then
                echo "ERROR: --space requiere <usuario>/<space>." >&2
                exit 2
            fi
            space_arg="$2"
            shift
            ;;
        --space=*)
            space_arg="${1#*=}"
            if [[ -z "$space_arg" ]]; then
                echo "ERROR: --space requiere <usuario>/<space>." >&2
                exit 2
            fi
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            echo "ERROR: opción desconocida: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
    shift
done

# Carga HF_TOKEN / HF_SPACE_ID desde .env sin pisar variables ya exportadas.
load_env_file() {
    local file="$1" line key value
    [[ -f "$file" ]] || return 0
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line%$'\r'}"
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line#export }"
        case "$line" in
            HF_TOKEN=* | HF_SPACE_ID=*) ;;
            *) continue ;;
        esac
        key="${line%%=*}"
        value="${line#*=}"
        value="${value#"${value%%[![:space:]]*}"}"
        value="${value%"${value##*[![:space:]]}"}"
        case "$value" in
            \"*\") value="${value:1:${#value}-2}" ;;
            \'*\') value="${value:1:${#value}-2}" ;;
        esac
        if [[ -z "${!key:-}" && -n "$value" ]]; then
            export "$key=$value"
        fi
    done <"$file"
}
load_env_file ".env"

space_id="${space_arg:-${HF_SPACE_ID:-}}"
if [[ -z "$space_id" || "$space_id" == "$LEGACY_SPACE_ID" ]]; then
    space_id="$DEFAULT_SPACE_ID"
fi

if [[ ! "$space_id" =~ ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ ]]; then
    echo "ERROR: Space inválido ('$space_id'). Usa el formato <usuario>/<space>." >&2
    exit 1
fi

owner="${space_id%%/*}"
space_url="https://huggingface.co/spaces/$space_id"
if [[ -n "${HF_TOKEN:-}" ]]; then
    token_status="configurado (oculto)"
else
    token_status="no configurado"
fi

echo "=== Deploy AgroVisión -> Hugging Face Spaces ==="
echo "Space: $space_url (rama main)"
echo "HF_TOKEN: $token_status"

if [[ -z "${HF_TOKEN:-}" ]]; then
    if ((dry_run)); then
        echo "AVISO: HF_TOKEN no está definido; el dry-run no requiere push." >&2
    else
        echo "ERROR: falta HF_TOKEN. Defínelo en el entorno o en .env (token write)." >&2
        exit 1
    fi
fi

# El backup y el trap se preparan antes del build para que cualquier fallo deje
# README.md intacto y elimine el commit temporal si llegó a crearse.
readme_backup="$(mktemp "${TMPDIR:-/tmp}/agrovision-readme.XXXXXX")"
cp README.md "$readme_backup"
readme_modified=0
temporary_commit=0
cleanup() {
    local status=$?
    trap - EXIT
    if ((temporary_commit)); then
        git reset --mixed HEAD~1 >/dev/null 2>&1 || true
    fi
    if ((readme_modified)); then
        git reset -q -- README.md >/dev/null 2>&1 || true
        cp "$readme_backup" README.md
    fi
    rm -f "$readme_backup"
    exit "$status"
}
trap cleanup EXIT

if ((dry_run)); then
    echo "[dry-run] Se ejecutaría: ./scripts/build.sh"
    echo "[dry-run] Se inyectaría .huggingface_frontmatter en README.md (commit temporal)."
    push_preview="git push"
    if ((force)); then
        push_preview+=" --force"
    fi
    push_preview+=" https://<owner>:***@huggingface.co/spaces/$space_id HEAD:main"
    echo "[dry-run] Se ejecutaría: $push_preview"
    echo "[dry-run] Sin cambios locales ni push real."
    exit 0
fi

echo
echo "=== [1/3] Compilando UI (scripts/build.sh) ==="
./scripts/build.sh

echo
echo "=== [2/3] Preparando README.md con frontmatter de HF Spaces ==="
if [[ ! -f .huggingface_frontmatter ]]; then
    echo "ERROR: falta .huggingface_frontmatter en la raíz del repo." >&2
    exit 1
fi
{
    cat .huggingface_frontmatter
    printf '\n'
    cat README.md
} >README.md.deploy.tmp
mv README.md.deploy.tmp README.md
readme_modified=1

git add README.md
git commit -m "build: deploy to Hugging Face Spaces with metadata" >/dev/null
temporary_commit=1

remote="https://${owner}:${HF_TOKEN}@huggingface.co/spaces/${space_id}"
push_args=(push)
if ((force)); then
    push_args+=(--force)
fi
push_args+=("$remote" "HEAD:main")

echo
echo "=== [3/3] Push al Space (HF construirá el Dockerfile) ==="
echo "Destino: $space_url (rama main)"
# Se captura la salida para redactar el token si git la incluyera en un error.
if ! push_output="$(git "${push_args[@]}" 2>&1)"; then
    printf '%s\n' "${push_output//$HF_TOKEN/***}" >&2
    echo "ERROR: el push falló. Si es el primer deploy, reintenta con --force." >&2
    exit 1
fi
printf '%s\n' "${push_output//$HF_TOKEN/***}"

echo
echo "=== Push completado. Sigue el build en $space_url ==="
echo "Cuando termine, la UI carga en / y la API en /api."
