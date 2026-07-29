# PocketBase backend for Anticipy — production image.
FROM alpine:3.20
ARG PB_VERSION=0.30.4
RUN apk add --no-cache ca-certificates unzip wget \
    && wget -q "https://github.com/pocketbase/pocketbase/releases/download/v${PB_VERSION}/pocketbase_${PB_VERSION}_linux_amd64.zip" -O /tmp/pb.zip \
    && unzip /tmp/pb.zip -d /app \
    && rm /tmp/pb.zip
COPY pb_migrations /app/pb_migrations
WORKDIR /app
# Railway injects PORT; pb_data lives on the attached volume.
CMD ./pocketbase serve --http 0.0.0.0:${PORT:-8090} --dir /pb_data --migrationsDir /app/pb_migrations
