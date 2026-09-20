#!/usr/bin/env python3
"""CLI wrapper around faster-whisper that mimics mlx_whisper's CLI surface
(same flags, same --output-format all behaviour) so it can be dropped into
a Docker ENTRYPOINT with sane defaults, all overridable via flags or env vars.
"""
import argparse
import json
import os
import sys
from pathlib import Path

from faster_whisper import WhisperModel


def str2bool(v: str) -> bool:
    if isinstance(v, bool):
        return v
    if v.lower() in ("true", "1", "yes", "y"):
        return True
    if v.lower() in ("false", "0", "no", "n"):
        return False
    raise argparse.ArgumentTypeError(f"invalid boolean value: {v!r}")


def env_default(name: str, default: str) -> str:
    return os.environ.get(name, default)


def fmt_timestamp(seconds: float, always_include_hours: bool = True, decimal_marker: str = ",") -> str:
    assert seconds >= 0
    ms = round(seconds * 1000.0)
    hours = ms // 3_600_000
    ms -= hours * 3_600_000
    minutes = ms // 60_000
    ms -= minutes * 60_000
    secs = ms // 1_000
    ms -= secs * 1_000
    hours_marker = f"{hours:02d}:" if always_include_hours or hours > 0 else ""
    return f"{hours_marker}{minutes:02d}:{secs:02d}{decimal_marker}{ms:03d}"


def write_txt(segments, f):
    for seg in segments:
        f.write(seg["text"].strip() + "\n")


def write_vtt(segments, f):
    f.write("WEBVTT\n\n")
    for seg in segments:
        start = fmt_timestamp(seg["start"], always_include_hours=False, decimal_marker=".")
        end = fmt_timestamp(seg["end"], always_include_hours=False, decimal_marker=".")
        f.write(f"{start} --> {end}\n{seg['text'].strip()}\n\n")


def write_srt(segments, f):
    for i, seg in enumerate(segments, start=1):
        start = fmt_timestamp(seg["start"], always_include_hours=True, decimal_marker=",")
        end = fmt_timestamp(seg["end"], always_include_hours=True, decimal_marker=",")
        f.write(f"{i}\n{start} --> {end}\n{seg['text'].strip()}\n\n")


def write_tsv(segments, f):
    f.write("start\tend\ttext\n")
    for seg in segments:
        f.write(f"{round(seg['start'] * 1000)}\t{round(seg['end'] * 1000)}\t{seg['text'].strip()}\n")


def write_json(result, f):
    json.dump(result, f, indent=2, ensure_ascii=False)


WRITERS = {"txt": write_txt, "vtt": write_vtt, "srt": write_srt, "tsv": write_tsv}


def main():
    p = argparse.ArgumentParser(description="Transcribe audio with faster-whisper (CPU)")
    p.add_argument("audio", help="Path to input audio file")
    p.add_argument("--model", default=env_default("WHISPER_MODEL", "large-v3-turbo"),
                   help="faster-whisper / CTranslate2 model name or local path")
    p.add_argument("--language", default=env_default("WHISPER_LANGUAGE", "en"),
                   help="Language code, or 'auto' to detect")
    p.add_argument("--compute-type", default=env_default("WHISPER_COMPUTE_TYPE", "int8"),
                   help="int8 | int8_float32 | float32 | float16 (CPU: use int8 or int8_float32)")
    p.add_argument("--cpu-threads", type=int, default=int(env_default("WHISPER_CPU_THREADS", "0")),
                   help="0 = let ctranslate2 pick")
    p.add_argument("--condition-on-previous-text", type=str2bool,
                   default=str2bool(env_default("WHISPER_CONDITION_ON_PREVIOUS_TEXT", "False")))
    p.add_argument("--no-speech-threshold", type=float,
                   default=float(env_default("WHISPER_NO_SPEECH_THRESHOLD", "0.4")))
    p.add_argument("--word-timestamps", type=str2bool,
                   default=str2bool(env_default("WHISPER_WORD_TIMESTAMPS", "True")))
    p.add_argument("--hallucination-silence-threshold", type=float,
                   default=float(env_default("WHISPER_HALLUCINATION_SILENCE_THRESHOLD", "1.5")))
    p.add_argument("--vad-filter", type=str2bool, default=str2bool(env_default("WHISPER_VAD_FILTER", "True")))
    p.add_argument("--beam-size", type=int, default=int(env_default("WHISPER_BEAM_SIZE", "5")))
    p.add_argument("--output-dir", default=env_default("WHISPER_OUTPUT_DIR", "/data/transcript"))
    p.add_argument("--output-format", default=env_default("WHISPER_OUTPUT_FORMAT", "all"),
                   choices=["txt", "vtt", "srt", "tsv", "json", "all"])
    args = p.parse_args()

    audio_path = Path(args.audio)
    if not audio_path.is_file():
        sys.exit(f"error: input audio not found: {audio_path}")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    language = None if args.language.lower() == "auto" else args.language

    print(f"[transcribe] loading model={args.model} compute_type={args.compute_type}", file=sys.stderr)
    model = WhisperModel(
        args.model,
        device="cpu",
        compute_type=args.compute_type,
        cpu_threads=args.cpu_threads,
    )

    seg_iter, info = model.transcribe(
        str(audio_path),
        language=language,
        beam_size=args.beam_size,
        condition_on_previous_text=args.condition_on_previous_text,
        no_speech_threshold=args.no_speech_threshold,
        word_timestamps=args.word_timestamps,
        hallucination_silence_threshold=args.hallucination_silence_threshold,
        vad_filter=args.vad_filter,
    )

    print(f"[transcribe] detected language={info.language} prob={info.language_probability:.2f}", file=sys.stderr)

    segments = []
    for seg in seg_iter:
        words = None
        if seg.words:
            words = [
                {"start": w.start, "end": w.end, "word": w.word, "probability": w.probability}
                for w in seg.words
            ]
        segments.append({
            "id": seg.id,
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
            "words": words,
        })
        print(f"[{fmt_timestamp(seg.start)} --> {fmt_timestamp(seg.end)}] {seg.text.strip()}", file=sys.stderr)

    result = {
        "text": "".join(s["text"] for s in segments).strip(),
        "segments": segments,
        "language": info.language,
    }

    stem = audio_path.stem
    formats = list(WRITERS.keys()) + ["json"] if args.output_format == "all" else [args.output_format]

    for fmt in formats:
        out_path = out_dir / f"{stem}.{fmt}"
        with open(out_path, "w", encoding="utf-8") as f:
            if fmt == "json":
                write_json(result, f)
            else:
                WRITERS[fmt](segments, f)
        print(f"[transcribe] wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
