set shell := ["bash", "-euo", "pipefail", "-c"]

pep_tools := "check-math chatgpt2md claude2md commit-survey gemini2md gh-dependabot perplexity-export perplexity2md reflow toks webshot"
shell_tools := "bcat blinks trunk"
tools := "bcat blinks chatgpt2md check-math claude2md commit-survey gemini2md gh-dependabot perplexity-export perplexity2md reflow toks trunk webshot"

default:
    @just --list

# Run the same static checks used by CI.
check:
    uvx ruff@0.14.10 check .
    uvx ruff@0.14.10 format --check .
    shellcheck -e SC1091 bcat/bcat blinks/blinks trunk/trunk tests/*.sh
    for tool in {{shell_tools}}; do bash -n "$tool/$tool"; done

# Run the toolbox integration suite.
test:
    bash tests/run.sh

# Validate the source suite; toolbox tools are PEP 723 scripts and need no compile step.
build: check
    for tool in {{pep_tools}}; do uv run --script "$tool/$tool" -h >/dev/null; done

# Recreate the managed PATH links without touching standalone-project links.
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
