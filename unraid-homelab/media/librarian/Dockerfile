# Use a lightweight, minimal Python Alpine image
FROM python:3.11-alpine

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create app directory
WORKDIR /app

# Copy the bot script
COPY librarian_signal.py .

# Make the script executable
RUN chmod +x librarian_signal.py

# Create books_import directory
RUN mkdir -p /books_import

# Run the script
CMD ["python", "librarian_signal.py"]
