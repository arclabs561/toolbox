#!/usr/bin/env bash
# Build and publish the toolbox base image to an existing, infra-managed ECR repository.

set -euo pipefail

die() {
    printf 'push-ecr: %s\n' "$*" >&2
    exit 1
}

need_command() {
    command -v "$1" >/dev/null 2>&1 || die "$1 is required"
}

for command_name in aws docker git date mktemp chmod rm; do
    need_command "$command_name"
done

image_root="${TOOLBOX_ECR_IMAGE:-}"
aws_profile="${TOOLBOX_AWS_PROFILE:-}"
expected_role="${TOOLBOX_ECR_ROLE:-}"
region="${TOOLBOX_ECR_REGION:-us-east-1}"
platforms="${TOOLBOX_DOCKER_PLATFORMS:-linux/amd64,linux/arm64}"

[ -n "$image_root" ] || die 'set TOOLBOX_ECR_IMAGE to an existing ECR image root'
[ -n "$aws_profile" ] || die 'set TOOLBOX_AWS_PROFILE to the temporary privileged profile'
[ -n "$expected_role" ] || die 'set TOOLBOX_ECR_ROLE to the exact expected IAM role name'

case "$image_root" in
    *:*) die 'TOOLBOX_ECR_IMAGE must not include a tag' ;;
    */*) ;;
    *) die 'TOOLBOX_ECR_IMAGE must include an ECR registry and repository' ;;
esac

registry="${image_root%%/*}"
case "$registry" in
    [0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].dkr.ecr."$region".amazonaws.com) ;;
    *) die "TOOLBOX_ECR_IMAGE must use a private ECR registry in region $region" ;;
esac

registry_account="${registry%%.*}"
identity="$(AWS_PROFILE="$aws_profile" aws sts get-caller-identity \
    --query '[Account,Arn]' --output text --no-cli-pager)"
case "$identity" in
    "$registry_account"$'\t'"arn:aws:sts::$registry_account:assumed-role/$expected_role/"*) ;;
    *) die "profile $aws_profile is not role $expected_role in account $registry_account" ;
esac

git_sha="$(git rev-parse --short=12 HEAD)"
date_tag="$(date -u +%Y%m%d)"
dirty_suffix=""
if ! git diff --quiet >/dev/null 2>&1 || ! git diff --cached --quiet >/dev/null 2>&1; then
    dirty_suffix="-dirty$(date -u +%H%M%S)"
fi
tag="${TOOLBOX_ECR_TAG:-${date_tag}-${git_sha}${dirty_suffix}}"
if [[ ! "$tag" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; then
    die "invalid ECR tag: $tag"
fi

umask 077
docker_config="$(mktemp -d "${TMPDIR:-/tmp}/toolbox-ecr.XXXXXX")"
chmod 700 "$docker_config"
printf '{"auths":{}}\n' >"$docker_config/config.json"
cleanup_docker_config() {
    rm -rf -- "$docker_config"
}
trap cleanup_docker_config EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
export DOCKER_CONFIG="$docker_config"

printf 'publishing %s:%s and %s:latest\n' "$image_root" "$tag" "$image_root"
AWS_PROFILE="$aws_profile" aws ecr get-login-password --region "$region" |
    docker login --username AWS --password-stdin "$registry" >/dev/null
docker buildx build \
    --platform "$platforms" \
    --tag "$image_root:$tag" \
    --tag "$image_root:latest" \
    --progress=plain \
    --push \
    -f docker/pinglet-base/Dockerfile \
    .

printf 'published %s:%s and %s:latest\n' "$image_root" "$tag" "$image_root"
