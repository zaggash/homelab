FROM nousresearch/hermes-agent:v2026.7.7@sha256:ce3b39adf33fffae8cb19dcae74f971975b972efe91207f7d7539f80a0aae66a

RUN apt-get update && apt-get install -y libolm-dev cmake g++ && rm -rf /var/lib/apt/lists/*
RUN uv pip install --python /opt/hermes/.venv/bin/python 'mautrix[encryption]' asyncpg aiosqlite Markdown aiohttp-socks
