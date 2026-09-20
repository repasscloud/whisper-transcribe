# Whisper Transcribe

A small, CPU-only Docker image for transcribing audio with
[faster-whisper](https://github.com/SYSTRAN/faster-whisper). Give it a WAV
file, get back `.txt` / `.srt` / `.vtt` / `.tsv` / `.json` transcripts.

## Why this exists

The original workflow this was built to replace used
[`mlx-whisper`](https://github.com/ml-explore/mlx-examples/tree/main/whisper),
which only runs on Apple Silicon via Metal. **`mlx-whisper` cannot run inside
Docker** — Docker Desktop on Mac runs Linux in a VM with no Metal/GPU
passthrough, so a container built around it fails at import.

This image swaps in `faster-whisper` (CTranslate2, CPU, int8-quantized)
instead. It's the closest CPU-portable equivalent: fast, small dependency
footprint (no PyTorch), and it runs anywhere Docker runs — your Mac, a Linux
box, a CI runner.

The CLI wrapper ([`transcribe.py`](transcribe.py)) mirrors the flags of the
original `mlx_whisper` command as closely as the two libraries allow, so the
muscle memory carries over.

## Image contents

- Base: `python:3.12-slim`
- System deps: `ffmpeg` (decodes arbitrary audio containers), `libgomp1`
  (required by `ctranslate2`)
- Python deps: `faster-whisper`, `requests` (see [Gotchas](#gotchas))
- No PyTorch, no CUDA, nothing GPU-related
- Built size: **~1.2 GB** (model weights are *not* baked in — see
  [Model caching](#model-caching))

## Quick start

```bash
docker build -t whisper-transcribe .
```

```bash
mkdir -p input transcript models
cp /path/to/your/recording.wav input/

docker run --rm \
  -v "$(pwd)/input:/data/input:ro" \
  -v "$(pwd)/transcript:/data/transcript" \
  -v "$(pwd)/models:/data/models" \
  whisper-transcribe /data/input/recording.wav
```

Transcripts land in `./transcript/recording.txt`, `.srt`, `.vtt`, `.tsv`,
`.json`.

Running the image with no arguments prints `--help` instead of erroring out
(see [How `--help` works](#how---help-works)).

## Volumes

| Container path | Purpose | Mount as |
| --- | --- | --- |
| `/data/input` | Where you put the audio file(s) you're feeding in | read-only bind mount |
| `/data/transcript` | Where output files are written | bind mount (so you can see them on the host) |
| `/data/models` | Hugging Face model cache (`HF_HOME`) | **named volume**, keep persistent |

### Model caching

The models volume matters: without it, every `docker run` re-downloads the
model from Hugging Face on every single run. `large-v3-turbo` is roughly
1.6 GB — you do not want that on every transcription. Use a named volume
(`-v whisper-models:/data/models`) rather than a bind mount so Docker manages
it and it survives image rebuilds.

## Configuration

Every flag has a matching environment variable baked into the image as a
default (set in the [Dockerfile](Dockerfile)). Override per-run either with
CLI flags or `-e` env vars — flags win if both are given.

| Flag | Env var | Default | Notes |
| --- | --- | --- | --- |
| `audio` (positional, required) | — | — | Path to input audio file inside the container |
| `--model` | `WHISPER_MODEL` | `large-v3-turbo` | Any faster-whisper/CTranslate2 model name or local path |
| `--language` | `WHISPER_LANGUAGE` | `en` | Language code, or `auto` to detect |
| `--compute-type` | `WHISPER_COMPUTE_TYPE` | `int8` | `int8` \| `int8_float32` \| `float32` \| `float16` |
| `--cpu-threads` | `WHISPER_CPU_THREADS` | `0` (auto) | `0` lets ctranslate2 pick |
| `--condition-on-previous-text` | `WHISPER_CONDITION_ON_PREVIOUS_TEXT` | `False` | |
| `--no-speech-threshold` | `WHISPER_NO_SPEECH_THRESHOLD` | `0.4` | |
| `--word-timestamps` | `WHISPER_WORD_TIMESTAMPS` | `True` | |
| `--hallucination-silence-threshold` | `WHISPER_HALLUCINATION_SILENCE_THRESHOLD` | `1.5` | |
| `--vad-filter` | `WHISPER_VAD_FILTER` | `True` | Voice-activity filter; not in the original mlx flags, on by default to cut hallucinations on silence |
| `--beam-size` | `WHISPER_BEAM_SIZE` | `5` | Not in the original mlx flags; faster-whisper-specific |
| `--output-dir` | `WHISPER_OUTPUT_DIR` | `/data/transcript` | |
| `--output-format` | `WHISPER_OUTPUT_FORMAT` | `all` | `txt` \| `vtt` \| `srt` \| `tsv` \| `json` \| `all` |

Only `audio` has no default — you must always pass it.

### Examples

Use a smaller/faster model:

```bash
docker run --rm -v "$(pwd)/input:/data/input:ro" -v "$(pwd)/transcript:/data/transcript" \
  -v whisper-models:/data/models \
  whisper-transcribe --model medium /data/input/recording.wav
```

Auto-detect language, only write SRT:

```bash
docker run --rm -v "$(pwd)/input:/data/input:ro" -v "$(pwd)/transcript:/data/transcript" \
  -v whisper-models:/data/models \
  whisper-transcribe --language auto --output-format srt /data/input/recording.wav
```

Set defaults via env instead of flags (handy in `docker-compose.yml` or CI):

```bash
docker run --rm -v "$(pwd)/input:/data/input:ro" -v "$(pwd)/transcript:/data/transcript" \
  -v whisper-models:/data/models \
  -e WHISPER_MODEL=medium \
  -e WHISPER_LANGUAGE=auto \
  -e WHISPER_OUTPUT_FORMAT=srt \
  whisper-transcribe /data/input/recording.wav
```

### docker-compose

```yaml
services:
  whisper:
    build: .
    image: whisper-transcribe
    volumes:
      - ./input:/data/input:ro
      - ./transcript:/data/transcript
      - whisper-models:/data/models
    environment:
      WHISPER_MODEL: large-v3-turbo
      WHISPER_LANGUAGE: en
    entrypoint: ["python", "transcribe.py"]
    command: ["/data/input/recording.wav"]

volumes:
  whisper-models:
```

## How `--help` works

The Dockerfile ends with:

```dockerfile
ENTRYPOINT ["python", "transcribe.py"]
CMD ["--help"]
```

Docker always runs `ENTRYPOINT` + `CMD` concatenated. `CMD` is just the
*default* tail — anything you pass after the image name on `docker run`
replaces it entirely.

- `docker run whisper-transcribe` → no args given → falls back to `CMD`
  → runs `python transcribe.py --help`
- `docker run whisper-transcribe /data/input/recording.wav` → your arg
  replaces `CMD` → runs `python transcribe.py /data/input/recording.wav`

## Output formats

`--output-format all` (the default) writes all five, named after the input
file's stem (`recording.wav` → `recording.txt`, `recording.srt`, ...):

- **txt** — plain text, one line per segment
- **vtt** — WebVTT subtitles
- **srt** — SubRip subtitles
- **tsv** — tab-separated `start\tend\ttext` in milliseconds
- **json** — full result: `text`, `segments` (with per-word timestamps when
  `--word-timestamps true`), `language`

An empty `.txt`/`.srt` for a given run is expected behavior if the audio
segment in question is silence or non-speech — the VAD filter and
no-speech threshold are working as intended, not a bug.

## Model notes

- `large-v3-turbo` resolves to the `Systran/faster-whisper-large-v3` family
  of CTranslate2-converted weights on Hugging Face — the same model class as
  MLX's, re-exported for CTranslate2. Transcription quality should be
  comparable; this is CPU-only so it will be slower than the Metal-accelerated
  MLX path on the same Mac.
- If raw throughput matters more than portability, running `mlx-whisper`
  natively (outside Docker) on Apple Silicon will still be faster.
- Smaller models (`tiny`, `base`, `small`, `medium`) trade accuracy for
  speed and are worth using for quick drafts or CI smoke tests.

## Gotchas

- **`requests` is pinned as a direct dependency** even though it's not
  imported by `transcribe.py` directly — `faster-whisper`'s own model
  download path needs it and doesn't declare it as a hard dependency in
  every release. Without it you'll hit `ModuleNotFoundError: No module
  named 'requests'` at model-load time. Keep it in `requirements.txt`.
- **`cpu_threads` must be an int, not `None`**, when calling
  `WhisperModel(...)` — `ctranslate2`'s constructor rejects `None`. The
  wrapper always passes an int (`0` means "let ctranslate2 decide").
- **Unauthenticated Hugging Face Hub warning** on first run
  (`Please set a HF_TOKEN...`) is harmless — it just means slower/rate-limited
  downloads, not a failure. Set `HF_TOKEN` as an env var if you hit rate
  limits.
- **No GPU support.** This image is CPU-only by design. If you need GPU
  acceleration on Linux with an NVIDIA card, you'd need a CUDA-enabled base
  image and `nvidia-container-toolkit` — a materially different (and much
  larger) image than this one.

## Repo layout

```text
.
├── Dockerfile        # image definition
├── transcribe.py      # CLI wrapper around faster-whisper
├── requirements.txt   # faster-whisper + requests
├── .dockerignore
└── README.md
```

## Development

Rebuild after any change to `Dockerfile`, `requirements.txt`, or
`transcribe.py`:

```bash
docker build -t whisper-transcribe .
```

Smoke test with the smallest model so you're not waiting on a multi-GB
download:

```bash
docker run --rm \
  -v "$(pwd)/input:/data/input:ro" \
  -v "$(pwd)/transcript:/data/transcript" \
  -v whisper-models:/data/models \
  whisper-transcribe --model tiny /data/input/recording.wav
```
