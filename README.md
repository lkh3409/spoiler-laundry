# 스포 세탁소 프로토타입

유튜브 영화 리뷰에서 감정과 평가는 남기고 스포일러만 지우는 크롬 확장과 로컬 서버입니다.
`sample_movie`는 동작 확인용 가상 영화이며, 이 데이터의 결과는 레포트 성능 근거로 쓰지 않습니다.

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
