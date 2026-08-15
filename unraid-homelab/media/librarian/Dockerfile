# Use a lightweight, minimal Python Alpine image
FROM python:3.13-alpine

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create a non-root user and group matching standard homelab permissions (UID/GID 1000)
RUN addgroup -g 1000 librarian && \
    adduser -u 1000 -G librarian -S -D -h /app librarian

# Create directories and set correct ownership
WORKDIR /app
RUN mkdir -p /books_import && \
    chown -R librarian:librarian /app /books_import

# Copy the bot script
COPY --chown=librarian:librarian librarian_signal.py .

# Make the script executable
RUN chmod +x librarian_signal.py

# Switch to non-root user
USER librarian

# Healthcheck ensuring polling loop heartbeat stays fresh
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD test $(($(date +%s) - $(stat -c %Y /tmp/librarian_heartbeat 2>/dev/null || echo 0))) -lt 60 || exit 1

# Run the script
CMD ["python", "librarian_signal.py"]

