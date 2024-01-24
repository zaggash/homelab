FROM eclipse-temurin:11.0.22_7-jre@sha256:a99d4e4a457b2d1ae2046d878298c2f22bd2d98a636f24b866b62bbdfde656c3
# renovate: datasource=github-tags depName=Pugmatt/BedrockConnect versioning=semver
ENV BEDROCK_CONNECT=1.40
RUN mkdir -p /app
ADD https://github.com/Pugmatt/BedrockConnect/releases/download/${BEDROCK_CONNECT}/BedrockConnect-1.0-SNAPSHOT.jar /app/
ADD custom_servers.json /app
WORKDIR /app
EXPOSE 19132/udp
CMD ["java", "-Xms128M", "-Xmx128M", "-jar", "BedrockConnect-1.0-SNAPSHOT.jar", "nodb=true", "custom_servers=/app/custom_servers.json"]
