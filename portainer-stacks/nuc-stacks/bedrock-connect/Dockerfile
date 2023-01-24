FROM eclipse-temurin:11.0.18_10-jre@sha256:58df1f3c9e689479d218df383c04040613864ef737dfb21cb4109a9ad444578d
RUN mkdir -p /app
ADD custom_servers.json https://github.com/Pugmatt/BedrockConnect/releases/latest/download/BedrockConnect-1.0-SNAPSHOT.jar /app/
WORKDIR /app
EXPOSE 19132/udp
CMD ["java", "-Xms128M", "-Xmx128M", "-jar", "BedrockConnect-1.0-SNAPSHOT.jar", "nodb=true", "custom_servers=/app/custom_servers.json"]
