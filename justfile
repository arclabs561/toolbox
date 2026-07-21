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
# already be cached, or be available through that context's configured registry.
test-docker:
    @printf 'docker context: '
    @docker context show
    if ! docker image inspect "${TOOLBOX_DOCKER_BASE:-python:3.12-slim}" >/dev/null 2>&1; then \
        echo "missing local base image: ${TOOLBOX_DOCKER_BASE:-python:3.12-slim}" >&2; \
        echo 'set TOOLBOX_DOCKER_BASE to a cached image or make the image available through Colima' >&2; \
        exit 2; \
    fi
    docker build --build-arg "BASE_IMAGE=${TOOLBOX_DOCKER_BASE:-python:3.12-slim}" -f tests/docker/Dockerfile -t toolbox-ips-smoke .
    docker run --rm --network none toolbox-ips-smoke

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
