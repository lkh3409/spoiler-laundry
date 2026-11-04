"""리뷰 영상을 미리 분석해 data/videos/<video_id>.json 으로 저장한다.

사용 예:
  python ingest.py --video-id abc123 --movie sample_movie --audio review.m4a
  python ingest.py --video-id abc123 --movie sample_movie --transcript transcript.json
"""
import argparse
import json

from pipeline import DATA_DIR, get_movie


def transcribe(audio_path, model_size):
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    lines, _ = model.transcribe(audio_path, language="ko", vad_filter=True)
    return [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()} for s in lines]


def chunk_transcript(lines, chunk_sec):
    """문장 부호 없이 겹치는 자동 자막을 일정 길이로 묶어 판단 단위를 만든다."""
    lines = [l for l in lines if not l["text"].startswith("[")]
    chunks = []
    for line in lines:
        if chunks and line["start"] - chunks[-1]["start"] < chunk_sec:
            chunks[-1]["text"] += " " + line["text"]
            chunks[-1]["end"] = line["start"]
        else:
            if chunks:
                chunks[-1]["end"] = line["start"]
            chunks.append({"start": line["start"], "end": line["end"], "text": line["text"]})
    return chunks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--movie", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--audio")
    source.add_argument("--transcript")
    parser.add_argument("--whisper-model", default="small")
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--chunk-sec", type=float, help="자동 자막을 이 길이(초)로 묶는다")
    args = parser.parse_args()

    if args.audio:
        transcript = transcribe(args.audio, args.whisper_model)
    else:
        with open(args.transcript, encoding="utf-8") as f:
            transcript = json.load(f)
    if args.chunk_sec:
        transcript = chunk_transcript(transcript, args.chunk_sec)

    segments = get_movie(args.movie).find_segments(transcript, use_llm=not args.no_llm)
    out_dir = DATA_DIR / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.video_id}.json"
    payload = {"movie_id": args.movie, "transcript": transcript, "segments": segments}
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"문장 {len(transcript)}개, 스포 구간 {len(segments)}개 -> {out_path}")
    for segment in segments:
        print(f"  {segment['start']:.1f}s ~ {segment['end']:.1f}s")


if __name__ == "__main__":
    main()
