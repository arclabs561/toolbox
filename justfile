set shell := ["bash", "-euo", "pipefail", "-c"]

pep_tools := "check-math chatgpt2md claude2md commit-survey gemini2md gh-dependabot pinglet perplexity-export perplexity2md reflow toks webshot"
shell_tools := "bcat blinks trunk"
tools := "bcat blinks chatgpt2md check-math claude2md commit-survey gemini2md gh-dependabot pinglet perplexity-export perplexity2md reflow toks trunk webshot"
shortcuts := "pingl"
base_image := "toolbox-pinglet-base:python3.12"

default:
    @just --list

# Run the same static checks used by CI.
check:
    uvx ruff@0.14.10 check .
    uvx ruff@0.14.10 format --check .
    shellcheck -e SC1091 bcat/bcat blinks/blinks trunk/trunk docker/push-ecr.sh tests/*.sh tests/docker/smoke.sh
    for tool in {{shell_tools}}; do bash -n "$tool/$tool"; done

# Run the toolbox integration suite.
test:
    bash tests/run.sh

# Build the toolbox-owned dependency image for the active Docker context.
docker-base:
    docker build -f docker/pinglet-base/Dockerfile -t "${TOOLBOX_BASE_IMAGE:-{{base_image}}}" .

# Publish to an existing, infra-managed ECR repository. This deliberately
# requires a separate temporary privileged session and exact role check. The
# publisher never creates or changes an ECR repository.
docker-base-push-ecr:
    ./docker/push-ecr.sh

# Exercise the read-only Linux adapter inside an isolated container namespace.
# Uses the active Docker context (Colima on this machine) and the toolbox-owned
# base by default. Build it first with `just docker-base` when it is absent.
test-docker:
    @printf 'docker context: '
    @docker context show
    if ! docker image inspect "${TOOLBOX_DOCKER_BASE:-{{base_image}}}" >/dev/null 2>&1; then \
        echo "missing local base image: ${TOOLBOX_DOCKER_BASE:-{{base_image}}}" >&2; \
        echo 'run just docker-base or set TOOLBOX_DOCKER_BASE to an existing image' >&2; \
        exit 2; \
    fi
    if [ -n "${TOOLBOX_DOCKER_PLATFORM:-}" ]; then \
        docker build --platform "${TOOLBOX_DOCKER_PLATFORM}" \
            --build-arg "BASE_IMAGE=${TOOLBOX_DOCKER_BASE:-{{base_image}}}" \
            -f tests/docker/Dockerfile -t toolbox-pinglet-smoke .; \
        docker run --rm --network none --platform "${TOOLBOX_DOCKER_PLATFORM}" toolbox-pinglet-smoke; \
    else \
        docker build \
            --build-arg "BASE_IMAGE=${TOOLBOX_DOCKER_BASE:-{{base_image}}}" \
            -f tests/docker/Dockerfile -t toolbox-pinglet-smoke .; \
        docker run --rm --network none toolbox-pinglet-smoke; \
    fi

# Run the smoke test for each explicitly supplied base/platform pair.
# Example: TOOLBOX_DOCKER_BASES='toolbox-pinglet-base:python3.12' TOOLBOX_DOCKER_PLATFORMS='linux/arm64' just test-docker-matrix
test-docker-matrix:
    bases="${TOOLBOX_DOCKER_BASES:-{{base_image}}}"; platforms="${TOOLBOX_DOCKER_PLATFORMS:-linux/arm64}"; \
    for base in $bases; do \
        for platform in $platforms; do \
            echo "docker smoke: base=$base platform=$platform"; \
            TOOLBOX_DOCKER_BASE="$base" TOOLBOX_DOCKER_PLATFORM="$platform" just test-docker; \
        done; \
    done

# Validate the source suite; toolbox tools are PEP 723 scripts and need no compile step.
build: check
    for tool in {{pep_tools}}; do uv run --script "$tool/$tool" -h >/dev/null; done

# Recreate the managed PATH links without touching the compatibility link for parloq.
link:
    mkdir -p bin
    for tool in {{tools}}; do \
        if [ -e "bin/$tool" ] && [ ! -L "bin/$tool" ]; then \
            echo "refusing to replace non-symlink bin/$tool" >&2; \
            exit 1; \
        fi; \
        ln -sfn "../$tool/$tool" "bin/$tool"; \
    done
    for shortcut in {{shortcuts}}; do \
        if [ -e "bin/$shortcut" ] && [ ! -L "bin/$shortcut" ]; then \
            echo "refusing to replace non-symlink bin/$shortcut" >&2; \
            exit 1; \
        fi; \
        ln -sfn "../pinglet/pinglet" "bin/$shortcut"; \
    done

# Validate, link, and print the PATH addition for the current checkout.
install: build link
    @printf 'toolbox links ready in %s/bin\n' "$PWD"
    @printf 'Add to your shell profile: export PATH="%s/bin:$PATH"\n' "$PWD"

# Print the PATH line without modifying a shell startup file.
path:
    @printf 'export PATH="%s/bin:$PATH"\n' "$PWD"
