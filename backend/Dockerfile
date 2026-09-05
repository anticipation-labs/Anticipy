# PocketBase backend for Anticipy — production image.
FROM alpine:3.20
ARG PB_VERSION=0.30.4
RUN apk add --no-cache ca-certificates unzip wget sqlite \
    && wget -q "https://github.com/pocketbase/pocketbase/releases/download/v${PB_VERSION}/pocketbase_${PB_VERSION}_linux_amd64.zip" -O /tmp/pb.zip \
    && unzip /tmp/pb.zip -d /app \
    && rm /tmp/pb.zip
COPY pb_migrations /app/pb_migrations
COPY pb_public /app/pb_public
COPY pb_hooks /app/pb_hooks
WORKDIR /app
# Railway injects PORT; pb_data lives on the attached volume.
# The volume filled (2026-08-15) and PocketBase could not even open its
# database: "disk I/O error", crash loop, hard outage. PocketBase's REQUEST-LOG
# database is separate from the data, is recreated empty on boot, and is the
# one large file that can be removed without losing a single customer record —
# so reclaim it before serving whenever headroom is gone. Data (data.db) is
# never touched here.
COPY start.sh /app/start.sh
COPY repair_data_db.sh /app/repair_data_db.sh
RUN chmod +x /app/start.sh
CMD ["/app/start.sh"]
