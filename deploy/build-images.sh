#!/bin/sh
# Builds the images a bundle runs: deploy/build-images.sh TAG [images.tar]
set -eu
tag="${1:?usage: deploy/build-images.sh TAG [images.tar]}"
output="${2:-}"
cd "$(dirname "$0")/.."
docker build -f apps/runtime/Dockerfile -t "daftar-runtime:$tag" .
docker build --target client -f apps/worker/Dockerfile -t "daftar-worker-client:$tag" .
if [ -n "$output" ]; then
  docker save "daftar-runtime:$tag" "daftar-worker-client:$tag" -o "$output"
fi
