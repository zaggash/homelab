FROM eclipse-temurin:11.0.31_11-jre@sha256:1cd29bec846b73a790ff778da2a416b3934a78eaa238ecd0a43a5c989e0e23bc
# renovate: datasource=github-tags depName=Pugmatt/BedrockConnect versioning=loose
ENV BEDROCK_CONNECT=1.69.0
RUN mkdir -p /app
ADD https://github.com/Pugmatt/BedrockConnect/releases/download/${BEDROCK_CONNECT}/BedrockConnect-1.0-SNAPSHOT.jar /app/
ADD custom_servers.json /app
WORKDIR /app
EXPOSE 19132/udp
CMD ["java", "-Xms128M", "-Xmx128M", "-jar", "BedrockConnect-1.0-SNAPSHOT.jar", "nodb=true", "custom_servers=/app/custom_servers.json"]
