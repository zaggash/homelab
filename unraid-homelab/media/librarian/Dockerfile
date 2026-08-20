# Use Debian-based Python slim image for Camoufox & Playwright compatibility
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV CAMOUFOX_HEADLESS=virtual

# Install OS libraries for headless Firefox/Camoufox, Xvfb and font rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    libgtk-3-0 \
    libdbus-glib-1-2 \
    libx11-xcb1 \
    libxtst6 \
    libxrandr2 \
    fonts-liberation \
    ca-certificates \
    curl \
    $(apt-cache search --names-only '^libasound2(t64)?$' | awk '{print $1}' | head -n 1) \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user matching standard homelab permissions (UID/GID 1000)
RUN groupadd -g 1000 librarian && \
    useradd -u 1000 -g librarian -m -d /app librarian

# Install Camoufox and fetch stealth browser binary pre-cached into image
RUN pip install --no-cache-dir camoufox[geoip] && \
    camoufox fetch && \
    chown -R librarian:librarian /app /root/.cache 2>/dev/null || true

# Set up workdir and import directory
WORKDIR /app
RUN mkdir -p /books_import && \
    chown -R librarian:librarian /app /books_import

# Copy application source code
COPY --chown=librarian:librarian src/ ./src/

# Switch to non-root user
USER librarian

# Healthcheck ensuring polling loop heartbeat stays fresh
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD test $(($(date +%s) - $(stat -c %Y /tmp/librarian_heartbeat 2>/dev/null || echo 0))) -lt 60 || exit 1

# Run the modular bot entrypoint
CMD ["python", "src/main.py"]
