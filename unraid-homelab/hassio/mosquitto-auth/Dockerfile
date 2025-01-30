FROM debian:stable-slim

# Install mosquitto + auth plugin
WORKDIR /usr/src

# renovate: datasource=github-tags depName=warmcat/libwebsockets versioning=semver
ARG LIBWEBSOCKET_VERSION=4.3.3
# renovate: datasource=github-tags depName=eclipse-mosquitto/mosquitto versioning=semver
ARG MOSQUITTO_VERSION=2.0.20
# renovate: datasource=github-tags depName=iegomez/mosquitto-go-auth versioning=semver
ARG MOSQUITTO_AUTH_VERSION=2.1.0

RUN apt-get update \
    && apt-get install -qy --no-install-recommends \
        pwgen \
        tini \
        bash \
        jq \
        tzdata \
        curl \
        ca-certificates \
        xz-utils \
        build-essential \
        cmake \
        git \
        ca-certificates \
        openssl \
        libssl-dev \
        libc-ares2 \
        libc-ares-dev \
        libcjson1 \
        libcjson-dev \
        xsltproc \
        docbook-xsl \
        golang-go \
    \

    # Compile and install libwebsocket
    #
    # DLWS_WITHOUT_TESTAPPS is just a workaround, see
    # https://github.com/warmcat/libwebsockets/issues/2790 for more
    && git clone --depth 1 -b "v${LIBWEBSOCKET_VERSION}" \
       https://libwebsockets.org/repo/libwebsockets \
    \
    && cd libwebsockets \
    && mkdir build \
    && cd build \
    && cmake -DLWS_WITH_EXTERNAL_POLL=ON -DLWS_WITHOUT_TESTAPPS=ON .. \
    && make install \
    && ldconfig \
    && cd ../.. \

    # Compile and install mosquitto
    && git clone --depth 1 -b "v${MOSQUITTO_VERSION}" \
       https://github.com/eclipse/mosquitto \
    \
    && cd mosquitto \
    && make WITH_WEBSOCKETS=yes WITH_SRV=yes \
    && make install \
    && cd .. \

    # Compile and install mosquitto-go-auth
    && git clone --depth 1 -b "${MOSQUITTO_AUTH_VERSION}" \
       https://github.com/iegomez/mosquitto-go-auth \
    \
    && cd mosquitto-go-auth \
    && sed -i 's/-I\/usr\/local\/include/-I\/usr\/include/' Makefile \
    && sed -i 's/LDFLAGS := .*$/& -Wl,-unresolved-symbols=ignore-all/' Makefile \
    && make \
    && mkdir -p /usr/share/mosquitto \
    && cp -f go-auth.so /usr/share/mosquitto \
    && cp -f pw /usr/local/bin \
    \

    && apt-get purge -y --auto-remove \
        build-essential \
        git \
        cmake \
        libssl-dev \
        libc-ares-dev \
        libcjson-dev \
        xsltproc \
        docbook-xsl \
        golang-go \
    && apt-get clean \
    && rm -fr \
        /etc/logrotate.d \
        /etc/mosquitto/* \
        /usr/src/libwebsockets \
        /usr/src/mosquitto \
        /usr/src/mosquitto-go-auth \
        /var/www \
        /var/lib/apt/lists/* \
	      /root/.cache \
	      /root/go

WORKDIR /mosquitto
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD [ "/usr/local/sbin/mosquitto" ,"-c", "/mosquitto/config/mosquitto.conf" ]
