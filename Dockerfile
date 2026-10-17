# Official multi-platform image resolved on 2026-10-17 (Python 3.11.17).
# Review and refresh the digest when applying subsequent Python/base updates.
FROM python:3.11-slim-bookworm@sha256:0a310eeecf4e1f5a0743f9a6520c90c88d089c903ca5fd283f501e3a805f5f89

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY . .

# The runtime uses only the Python standard library. Compile and test during the
# image build so a broken image cannot be published as a runnable sandbox.
RUN python -S -m compileall -q run.py tideway scripts tests \
    && python -S scripts/verify_submission.py \
    && useradd --create-home --uid 10001 tideway \
    && mkdir -p /app/data \
    && chown -R tideway:tideway /app

USER tideway
EXPOSE 8787

# The container listens internally. For interactive use, publish explicitly on
# host loopback with -p 127.0.0.1:8787:8787. The verifier uses --network none and
# checks HTTP over container loopback through docker exec, without host ports.
CMD ["python", "run.py", "--host", "0.0.0.0", "--port", "8787", "--db", "/app/data/tideway.sqlite3"]
