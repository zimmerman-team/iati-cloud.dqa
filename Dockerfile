FROM python:3.11-slim

WORKDIR /app

# Install UV
RUN pip install --no-cache-dir uv

# Copy project files
COPY pyproject.toml .
COPY uv.lock .
COPY app ./app
COPY data ./data

# Install dependencies using UV (frozen = reproduce lockfile exactly)
RUN uv sync --frozen --no-dev

# Add venv binaries to PATH so gunicorn and other entrypoints are found
ENV PATH="/app/.venv/bin:$PATH"

# Expose port
EXPOSE 5000

# Run the application
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "app.main:app"]
