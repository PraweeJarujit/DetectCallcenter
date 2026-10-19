FROM python:3.12-slim
# ffmpeg: เปิดไฟล์ mp3/m4a/webm (เสียงจาก LINE/มือถือ) · libsndfile: อ่าน wav/ogg/flac
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libsndfile1 curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY models ./models
RUN useradd -m -u 10001 ai && chown -R ai /srv
USER ai
ENV PORT=9000
EXPOSE 9000
HEALTHCHECK --interval=15s --timeout=5s --retries=5 CMD curl -fsS http://localhost:${PORT}/health || exit 1
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
