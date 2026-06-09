FROM nousresearch/hermes-agent:v2026.6.5@sha256:9ad3b04ec916ea2c2da22358fd43b024c788d74073210695af88bfc2e63869b4

RUN apt-get update && apt-get install -y libolm-dev cmake g++ && rm -rf /var/lib/apt/lists/*
RUN uv pip install --python /opt/hermes/.venv/bin/python 'mautrix[encryption]' asyncpg aiosqlite Markdown aiohttp-socks
