FROM nousresearch/hermes-agent:v2026.9.7@sha256:63bfb6d732f49a55d453e801057273785cc61e0f6ee43db3fa2f2a79846301b7

RUN apt-get update && apt-get install -y libolm-dev cmake g++ && rm -rf /var/lib/apt/lists/*
RUN uv pip install --python /opt/hermes/.venv/bin/python 'mautrix[encryption]' asyncpg aiosqlite Markdown aiohttp-socks
