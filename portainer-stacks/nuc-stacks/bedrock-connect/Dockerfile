FROM eclipse-temurin:11-jre@sha256:772b0000ef09d2099ef07d1df87b12d942248419e79ff46fa739a5feb617e543
RUN mkdir -p /app
ADD custom_servers.json https://github.com/Pugmatt/BedrockConnect/releases/latest/download/BedrockConnect-1.0-SNAPSHOT.jar /app/
WORKDIR /app
EXPOSE 19132/udp
CMD ["java", "-Xms128M", "-Xmx128M", "-jar", "BedrockConnect-1.0-SNAPSHOT.jar", "nodb=true", "custom_servers=/app/custom_servers.json"]
