FROM eclipse-temurin:11.0.32_9-jre@sha256:36d9ed86b75e03d756fd4f3b9fdcf952451ddce4a4c451d23cf457ef2d591920
# renovate: datasource=github-tags depName=Pugmatt/BedrockConnect versioning=loose
ENV BEDROCK_CONNECT=1.70.0
RUN mkdir -p /app
ADD https://github.com/Pugmatt/BedrockConnect/releases/download/${BEDROCK_CONNECT}/BedrockConnect-1.0-SNAPSHOT.jar /app/
ADD custom_servers.json /app
WORKDIR /app
EXPOSE 19132/udp
CMD ["java", "-Xms128M", "-Xmx128M", "-jar", "BedrockConnect-1.0-SNAPSHOT.jar", "nodb=true", "custom_servers=/app/custom_servers.json"]
