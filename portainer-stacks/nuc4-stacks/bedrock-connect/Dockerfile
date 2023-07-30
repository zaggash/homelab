FROM eclipse-temurin:11.0.20_8-jre@sha256:894577b0e822baf934c52d659f625565afa762d9f0df182495b1259164b7917f
RUN mkdir -p /app
ADD custom_servers.json https://github.com/Pugmatt/BedrockConnect/releases/latest/download/BedrockConnect-1.0-SNAPSHOT.jar /app/
WORKDIR /app
EXPOSE 19132/udp
CMD ["java", "-Xms128M", "-Xmx128M", "-jar", "BedrockConnect-1.0-SNAPSHOT.jar", "nodb=true", "custom_servers=/app/custom_servers.json"]
