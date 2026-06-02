#!/usr/bin/env bash
set -euo pipefail

ROOT=/opt/tako-performance
APP_NAME=bench-http
APP_ID="$APP_NAME/production"
VERSION=baseline-001
ROUTE=bench.test
FEATURE_APP_NAME=bench-features
FEATURE_APP_ID="$FEATURE_APP_NAME/production"
TAKO_DATA="$ROOT/tako-data"
TAKO_SOCKET="$ROOT/run/tako.sock"

sudo mkdir -p "$ROOT"/{bin,certs,configs,logs,run,results} \
  "$TAKO_DATA/apps/$APP_ID/releases/$VERSION" \
  "$TAKO_DATA/apps/$FEATURE_APP_ID/releases/$VERSION"
sudo chown -R "$USER":"$USER" "$ROOT"

if [[ ! -f "$ROOT/certs/bench.test.crt" || ! -f "$ROOT/certs/bench.test.key" ]]; then
  openssl req -x509 -newkey rsa:2048 -nodes -days 30 \
    -subj "/CN=bench.test" \
    -addext "subjectAltName=DNS:bench.test" \
    -keyout "$ROOT/certs/bench.test.key" \
    -out "$ROOT/certs/bench.test.crt"
fi

mkdir -p "$TAKO_DATA/certs/$ROUTE"
cp "$ROOT/certs/bench.test.crt" "$TAKO_DATA/certs/$ROUTE/fullchain.pem"
cp "$ROOT/certs/bench.test.key" "$TAKO_DATA/certs/$ROUTE/privkey.pem"
cat "$ROOT/certs/bench.test.crt" "$ROOT/certs/bench.test.key" > "$ROOT/certs/bench.test.pem"
chmod 0600 "$ROOT/certs/bench.test.pem"

go build -o "$ROOT/bin/benchapp" ./cmd/benchapp

if [[ ! -x "$ROOT/bin/caddy" ]]; then
  go install github.com/caddyserver/xcaddy/cmd/xcaddy@latest
  "$(go env GOPATH)/bin/xcaddy" build \
    --output "$ROOT/bin/caddy" \
    --with github.com/mholt/caddy-ratelimit
fi

cp "$ROOT/bin/benchapp" "$TAKO_DATA/apps/$APP_ID/releases/$VERSION/benchapp"
cat > "$TAKO_DATA/apps/$APP_ID/releases/$VERSION/app.json" <<JSON
{
  "runtime": "go",
  "main": "benchapp",
  "idle_timeout": 300,
  "env_vars": {
    "TAKO_BUILD": "$VERSION"
  }
}
JSON

chmod 0755 "$TAKO_DATA/apps/$APP_ID/releases/$VERSION/benchapp"

rsync -a --delete apps/channels-workflows/ "$TAKO_DATA/apps/$FEATURE_APP_ID/releases/$VERSION/"
cat > "$TAKO_DATA/apps/$FEATURE_APP_ID/releases/$VERSION/app.json" <<JSON
{
  "runtime": "bun",
  "main": "src/index.ts",
  "idle_timeout": 300,
  "package_manager": "bun",
  "env_vars": {
    "TAKO_BUILD": "$VERSION"
  }
}
JSON
chmod -R g+rwX "$TAKO_DATA/apps/$FEATURE_APP_ID/releases/$VERSION"

sudo chown -R tako:tako "$TAKO_DATA"
sudo chmod 0710 "$TAKO_DATA"

cp configs/nginx/*.conf "$ROOT/configs/"
cp configs/caddy/*.Caddyfile "$ROOT/configs/"
cp configs/haproxy/single.cfg "$ROOT/configs/haproxy-single.cfg"
cp configs/envoy/single.yaml "$ROOT/configs/envoy-single.yaml"
cp scripts/remote/takoctl.py "$ROOT/bin/takoctl.py"
chmod +x "$ROOT/bin/takoctl.py"

echo "Prepared $ROOT"
