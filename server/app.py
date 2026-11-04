"""크롬 확장에 판단 결과를 전달하는 로컬 서버. 내 컴퓨터(127.0.0.1)에서만 연다."""
import json
import threading

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from pipeline import DATA_DIR, get_movie

app = FastAPI(title="스포 세탁소")

CACHE_PATH = DATA_DIR / "comment_cache.json"
_cache_lock = threading.Lock()
_cache = json.loads(CACHE_PATH.read_text(encoding="utf-8")) if CACHE_PATH.exists() else {}


class CommentRequest(BaseModel):
    text: str


def load_video(video_id):
    path = DATA_DIR / "videos" / f"{video_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/videos/{video_id}")
def video(video_id: str):
    data = load_video(video_id)
    if data is None:
        raise HTTPException(404, "등록되지 않은 영상")
    return {"movie_id": data["movie_id"], "segments": data["segments"]}


@app.post("/api/videos/{video_id}/comments")
def check_comment(video_id: str, request: CommentRequest):
    data = load_video(video_id)
    if data is None:
        raise HTTPException(404, "등록되지 않은 영상")
    text = " ".join(request.text.split())
    key = f"{data['movie_id']}:{text}"
    with _cache_lock:
        if key in _cache:
            return _cache[key]
    result = get_movie(data["movie_id"]).check_comment(text)
    # LLM 없이 낸 임시 결과는 저장하지 않아, Ollama를 켠 뒤 다시 판단하게 한다
    if result["method"] != "embedding-only":
        with _cache_lock:
            _cache[key] = result
            CACHE_PATH.write_text(json.dumps(_cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return result
