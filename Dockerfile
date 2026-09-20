FROM python:3.12-slim AS base

# faster-whisper needs libgomp for ctranslate2, and ffmpeg to decode arbitrary
# audio containers before feeding samples in. Nothing else.
RUN DEBIAN_FRONTEND=noninteractive apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ffmpeg libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && find /usr/local/lib/python3.12 -name '__pycache__' -exec rm -rf {} + \
    && find /usr/local/lib/python3.12 -name '*.pyc' -delete

COPY transcribe.py .

# Model weights are downloaded to this volume on first run and cached there,
# so re-runs and other containers sharing the volume don't re-download.
ENV HF_HOME=/data/models \
    WHISPER_MODEL=large-v3-turbo \
    WHISPER_LANGUAGE=en \
    WHISPER_COMPUTE_TYPE=int8 \
    WHISPER_CONDITION_ON_PREVIOUS_TEXT=False \
    WHISPER_NO_SPEECH_THRESHOLD=0.4 \
    WHISPER_WORD_TIMESTAMPS=True \
    WHISPER_HALLUCINATION_SILENCE_THRESHOLD=1.5 \
    WHISPER_OUTPUT_DIR=/data/transcript \
    WHISPER_OUTPUT_FORMAT=all

RUN mkdir -p /data/models /data/transcript /data/input

VOLUME ["/data/transcript", "/data/models"]

ENTRYPOINT ["python", "transcribe.py"]
CMD ["--help"]