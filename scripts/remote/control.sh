#!/usr/bin/env bash
set -euo pipefail

ROOT=/opt/tako-performance
TAKO_DATA="$ROOT/tako-data"
TAKO_SOCKET="$ROOT/run/tako.sock"
TAKO_SERVER_BIN="${TAKO_SERVER_BIN:-/usr/local/bin/tako-server}"
CADDY_BIN="${CADDY_BIN:-$ROOT/bin/caddy}"
PINGORA_FIXED_PROXY_BIN="${PINGORA_FIXED_PROXY_BIN:-$ROOT/bin/pingora-fixed-proxy-rps}"
HAPROXY_BIN="${HAPROXY_BIN:-haproxy}"
if [[ -z "${ENVOY_BIN:-}" ]]; then
  if [[ -x "$ROOT/bin/envoy-v1.38" ]]; then
    ENVOY_BIN="$ROOT/bin/envoy-v1.38"
  else
    ENVOY_BIN=envoy
  fi
fi
TAKO_APP=bench-http/production
TAKO_FEATURE_APP=bench-features/production
TAKO_VERSION=baseline-001
TAKO_RELEASE="$TAKO_DATA/apps/$TAKO_APP/releases/$TAKO_VERSION"
TAKO_FEATURE_RELEASE="$TAKO_DATA/apps/$TAKO_FEATURE_APP/releases/$TAKO_VERSION"
ROUTE=bench.test
BENCH_IP="${BENCH_IP:-127.0.0.1}"

ulimit -n 65535 2>/dev/null || ulimit -n 4096 2>/dev/null || true

sudo_high_nofile() {
  sudo -n sh -c 'ulimit -n 65535; exec "$@"' sh "$@"
}

stop_pidfile() {
  local file="$1"
  if [[ -f "$file" ]]; then
    local pid
    pid="$(cat "$file" 2>/dev/null || true)"
    if [[ -n "$pid" ]]; then
      kill "$pid" 2>/dev/null || sudo -n kill "$pid" 2>/dev/null || true
      for _ in $(seq 1 50); do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.1
      done
      kill -9 "$pid" 2>/dev/null || sudo -n kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$file"
  fi
}

wait_port_free() {
  local port="$1"
  for _ in $(seq 1 100); do
    if ! ss -ltn "sport = :$port" 2>/dev/null | tail -n +2 | grep -q .; then
      return 0
    fi
    sleep 0.1
  done

  sudo -n fuser -k "$port/tcp" >/dev/null 2>&1 || true
  for _ in $(seq 1 50); do
    if ! ss -ltn "sport = :$port" 2>/dev/null | tail -n +2 | grep -q .; then
      return 0
    fi
    sleep 0.1
  done

  echo "port $port is still in use" >&2
  return 1
}

stop_all() {
  stop_pidfile "$ROOT/run/tako-server.pid"
  stop_pidfile "$ROOT/run/caddy.pid"
  stop_pidfile "$ROOT/run/pingora-fixed-proxy.pid"
  stop_pidfile "$ROOT/run/haproxy.pid"
  stop_pidfile "$ROOT/run/envoy.pid"
  if [[ -f "$ROOT/run/nginx.pid" ]]; then
    sudo -n nginx -s quit -c "$ROOT/configs/nginx-active.conf" -p "$ROOT/nginx" 2>/dev/null || true
    nginx -s quit -c "$ROOT/configs/nginx-active.conf" -p "$ROOT/nginx" 2>/dev/null || true
    sleep 0.5
    stop_pidfile "$ROOT/run/nginx.pid"
  fi
  for file in "$ROOT"/run/app-*.pid; do
    [[ -e "$file" ]] || continue
    stop_pidfile "$file"
  done
  sudo -n pkill -f "caddy run --config $ROOT/configs/" 2>/dev/null || true
  sudo -n pkill -f "$PINGORA_FIXED_PROXY_BIN" 2>/dev/null || true
  sudo -n pkill -f "$HAPROXY_BIN -f $ROOT/configs/haproxy-active.cfg" 2>/dev/null || true
  sudo -n pkill -f "$ENVOY_BIN -c $ROOT/configs/envoy-single.yaml" 2>/dev/null || true
  sudo -n pkill -f "$TAKO_SERVER_BIN --data-dir $TAKO_DATA" 2>/dev/null || true
  pkill -f "$ROOT/bin/benchapp" 2>/dev/null || true
  pkill -f "$TAKO_DATA/apps/.*/benchapp" 2>/dev/null || true
  rm -f "$ROOT/run/tako.sock" "$ROOT/run/tako-"*.sock
  wait_port_free 18443
  wait_port_free 18080
}

start_apps() {
  local count="$1"
  for i in $(seq 1 "$count"); do
    local port=$((9100 + i))
    HOST=127.0.0.1 PORT="$port" TAKO_APP_NAME=bench-http TAKO_BUILD=manual \
      "$ROOT/bin/benchapp" > "$ROOT/logs/app-$i.log" 2>&1 &
    echo $! > "$ROOT/run/app-$i.pid"
  done
}

wait_https() {
  local path="${1:-plaintext}"
  local url="https://bench.test:18443/$path"
  for _ in $(seq 1 100); do
    if curl -fksS --resolve "bench.test:18443:$BENCH_IP" "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.1
  done
  echo "service did not become ready" >&2
  return 1
}

tako_cmd() {
  sudo -n "$ROOT/bin/takoctl.py" "$TAKO_SOCKET"
}

start_tako_server() {
  local env_args=()
  if [[ -n "${TAKO_MAX_REQUESTS_PER_IP:-}" ]]; then
    env_args+=("TAKO_MAX_REQUESTS_PER_IP=$TAKO_MAX_REQUESTS_PER_IP")
  fi

  sudo_high_nofile env "${env_args[@]}" "$TAKO_SERVER_BIN" \
    --data-dir "$TAKO_DATA" \
    --socket "$TAKO_SOCKET" \
    --http-port 18080 \
    --https-port 18443 \
    --metrics-port 0 \
    --no-acme \
    > "$ROOT/logs/tako-server.log" 2>&1 &
  echo $! > "$ROOT/run/tako-server.pid"
  for _ in $(seq 1 100); do
    [[ -S "$TAKO_SOCKET" ]] && return 0
    sleep 0.1
  done
  echo "tako-server socket did not become ready" >&2
  return 1
}

fix_tako_internal_socket_permissions() {
  for _ in $(seq 1 100); do
    if [[ -e "$TAKO_DATA/internal.sock" ]]; then
      sudo -n chgrp tako "$TAKO_DATA"/internal*.sock 2>/dev/null || true
      sudo -n chmod 0660 "$TAKO_DATA"/internal*.sock 2>/dev/null || true
      return 0
    fi
    sleep 0.1
  done
  echo "tako internal socket did not become ready" >&2
  return 1
}

deploy_tako() {
  local app="$1"
  local release="$2"
  local count="$3"
  local prepare="${4:-no}"
  local wait_path="${5:-plaintext}"
  if [[ "$prepare" == "yes" ]]; then
    jq -n --arg app "$app" --arg path "$release" \
      '{command: "prepare_release", app: $app, path: $path}' | tako_cmd >/tmp/tako-prepare-response.json
    jq -e '.status == "ok"' /tmp/tako-prepare-response.json >/dev/null
  fi
  jq -n \
    --arg app "$app" \
    --arg version "$TAKO_VERSION" \
    --arg path "$release" \
    --arg route "$ROUTE" \
    '{
      command: "deploy",
      app: $app,
      version: $version,
      path: $path,
      routes: [$route],
      source_ip: "direct",
      secrets: {},
      storages: {},
      ssl: { provider: "letsencrypt" },
      backup: null
    }' | tako_cmd >/tmp/tako-deploy-response.json
  jq -e '.status == "ok"' /tmp/tako-deploy-response.json >/dev/null
  jq -n --arg app "$app" --argjson instances "$count" \
    '{command: "scale", app: $app, instances: $instances}' | tako_cmd >/tmp/tako-scale-response.json
  jq -e '.status == "ok"' /tmp/tako-scale-response.json >/dev/null
  wait_https "$wait_path"
}

deploy_http_tako() {
  local count="$1"
  delete_tako_app "$TAKO_FEATURE_APP"
  deploy_tako "$TAKO_APP" "$TAKO_RELEASE" "$count" no
}

delete_tako_app() {
  local app="$1"
  jq -n --arg app "$app" '{command: "delete", app: $app}' | tako_cmd >/tmp/tako-delete-response.json || true
}

case "${1:-}" in
  stop)
    stop_all
    ;;
  nginx-single)
    stop_all
    mkdir -p "$ROOT/nginx"
    cp "$ROOT/configs/single.conf" "$ROOT/configs/nginx-active.conf"
    start_apps 1
    sudo_high_nofile nginx -c "$ROOT/configs/nginx-active.conf" -p "$ROOT/nginx"
    wait_https
    ;;
  nginx-lb)
    stop_all
    mkdir -p "$ROOT/nginx"
    cp "$ROOT/configs/lb.conf" "$ROOT/configs/nginx-active.conf"
    start_apps 4
    sudo_high_nofile nginx -c "$ROOT/configs/nginx-active.conf" -p "$ROOT/nginx"
    wait_https
    ;;
  caddy-single)
    stop_all
    start_apps 1
    sudo_high_nofile "$CADDY_BIN" run --config "$ROOT/configs/single.Caddyfile" --adapter caddyfile \
      > "$ROOT/logs/caddy.log" 2>&1 &
    echo $! > "$ROOT/run/caddy.pid"
    wait_https
    ;;
  caddy-lb)
    stop_all
    start_apps 4
    sudo_high_nofile "$CADDY_BIN" run --config "$ROOT/configs/lb.Caddyfile" --adapter caddyfile \
      > "$ROOT/logs/caddy.log" 2>&1 &
    echo $! > "$ROOT/run/caddy.pid"
    wait_https
    ;;
  haproxy-single)
    stop_all
    local_threads="$(nproc)"
    sed "s/__THREADS__/$local_threads/g" "$ROOT/configs/haproxy-single.cfg" > "$ROOT/configs/haproxy-active.cfg"
    start_apps 1
    sudo_high_nofile "$HAPROXY_BIN" -f "$ROOT/configs/haproxy-active.cfg" -p "$ROOT/run/haproxy.pid" -D \
      > "$ROOT/logs/haproxy.log" 2>&1
    wait_https
    ;;
  envoy-single)
    stop_all
    start_apps 1
    sudo_high_nofile "$ENVOY_BIN" -c "$ROOT/configs/envoy-single.yaml" --concurrency "$(nproc)" --log-level warn \
      > "$ROOT/logs/envoy.log" 2>&1 &
    echo $! > "$ROOT/run/envoy.pid"
    wait_https
    ;;
  pingora-single)
    stop_all
    start_apps 1
    sudo_high_nofile "$PINGORA_FIXED_PROXY_BIN" 18443 9101 \
      "$ROOT/certs/bench.test.crt" "$ROOT/certs/bench.test.key" \
      > "$ROOT/logs/pingora-fixed-proxy.log" 2>&1 &
    echo $! > "$ROOT/run/pingora-fixed-proxy.pid"
    wait_https
    ;;
  tako-single)
    stop_all
    start_tako_server
    deploy_http_tako 1
    ;;
  tako-lb)
    stop_all
    start_tako_server
    deploy_http_tako 4
    ;;
  tako-features)
    stop_all
    start_tako_server
    delete_tako_app "$TAKO_APP"
    deploy_tako "$TAKO_FEATURE_APP" "$TAKO_FEATURE_RELEASE" 1 yes status
    ;;
  *)
    echo "usage: $0 stop|nginx-single|nginx-lb|caddy-single|caddy-lb|haproxy-single|envoy-single|pingora-single|tako-single|tako-lb|tako-features" >&2
    exit 2
    ;;
esac
