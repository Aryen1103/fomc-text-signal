# Linux environment for the model-based tone scorers (phase 2). The repository is
# mounted at /work, so data, the model cache and results stay on the host:
#   docker build -t fomc-signal .
#   docker run --rm -v "$PWD":/work fomc-signal python scripts/score.py --validate
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/work/src HF_HOME=/work/data/hf_cache
COPY requirements.txt requirements-models.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
 && pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir "transformers>=4.40" sentencepiece protobuf
WORKDIR /work
