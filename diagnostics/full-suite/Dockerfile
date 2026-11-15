FROM envoyproxy/envoy:v1.38.0@sha256:8146b97ee61a42cd216514709e4e3198af75f014974e3d9f310aef9c901fcbdf AS envoy
FROM ubuntu:26.04@sha256:065aa8626841f16057b78b027b464cd59c4fac36c204c72dcbf48d66f5fa8a96
ENV DEBIAN_FRONTEND=noninteractive
RUN --mount=type=secret,id=proxy_ca \
    apt-get -o Acquire::https::CaInfo=/run/secrets/proxy_ca update && \
    apt-get -o Acquire::https::CaInfo=/run/secrets/proxy_ca install -y --no-install-recommends \
      ca-certificates curl git sudo libvips42 libcap2-bin podman zstd python3 procps iproute2 openssl nginx haproxy \
      netcat-openbsd libheif-plugin-aomenc libheif-plugin-aomdec libheif-plugin-dav1d && \
    rm -rf /var/lib/apt/lists/*
COPY --from=envoy /usr/local/bin/envoy /usr/local/bin/envoy
COPY diagnostics/full-suite/entrypoint.sh /entrypoint.sh
ENTRYPOINT ["bash", "/entrypoint.sh"]
