FROM eclipse-temurin:11.0.32_9-jre@sha256:4ccb3ef16bf278cca84540b204e315d19846b4808340b6c20aee201590401b13
# renovate: datasource=github-tags depName=Pugmatt/BedrockConnect versioning=loose
ENV BEDROCK_CONNECT=1.71.0
RUN mkdir -p /app
ADD https://github.com/Pugmatt/BedrockConnect/releases/download/${BEDROCK_CONNECT}/BedrockConnect-1.0-SNAPSHOT.jar /app/
ADD custom_servers.json /app
WORKDIR /app
EXPOSE 19132/udp
CMD ["java", "-Xms128M", "-Xmx128M", "-jar", "BedrockConnect-1.0-SNAPSHOT.jar", "nodb=true", "custom_servers=/app/custom_servers.json"]
