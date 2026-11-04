"""스포 세탁소 판단 파이프라인: 임베딩으로 후보를 찾고 LLM으로 확인한 뒤 댓글을 세탁한다."""
import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path

import faiss
import httpx
import numpy as np
from presidio_analyzer import Pattern, PatternRecognizer
from sentence_transformers import SentenceTransformer

DATA_DIR = Path(__file__).parent / "data"
EMBEDDING_MODEL = "jhgan/ko-sroberta-multitask"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "exaone3.5:2.4b"

# 평가 데이터(evaluate.py)로 다시 정해야 하는 시작값
SIM_THRESHOLD = 0.45
NAME_SIM_THRESHOLD = 0.30
SEGMENT_GAP_SEC = 5.0

TOP_FACTS = 3
# 세탁한 문장은 판단 기준보다 엄격하게 검사해, 사건이 남아 있으면 고정 문구로 바꾼다
WASH_MAX_SIM = 0.35

FALLBACK_WASH = "(스포일러가 포함된 댓글이에요. 관람 후 공개)"

# 예시는 성능을 재는 영화와 섞이지 않도록 다른 가상 영화로 든다
JUDGE_SYSTEM = """너는 영화 스포일러 판별기다. 네 영화 지식은 쓰지 말고 주어진 사실만 근거로 판단한다.
댓글이 숨겨야 할 사실 속 사건, 정체, 관계, 죽음, 결말 중 하나라도 직접 말하거나 암시하면 reveals는 true다.
감정 표현이 섞여 있어도 사건을 언급하면 true다. 인물 이름이 나와도 연기, 외모, 음악, 연출에 대한 평가뿐이면 false다.

예시
숨겨야 할 사실: 민수의 형이 살인범이다
댓글: 형이 범인일 줄 몰랐다 ㅠㅠ
답: {"reason": "범인의 정체를 말함", "reveals": true}

숨겨야 할 사실: 마지막에 민수가 바다에서 죽는다
댓글: 민수 마지막 장면 보고 펑펑 울었어요 안 죽었으면
답: {"reason": "민수의 죽음을 암시함", "reveals": true}

숨겨야 할 사실: 민수의 형이 살인범이다
댓글: 민수 형 역 배우 연기 진짜 잘한다
답: {"reason": "연기 평가만 있음", "reveals": false}

반드시 {"reason": "짧은 이유", "reveals": true 또는 false} JSON으로만 답한다."""

WASH_SYSTEM = """너는 유튜브 댓글에서 영화 스포일러만 지우는 편집기다.
감정과 평가 표현은 그대로 두고, 인물 이름, 사건, 정체, 결말 정보는 모두 지운다. 새로운 내용을 지어내지 않는다.

예시
댓글: 진짜 소름이었음 ㅠㅠ 민수 형이 범인일 줄이야
답: {"washed": "진짜 소름이었음 ㅠㅠ"}

댓글: 마지막에 민수 죽을 때 펑펑 울었어요 연출 최고
답: {"washed": "펑펑 울었어요 연출 최고"}

반드시 {"washed": "다시 쓴 댓글"} JSON으로만 답한다."""

_embedder = None
_embedder_lock = threading.Lock()
_llm_lock = threading.Lock()


def get_embedder():
    global _embedder
    with _embedder_lock:
        if _embedder is None:
            _embedder = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
    return _embedder


def embed(texts):
    vectors = get_embedder().encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(vectors, dtype="float32")


def split_sentences(text):
    parts = re.split(r"(?<=[.!?…])\s+|\n+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def ask_llm(system, user):
    """Ollama가 꺼져 있으면 None을 돌려줘 호출한 쪽이 대체 동작을 고르게 한다."""
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    try:
        with _llm_lock:
            response = httpx.post(OLLAMA_URL, json=payload, timeout=180)
        response.raise_for_status()
        return json.loads(response.json()["message"]["content"])
    except (httpx.HTTPError, json.JSONDecodeError, KeyError):
        return None


@dataclass
class Verdict:
    spoiler: bool
    score: float
    fact: str | None
    method: str

    def to_dict(self):
        return {"spoiler": self.spoiler, "score": round(self.score, 3), "fact": self.fact, "method": self.method}


class MovieIndex:
    def __init__(self, movie_id):
        movie = json.loads((DATA_DIR / "movies" / f"{movie_id}.json").read_text(encoding="utf-8"))
        self.movie_id = movie_id
        self.title = movie["title"]
        self.safe = [f["text"] for f in movie["facts"] if f["risk"] == "safe"]
        self.danger = [f["text"] for f in movie["facts"] if f["risk"] != "safe"]
        self.safe_index = self._build(self.safe)
        self.danger_index = self._build(self.danger)
        patterns = [Pattern(name, re.escape(name), 1.0) for name in movie.get("characters", [])]
        self.names = PatternRecognizer(supported_entity="CHARACTER", patterns=patterns) if patterns else None

    @staticmethod
    def _build(texts):
        if not texts:
            return None
        vectors = embed(texts)
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        return index

    def _nearest(self, vector, index, texts):
        if index is None:
            return -1.0, None
        scores, ids = index.search(vector, 1)
        return float(scores[0][0]), texts[int(ids[0][0])]

    def has_character(self, text):
        return bool(self.names and self.names.analyze(text, ["CHARACTER"]))

    def candidate(self, sentence):
        """1단계: 위험한 사실에 가깝고 안전한 사실보다 더 가까운 문장만 후보로 고른다."""
        vector = embed([sentence])
        danger_score, danger_fact = self._nearest(vector, self.danger_index, self.danger)
        safe_score, _ = self._nearest(vector, self.safe_index, self.safe)
        threshold = NAME_SIM_THRESHOLD if self.has_character(sentence) else SIM_THRESHOLD
        return danger_score >= threshold and danger_score > safe_score, danger_score, danger_fact

    def nearest_facts(self, sentence):
        _, ids = self.danger_index.search(embed([sentence]), min(TOP_FACTS, len(self.danger)))
        return [self.danger[int(i)] for i in ids[0]]

    def judge_sentence(self, sentence, use_llm=True):
        is_candidate, score, fact = self.candidate(sentence)
        if not is_candidate:
            return Verdict(False, score, None, "embedding")
        if not use_llm:
            return Verdict(True, score, fact, "embedding")
        facts = "\n".join(f"- {f}" for f in self.nearest_facts(sentence))
        answer = ask_llm(JUDGE_SYSTEM, f"숨겨야 할 사실:\n{facts}\n댓글: {sentence}")
        if answer is None or "reveals" not in answer:
            return Verdict(True, score, fact, "embedding-only")
        return Verdict(answer["reveals"] is True, score, fact, "llm")

    def judge_text(self, text, use_llm=True):
        verdicts = [self.judge_sentence(s, use_llm) for s in split_sentences(text)]
        spoilers = [v for v in verdicts if v.spoiler]
        if spoilers:
            return max(spoilers, key=lambda v: v.score)
        return max(verdicts, key=lambda v: v.score, default=Verdict(False, 0.0, None, "empty"))

    def wash(self, text):
        """감정과 평가만 남기고, 결과가 조금이라도 위험하면 고정 문구로 바꾼다."""
        answer = ask_llm(WASH_SYSTEM, f"댓글: {text}")
        washed = (answer or {}).get("washed")
        if not isinstance(washed, str) or not washed.strip():
            return FALLBACK_WASH
        washed = washed.strip()
        danger_score, _ = self._nearest(embed([washed]), self.danger_index, self.danger)
        if self.has_character(washed) or danger_score >= WASH_MAX_SIM:
            return FALLBACK_WASH
        return washed

    def check_comment(self, text):
        verdict = self.judge_text(text)
        return {**verdict.to_dict(), "washed": self.wash(text) if verdict.spoiler else None}

    def find_segments(self, transcript, use_llm=True):
        """스포로 판단한 받아쓰기 문장을 가까운 것끼리 묶어 건너뛸 구간으로 만든다."""
        segments = []
        for line in transcript:
            verdict = self.judge_sentence(line["text"], use_llm)
            if not verdict.spoiler:
                continue
            if segments and line["start"] - segments[-1]["end"] <= SEGMENT_GAP_SEC:
                segments[-1]["end"] = line["end"]
                segments[-1]["facts"].append(verdict.fact)
            else:
                segments.append({"start": line["start"], "end": line["end"], "facts": [verdict.fact]})
        return segments


_movies = {}
_movies_lock = threading.Lock()


def get_movie(movie_id):
    with _movies_lock:
        if movie_id not in _movies:
            _movies[movie_id] = MovieIndex(movie_id)
        return _movies[movie_id]
