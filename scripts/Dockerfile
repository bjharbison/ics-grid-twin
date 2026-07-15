FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY mock_fleet.py .
RUN useradd --create-home --uid 10002 sim
USER sim
CMD ["python", "-u", "mock_fleet.py"]
