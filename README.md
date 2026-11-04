# 스포 세탁소 프로토타입

유튜브 영화 리뷰에서 감정과 평가는 남기고 스포일러만 지우는 크롬 확장과 로컬 서버입니다.
`sample_movie`는 동작 확인용 가상 영화이며, 이 데이터의 결과는 레포트 성능 근거로 쓰지 않습니다.

> **스포일러 주의:** `server/data/movies/brand_new_day.json`과 `server/data/samples/brand_new_day_smoke.csv`에는 영화 "스파이더맨: 브랜드 뉴 데이"의 전개와 결말이 들어 있습니다.

아직 프로토타입이며 스포 판단 정확도는 낮습니다. 스포를 놓치거나 평가를 스포로 잘못 가릴 수 있습니다.

## 준비

- Python 3.12에서 확인했습니다.
- `server/requirements.txt`의 패키지를 설치합니다.
- [Ollama](https://ollama.com)를 설치하고 `ollama pull exaone3.5:2.4b`로 모델을 받습니다. Ollama가 없으면 LLM 확인과 댓글 세탁 없이 동작합니다.

## 실행

```bash
cd server
.venv/Scripts/python -m uvicorn app:app --host 127.0.0.1 --port 8765
```

1. `chrome://extensions`에서 개발자 모드를 켭니다.
2. "압축해제된 확장 프로그램을 로드합니다"로 `extension` 폴더를 선택합니다.
3. 등록한 영상을 유튜브에서 엽니다.

## 데모 영화 등록

1. `server/data/movies/<영화ID>.json`에 등장인물과 사실 목록을 작성합니다. 사실의 `risk`는 `safe`, `medium`, `high` 중 하나입니다.
2. 리뷰 영상을 분석합니다.

```bash
.venv/Scripts/python ingest.py --video-id <유튜브 영상 ID> --movie <영화ID> --audio <음성 파일>
```

## 기준값 측정

정답을 표시한 `text,label` CSV로 기준값별 결과를 확인합니다.

```bash
.venv/Scripts/python evaluate.py --movie <영화ID> --labels <CSV 파일>
```

## 라이선스

직접 작성한 코드는 [MIT 라이선스](LICENSE)를 따릅니다. 다음은 MIT 적용 대상이 아닙니다.

- `server/data/movies/brand_new_day.json`: 한국어 위키백과 [스파이더맨: 브랜드 뉴 데이](https://ko.wikipedia.org/wiki/스파이더맨:_브랜드_뉴_데이)의 줄거리를 요약해 고쳐 쓴 자료로, [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/deed.ko)을 따릅니다.
- LLM 모델 `exaone3.5:2.4b`: 저장소에 포함되어 있지 않습니다. 사용 전에 [모델 페이지](https://ollama.com/library/exaone3.5)의 라이선스를 확인하세요. 비상업적 사용 조건이 있을 수 있습니다.
- 사용하는 Python 패키지와 임베딩 모델: 각자의 라이선스를 따릅니다.

SponsorBlock은 구간 건너뛰기 구조만 참고했으며 코드는 포함하지 않았습니다.
