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

COPY entrypoint.sh helper.py /app/
RUN chmod 755 /app/entrypoint.sh

USER helper
ENV DISPLAY=:99
VOLUME /data
EXPOSE 6080

ENTRYPOINT ["/app/entrypoint.sh"]
