FROM python:3.11.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY . .

# The runtime uses only the Python standard library. Compile and test during the
# image build so a broken image cannot be published as a runnable sandbox.
RUN python -m compileall -q run.py tideway scripts tests \
    && python -m unittest discover -s tests -q \
    && useradd --create-home --uid 10001 tideway \
    && mkdir -p /app/data \
    && chown -R tideway:tideway /app

USER tideway
EXPOSE 8787

# The container listens on all interfaces internally; docker-run publishes it
# only on the host loopback address.
CMD ["python", "run.py", "--host", "0.0.0.0", "--port", "8787", "--db", "/app/data/tideway.sqlite3"]
