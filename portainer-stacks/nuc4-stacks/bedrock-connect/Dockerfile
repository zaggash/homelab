FROM eclipse-temurin:11.0.21_9-jre@sha256:efe41c483824a976f171445d8b294006c3724b438a15c92ec58c3183c4f34cc5
RUN mkdir -p /app
ADD custom_servers.json https://github.com/Pugmatt/BedrockConnect/releases/latest/download/BedrockConnect-1.0-SNAPSHOT.jar /app/
WORKDIR /app
EXPOSE 19132/udp
CMD ["java", "-Xms128M", "-Xmx128M", "-jar", "BedrockConnect-1.0-SNAPSHOT.jar", "nodb=true", "custom_servers=/app/custom_servers.json"]
