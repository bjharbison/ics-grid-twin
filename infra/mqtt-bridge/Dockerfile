FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bridge.py .

# Run unprivileged. The bridge only needs outbound TCP.
RUN useradd --create-home --uid 10001 bridge
USER bridge

CMD ["python", "-u", "bridge.py"]
