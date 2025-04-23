FROM eclipse-temurin:11.0.27_6-jre@sha256:71402f9fe72d629a227ce2d65e7366ada8c2fe8ad3bf4cb112446e3ab3dfb10e
# renovate: datasource=github-tags depName=Pugmatt/BedrockConnect versioning=loose
ENV BEDROCK_CONNECT=1.55
RUN mkdir -p /app
ADD https://github.com/Pugmatt/BedrockConnect/releases/download/${BEDROCK_CONNECT}/BedrockConnect-1.0-SNAPSHOT.jar /app/
ADD custom_servers.json /app
WORKDIR /app
EXPOSE 19132/udp
CMD ["java", "-Xms128M", "-Xmx128M", "-jar", "BedrockConnect-1.0-SNAPSHOT.jar", "nodb=true", "custom_servers=/app/custom_servers.json"]
