# renovate: datasource=github-tags depName=warmcat/libwebsockets versioning=semver
ARG LIBWEBSOCKET_VERSION=4.5.2
# renovate: datasource=github-tags depName=eclipse-mosquitto/mosquitto versioning=semver
ARG MOSQUITTO_VERSION=2.1.1
# renovate: datasource=github-tags depName=iegomez/mosquitto-go-auth versioning=semver
ARG MOSQUITTO_AUTH_VERSION=3.0.0


#### Use debian:stable-slim as a builder for Mosquitto and libwebsockets.
FROM debian:stable-slim as mosquitto_builder
ARG LIBWEBSOCKET_VERSION
ARG MOSQUITTO_VERSION
# Build libwebsockets
RUN set -ex \
  && apt-get update \
  && apt-get install -y \
       wget \
       git \
       build-essential \
       cmake \
       libargon2-dev \
       libssl-dev \
       libcjson-dev \
       libedit-dev \
       libmicrohttpd-dev \
       libsqlite3-dev \
  && wget --inet4-only https://github.com/warmcat/libwebsockets/archive/v${LIBWEBSOCKET_VERSION}.tar.gz \
       -O /tmp/lws.tar.gz \
  && mkdir -p /build/lws \
  && tar --strip=1 -xf /tmp/lws.tar.gz -C /build/lws \
  && cd /build/lws \
  && cmake . \
       -DCMAKE_BUILD_TYPE=MinSizeRel \
       -DCMAKE_INSTALL_PREFIX=/usr \
       -DLWS_IPV6=ON \
       -DLWS_WITHOUT_BUILTIN_GETIFADDRS=ON \
       -DLWS_WITHOUT_CLIENT=ON \
       -DLWS_WITHOUT_EXTENSIONS=ON \
       -DLWS_WITHOUT_TESTAPPS=ON \
       -DLWS_WITH_HTTP2=OFF \
       -DLWS_WITH_SHARED=OFF \
       -DLWS_WITH_ZIP_FOPS=OFF \
       -DLWS_WITH_ZLIB=OFF \
       -DLWS_WITH_EXTERNAL_POLL=ON \
  && make -j "$(nproc)"

RUN set -ex \
  && mkdir -p /app \
  && cd /app \
  && wget --inet4-only https://mosquitto.org/files/source/mosquitto-${MOSQUITTO_VERSION}.tar.gz \
  && tar xzvf mosquitto-${MOSQUITTO_VERSION}.tar.gz \
  && cd mosquitto-${MOSQUITTO_VERSION} \
  && make CFLAGS="-Wall -O2 -I/build/lws/include" LDFLAGS="-L/build/lws/lib" \
       WITH_WEBSOCKETS=yes \
       WITH_ADNS=no \
       WITH_DOCS=no \
       WITH_SHARED_LIBRARIES=yes \
       WITH_SRV=no \
       WITH_STRIP=yes \
  && make install


#### Use golang:latest as a builder for the Mosquitto Go Auth plugin.
FROM golang:latest AS go_auth_builder
ARG MOSQUITTO_AUTH_VERSION
ENV CGO_CFLAGS="-I/usr/local/include -fPIC"
ENV CGO_LDFLAGS="-shared -Wl,-unresolved-symbols=ignore-all"
ENV CGO_ENABLED=1

COPY --from=mosquitto_builder /usr/local/include/ /usr/local/include/

RUN set -ex \
  && apt-get update \
  && apt install -y \
       libcjson1 \
       libcjson-dev \
  && mkdir /app \
  && cd /app \
  && wget --inet4-only \
       https://github.com/iegomez/mosquitto-go-auth/archive/refs/tags/${MOSQUITTO_AUTH_VERSION}.tar.gz \
       -O /tmp/mosquitto-go-auth-${MOSQUITTO_AUTH_VERSION}.tar.gz \
  && tar xvzf /tmp/mosquitto-go-auth-${MOSQUITTO_AUTH_VERSION}.tar.gz -C /app --strip-components=1 \
  && go build -buildmode=c-archive go-auth.go \
  && go build -buildmode=c-shared -o go-auth.so \
  && go build pw-gen/pw.go


#### Create from a new image.
FROM debian:stable-slim@sha256:4448d44b91bf4a13cb1b4e02d9d5f87ed40621d6e33f0ae7b6ddf71d57e29364
RUN set -ex \
  && apt update \
  && apt install -y \
       bash \
       tzdata \
       openssl \
       ca-certificates \
       libc-ares2 \
       openssl \
       uuid \
       tini \
       wget \
       libssl-dev \
       libcjson-dev \

  && mkdir -p /var/lib/mosquitto /var/log/mosquitto /mosquitto/conf.d \
  && wget https://raw.githubusercontent.com/eclipse-mosquitto/mosquitto/refs/heads/master/docker/generic/mosquitto-no-auth.conf \
       -O /mosquitto/conf.d/mosquitto.conf \
  && groupadd mosquitto \
  && useradd -s /sbin/nologin mosquitto -g mosquitto -d /var/lib/mosquitto \
  && chown -R mosquitto:mosquitto /var/lib/mosquitto /var/log/mosquitto

COPY --from=mosquitto_builder /usr/local/sbin/mosquitto /usr/sbin/mosquitto
COPY --from=mosquitto_builder /usr/local/lib/libmosquitto* /usr/local/lib/

COPY --from=mosquitto_builder /usr/local/bin/mosquitto_passwd /usr/bin/mosquitto_passwd
COPY --from=mosquitto_builder /usr/local/bin/mosquitto_sub /usr/bin/mosquitto_sub
COPY --from=mosquitto_builder /usr/local/bin/mosquitto_pub /usr/bin/mosquitto_pub
COPY --from=mosquitto_builder /usr/local/bin/mosquitto_rr /usr/bin/mosquitto_rr

COPY --from=go_auth_builder /app/pw /mosquitto/pw
COPY --from=go_auth_builder /app/go-auth.so /mosquitto/go-auth.so

RUN ldconfig
WORKDIR /mosquitto
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD [ "/usr/sbin/mosquitto" ,"-c", "/mosquitto/conf.d/mosquitto.conf" ]
