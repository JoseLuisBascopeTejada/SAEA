FROM python:3.11-slim

WORKDIR /app

COPY requirements/base.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
# insightface pulls in opencv-python as a transitive dep, overwriting headless and causing libxcb.so.1 ImportError — reinstall headless last.
RUN pip install --no-cache-dir --force-reinstall opencv-python-headless

COPY app/ app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
