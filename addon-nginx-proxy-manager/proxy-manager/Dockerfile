ARG BUILD_FROM=ghcr.io/hassio-addons/base:18.0.2
# hadolint ignore=DL3006
FROM ${BUILD_FROM} AS downloader
ARG NGINX_PROXY_MANAGER_VERSION="v2.12.4"
RUN apk add --no-cache curl git patch=2.8-r0 yarn=1.22.22-r1 \
    && yarn global add modclean\
 && curl -J -L -o /nginxproxymanager.tar.gz \
    "https://github.com/NginxProxyManager/nginx-proxy-manager/archive/${NGINX_PROXY_MANAGER_VERSION}.tar.gz"

COPY patches/*.patch /tmp/patches/
RUN mkdir -p /usr/src && \
    for file in /tmp/patches/*.patch; do \
      if grep -qE 'package\.json|yarn\.lock|\.npmrc|\.yarnrc' "$file"; then \
        cp "$file" /usr/src/$(basename "$file"); \
      fi; \
    done

RUN mkdir /app \
    && tar zxvf \
        /nginxproxymanager.tar.gz \
        --strip 1 -C /app \
    \
    && for i in /usr/src/*.patch; do \
        patch -d /app -p 1 < "${i}"; done \
    \
    && cd /app/frontend \
    && yarn install --ignore-engines --network-timeout 100000 

FROM ${BUILD_FROM}

# Required for webpack config of NPM with Node.js 22
ENV NODE_OPTIONS="--openssl-legacy-provider"

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Copy patches not included in the downloader stage

COPY patches/*.patch /tmp/patches/
RUN mkdir -p /usr/src && \
    for file in /tmp/patches/*.patch; do \
      if ! grep -qE 'frontend/package\.json|frontend/yarn\.lock|\.npmrc|\.yarnrc' "$file"; then \
        cp "$file" /usr/src/$(basename "$file"); \
      fi; \
    done

COPY scripts/*.sh /usr/src/scripts/

RUN chmod +x /usr/src/scripts/*.sh

COPY --from=downloader /app /app

ARG PROXY_MANAGER_VERSION
# Setup base
ARG NGINX_PROXY_MANAGER_VERSION="v2.12.4"
# hadolint ignore=DL3003,DL3042
RUN apk add --no-cache --virtual .build-dependencies \
    build-base=0.5-r3 \
    git=2.49.1-r0 \
    libffi-dev=3.4.8-r0 \
    openssl-dev=3.5.1-r0 \
    patch=2.8-r0 \
    python3-dev=3.12.11-r0

RUN apk add --no-cache \
    apache2-utils \
    certbot=4.0.0-r0 \
    libcap=2.76-r0 \
    logrotate=3.21.0-r1 \
    nginx-mod-stream=1.28.0-r3 \
    nginx=1.28.0-r3 \
    nodejs=22.16.0-r2 \
    npm=11.3.0-r0 \
    openssl=3.5.1-r0 \
    py3-pip=25.1.1-r0 \
    python3=3.12.11-r0 \
    yarn=1.22.22-r1 \
    && yarn global add modclean

RUN adduser -S -H -s /sbin/nologin npm && \
    addgroup npm || true && \
    adduser npm npm && \
    mkdir -p /data/logs && \
    chown -R npm:npm /data/logs && \
    chmod -R g+w /data/logs

RUN for i in /usr/src/*.patch; do \
        patch -d /app -p 1 < "${i}"; done

RUN for i in /usr/src/scripts/*.sh; do \
        sh "${i}"; done

RUN cd /app/frontend \
    && yarn build --ignore-engines \
    && rm -rf node_modules \
    \
    && mkdir -p /opt/nginx-proxy-manager/frontend \
    && cp -r /app/frontend/dist/. /opt/nginx-proxy-manager/frontend/ \
    && cd /app/backend \
    && yarn install \
    && rm -rf node_modules \
    && cp -r /app/backend/. /opt/nginx-proxy-manager/ \
    \
    && cp -R /app/global/. /opt/nginx-proxy-manager/global/ \
    \
    && cd /opt/nginx-proxy-manager \
    && yarn install \
    && rm -rf /etc/services.d/frontend \
    && rm -rf /opt/nginx-proxy-manager/config \
    \
    && rm -f -r /etc/nginx \
    && cp -r /app/docker/rootfs/etc/nginx /etc/nginx \
    && rm -f /etc/nginx/conf.d/dev.conf \
    \
    && cp /app/docker/rootfs/etc/letsencrypt.ini /etc \
    && cp /app/docker/rootfs/etc/logrotate.d/nginx-proxy-manager /etc/logrotate.d \
    \
    && sed -i "s#user npm;#user root;#" /etc/nginx/nginx.conf \
    && sed -i "s#root /app/frontend;#root /opt/nginx-proxy-manager/frontend;#" \
        /etc/nginx/conf.d/production.conf \
    && sed -i "s#table.string('id').notNull().primary();#table.string('id', 32).notNull().primary();#" \
        /opt/nginx-proxy-manager/migrations/20190227065017_settings.js \
    \
    && mkdir -p \
        /run/nginx \
    \
    && modclean \
        --path /opt/nginx-proxy-manager \
        --no-progress \
        --keep-empty \
        --run \
    \
    && yarn global remove modclean \
    && yarn cache clean \
    \
    && apk del --purge .build-dependencies \
    \
    && rm -f -r \
        /app \
        /etc/init.d/nginx \
        /etc/logrotate.d/nginx \
        /opt/nginx-proxy-manager/node_modules/bcrypt/build \
        /root/.cache \
        /root/.node-gyp \
        /tmp/.[!.]* \
        /tmp/* \
        /usr/lib/node_modules \
        /usr/local/share/.cache \
        /var/lib/nginx \
        /var/log/nginx \
        /var/tmp/nginx \
        /var/www

# Copy root filesystem
COPY rootfs /

# Ensure all scripts in s6-rc.d are executable
RUN chmod -R +x /etc/s6-overlay/s6-rc.d

# Always run as root to ensure /dev/stdout is writable

# Build arguments
ARG BUILD_ARCH
ARG BUILD_DATE
ARG BUILD_DESCRIPTION
ARG BUILD_NAME
ARG BUILD_REF
ARG BUILD_REPOSITORY
ARG BUILD_VERSION

# Labels
LABEL \
    io.hass.name="${BUILD_NAME}" \
    io.hass.description="${BUILD_DESCRIPTION}" \
    io.hass.arch="${BUILD_ARCH}" \
    io.hass.type="addon" \
    io.hass.version=${BUILD_VERSION} \
    maintainer="Franck Nijhof <frenck@addons.community>" \
    org.opencontainers.image.title="${BUILD_NAME}" \
    org.opencontainers.image.description="${BUILD_DESCRIPTION}" \
    org.opencontainers.image.vendor="Home Assistant Community Add-ons" \
    org.opencontainers.image.authors="Franck Nijhof <frenck@addons.community>" \
    org.opencontainers.image.licenses="MIT" \
    org.opencontainers.image.url="https://addons.community" \
    org.opencontainers.image.source="https://github.com/${BUILD_REPOSITORY}" \
    org.opencontainers.image.documentation="https://github.com/${BUILD_REPOSITORY}/blob/main/README.md" \
    org.opencontainers.image.created=${BUILD_DATE} \
    org.opencontainers.image.revision=${BUILD_REF} \
    org.opencontainers.image.version=${BUILD_VERSION}
