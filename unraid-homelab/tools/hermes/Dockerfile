FROM nousresearch/hermes-agent:v2026.7.30@sha256:b869e64d6496d4763d5e4fb675b5f504cb23b0e35ec9b790481a56118602b10f

RUN apt-get update && apt-get install -y libolm-dev cmake g++ && rm -rf /var/lib/apt/lists/*
RUN uv pip install --python /opt/hermes/.venv/bin/python 'mautrix[encryption]' asyncpg aiosqlite Markdown aiohttp-socks
