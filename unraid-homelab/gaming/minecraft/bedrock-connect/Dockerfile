FROM eclipse-temurin:11.0.25_9-jre@sha256:aad86b65775cf99e8bfdc4636c7adabc3b872172bd598d25a2e7a74cf6505a85
# renovate: datasource=github-tags depName=Pugmatt/BedrockConnect versioning=loose
ENV BEDROCK_CONNECT=1.51
RUN mkdir -p /app
ADD https://github.com/Pugmatt/BedrockConnect/releases/download/${BEDROCK_CONNECT}/BedrockConnect-1.0-SNAPSHOT.jar /app/
ADD custom_servers.json /app
WORKDIR /app
EXPOSE 19132/udp
CMD ["java", "-Xms128M", "-Xmx128M", "-jar", "BedrockConnect-1.0-SNAPSHOT.jar", "nodb=true", "custom_servers=/app/custom_servers.json"]
