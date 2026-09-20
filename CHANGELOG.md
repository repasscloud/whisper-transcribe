# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-09-20

### Added

- `README.md` with full setup, configuration reference, volume/model-caching
  notes, `docker-compose` example, and troubleshooting gotchas.
- `CHANGELOG.md` (this file).
- CI: native `linux/arm64` builds on `ubuntu-24.04-arm`, replacing QEMU
  emulation. The build job is now a matrix (`linux/amd64` on `ubuntu-latest`,
  `linux/arm64` on `ubuntu-24.04-arm`), with a separate `manifest` job that
  stitches the two single-arch images into one multi-arch manifest via
  `docker buildx imagetools create`.

### Changed

- Docker Hub image tags are now bare semver (`0.2.0`) instead of
  `v`-prefixed (`v0.2.0`), stripped from the git tag via
  `${GITHUB_REF_NAME#v}` in CI.
- Split the release workflow into three jobs (`validate`, `build`,
  `manifest`) instead of one, so tag validation runs once and each
  architecture builds independently.

### Fixed

- `apt-get` steps in the `Dockerfile` now set `DEBIAN_FRONTEND=noninteractive`
to prevent interactive prompts from hanging the build.
- `pip` is upgraded before installing dependencies in the `Dockerfile`.

## [0.1.0] - 2026-09-20

### Added

- Initial release: Docker image for CPU-only audio transcription using
  [faster-whisper](https://github.com/SYSTRAN/faster-whisper), replacing the
  original `mlx-whisper`-based workflow (which cannot run in a Linux
  container — no Metal/GPU passthrough).
- `transcribe.py`: CLI wrapper mirroring the original `mlx_whisper` flag
  surface (model, language, condition-on-previous-text, no-speech-threshold,
  word-timestamps, hallucination-silence-threshold, output-dir,
  output-format), with matching `WHISPER_*` environment variable defaults.
- Output writers for `txt`, `vtt`, `srt`, `tsv`, and `json`, including
  `--output-format all`.
- `Dockerfile` based on `python:3.12-slim` with `ffmpeg` and `libgomp1`,
  no PyTorch/CUDA — built image size ~1.2 GB.
- Model weights cached via `HF_HOME=/data/models`, intended to be mounted as
  a persistent volume rather than baked into the image.
- GitHub Actions workflow to build and push the image to Docker Hub on
  `vX.Y.Z` tag pushes, gated on the tag matching an ancestor commit of
  `main`.

[0.2.0]: https://github.com/repasscloud/whisper-transcribe/releases/tag/v0.2.0
[0.1.0]: https://github.com/repasscloud/whisper-transcribe/releases/tag/v0.1.0
