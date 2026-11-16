# Pinned by digest so that a build is repeatable; Dependabot proposes the
# newer ones. The browser itself is the newest that Debian has at build time.
FROM debian:bookworm-slim@sha256:734a72b3d6142a71993b4bc580ca01d8ca687f77a2c422d96a961d3376b179bc

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        chromium xvfb x11vnc novnc websockify \
        python3 python3-websocket ca-certificates fonts-liberation \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 helper \
    && mkdir -p /data /tmp/.X11-unix \
    && chown helper:helper /data \
    && chmod 1777 /tmp/.X11-unix

COPY entrypoint.sh helper.py healthcheck.py ingress_guard.py /app/
COPY index.html /usr/share/novnc/index.html
RUN chmod 755 /app/entrypoint.sh

# Starts as root only to take ownership of /data, then drops to "helper"
# (see entrypoint.sh). Running it with another user is fine too.
ENV DISPLAY=:99
VOLUME /data
EXPOSE 6080

# Healthy while the helper's loop goes round (healthcheck.py).
HEALTHCHECK --interval=1m --timeout=10s --start-period=3m --retries=3 \
    CMD ["python3", "/app/healthcheck.py"]

ENTRYPOINT ["/app/entrypoint.sh"]
