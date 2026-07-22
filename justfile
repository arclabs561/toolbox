set shell := ["bash", "-euo", "pipefail", "-c"]

pep_tools := "check-math chatgpt2md claude2md commit-survey gemini2md gh-dependabot ips perplexity-export perplexity2md reflow toks webshot"
shell_tools := "bcat blinks trunk"
tools := "bcat blinks chatgpt2md check-math claude2md commit-survey gemini2md gh-dependabot ips perplexity-export perplexity2md reflow toks trunk webshot"

default:
    @just --list

# Run the same static checks used by CI.
check:
    uvx ruff@0.14.10 check .
    uvx ruff@0.14.10 format --check .
    shellcheck -e SC1091 bcat/bcat blinks/blinks trunk/trunk tests/*.sh tests/docker/smoke.sh
    for tool in {{shell_tools}}; do bash -n "$tool/$tool"; done

# Run the toolbox integration suite.
test:
    bash tests/run.sh

# Exercise the read-only Linux adapter inside an isolated container namespace.
# Uses the active Docker context (Colima on this machine). The base image must
# already be cached in that context; this target never performs an implicit pull.
test-docker:
    @printf 'docker context: '
    @docker context show
    if ! docker image inspect "${TOOLBOX_DOCKER_BASE:-python:3.12-slim}" >/dev/null 2>&1; then \
        echo "missing cached base image: ${TOOLBOX_DOCKER_BASE:-python:3.12-slim}" >&2; \
        echo 'set TOOLBOX_DOCKER_BASE to an image already present in this Docker context' >&2; \
        exit 2; \
    fi
    if [ -n "${TOOLBOX_DOCKER_PLATFORM:-}" ]; then \
        docker build --platform "${TOOLBOX_DOCKER_PLATFORM}" \
            --build-arg "BASE_IMAGE=${TOOLBOX_DOCKER_BASE:-python:3.12-slim}" \
            --build-arg "INSTALL_DEPS=${TOOLBOX_DOCKER_INSTALL_DEPS:-1}" \
            -f tests/docker/Dockerfile -t toolbox-ips-smoke .; \
        docker run --rm --network none --platform "${TOOLBOX_DOCKER_PLATFORM}" toolbox-ips-smoke; \
    else \
        docker build \
            --build-arg "BASE_IMAGE=${TOOLBOX_DOCKER_BASE:-python:3.12-slim}" \
            --build-arg "INSTALL_DEPS=${TOOLBOX_DOCKER_INSTALL_DEPS:-1}" \
            -f tests/docker/Dockerfile -t toolbox-ips-smoke .; \
        docker run --rm --network none toolbox-ips-smoke; \
    fi

# Run the smoke test for each explicitly supplied cached base/platform pair.
# Example: TOOLBOX_DOCKER_BASES='image-a image-b' TOOLBOX_DOCKER_PLATFORMS='linux/arm64 linux/amd64' just test-docker-matrix
test-docker-matrix:
    bases="${TOOLBOX_DOCKER_BASES:-python:3.12-slim}"; platforms="${TOOLBOX_DOCKER_PLATFORMS:-linux/arm64}"; \
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

# Validate, link, and print the PATH addition for the current checkout.
install: build link
    @printf 'toolbox links ready in %s/bin\n' "$PWD"
    @printf 'Add to your shell profile: export PATH="%s/bin:$PATH"\n' "$PWD"

# Print the PATH line without modifying a shell startup file.
path:
    @printf 'export PATH="%s/bin:$PATH"\n' "$PWD"
