FROM eclipse-temurin:11.0.21_9-jre@sha256:d544d3e33bc08d1b3a734960f950810c68a1d7f78a226dbf61e165a3400b61c8
# renovate: datasource=github-tags depName=Pugmatt/BedrockConnect versioning=semver
ENV BEDROCK_CONNECT=1.40
RUN mkdir -p /app
ADD https://github.com/Pugmatt/BedrockConnect/releases/download/${BEDROCK_CONNECT}/BedrockConnect-1.0-SNAPSHOT.jar /app/
ADD custom_servers.json /app
WORKDIR /app
EXPOSE 19132/udp
CMD ["java", "-Xms128M", "-Xmx128M", "-jar", "BedrockConnect-1.0-SNAPSHOT.jar", "nodb=true", "custom_servers=/app/custom_servers.json"]
