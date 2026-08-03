FROM nousresearch/hermes-agent:v2026.8.3@sha256:16788311e2fa3035456bdc1bafb8ec2b1777db64ebf020af9bb7eb73c3712c9e

RUN apt-get update && apt-get install -y libolm-dev cmake g++ && rm -rf /var/lib/apt/lists/*
RUN uv pip install --python /opt/hermes/.venv/bin/python 'mautrix[encryption]' asyncpg aiosqlite Markdown aiohttp-socks
