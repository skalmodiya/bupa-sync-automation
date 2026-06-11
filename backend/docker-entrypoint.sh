#!/bin/sh
# Ensure settings.json exists in the data volume on first run.
# The volume mount overrides the Docker image's /app/data directory,
# so we seed the default docker-settings.json if no settings exist yet.

if [ ! -f /app/data/settings.json ]; then
  echo "First run detected: seeding default settings.json into data volume..."
  cp /app/docker-settings.json /app/data/settings.json
fi

exec "$@"
