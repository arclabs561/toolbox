#!/usr/bin/env bash
# Verify the registry publishers preserve the local credential and access boundaries.
. "$(dirname "$0")/lib.sh"

ecr=$(<"$ROOT/docker/push-ecr.sh")
assert_contains "ECR requires an explicit image root" "$ecr" 'TOOLBOX_ECR_IMAGE'
assert_contains "ECR requires an explicit privileged profile" "$ecr" 'TOOLBOX_AWS_PROFILE'
assert_contains "ECR requires an exact role" "$ecr" 'TOOLBOX_ECR_ROLE'
assert_contains "ECR checks the caller role" "$ecr" "assumed-role/\$expected_role/"
assert_contains "ECR uses a temporary Docker config" "$ecr" "mktemp -d \"\${TMPDIR:-/tmp}/toolbox-ecr.XXXXXX\""
assert_contains "ECR makes the temporary config private" "$ecr" "chmod 700 \"\$docker_config\""
assert_contains "ECR cleans up the temporary config" "$ecr" "rm -rf -- \"\$docker_config\""
assert_not_contains "ECR does not create repositories" "$ecr" 'aws ecr create-repository'
assert_not_contains "ECR never uses the persistent Docker config" "$ecr" "\$HOME/.docker"

finish
