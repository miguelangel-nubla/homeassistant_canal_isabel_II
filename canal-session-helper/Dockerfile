FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        chromium xvfb x11vnc novnc websockify \
        python3 python3-websocket ca-certificates fonts-liberation \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 helper \
    && mkdir -p /data /tmp/.X11-unix \
    && chown helper:helper /data \
    && chmod 1777 /tmp/.X11-unix

COPY entrypoint.sh helper.py ingress_guard.py /app/
COPY index.html /usr/share/novnc/index.html
RUN chmod 755 /app/entrypoint.sh

# Starts as root only to take ownership of /data, then drops to "helper"
# (see entrypoint.sh). Running it with another user is fine too.
ENV DISPLAY=:99
VOLUME /data
EXPOSE 6080

ENTRYPOINT ["/app/entrypoint.sh"]
