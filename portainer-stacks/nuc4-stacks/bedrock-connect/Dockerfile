FROM eclipse-temurin:11.0.19_7-jre@sha256:18c3e334425f4fbf3a53f2f0df713e4d206894fb00ab2edde6df0311f5b63550
RUN mkdir -p /app
ADD custom_servers.json https://github.com/Pugmatt/BedrockConnect/releases/latest/download/BedrockConnect-1.0-SNAPSHOT.jar /app/
WORKDIR /app
EXPOSE 19132/udp
CMD ["java", "-Xms128M", "-Xmx128M", "-jar", "BedrockConnect-1.0-SNAPSHOT.jar", "nodb=true", "custom_servers=/app/custom_servers.json"]
