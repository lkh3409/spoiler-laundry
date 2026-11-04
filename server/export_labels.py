"""모은 댓글을 정답 표시용 CSV 두 개로 나눈다. 다시 실행해도 이미 표시한 정답은 유지한다.

tune: 모델 판단을 채워 두어 틀린 것만 고치면 되는 기준값 조정용
test: 모델 판단에 끌리지 않도록 비워 둔 최종 측정용
label: 1=스포, 0=안전
"""
import argparse
import csv
import hashlib

from pipeline import DATA_DIR, get_movie


def group_of(text):
    """파일을 다시 만들어도 댓글이 다른 쪽으로 옮겨 가지 않도록 내용으로 나눈다."""
    return "tune" if hashlib.md5(text.encode("utf-8")).digest()[0] % 2 == 0 else "test"


def read_labels(path):
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {row["text"]: row["label"] for row in csv.DictReader(f)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--movie", required=True)
    args = parser.parse_args()

    comments = (DATA_DIR / "comments" / f"{args.movie}.txt").read_text(encoding="utf-8").splitlines()
    movie = get_movie(args.movie)
    out_dir = DATA_DIR / "labels"
    out_dir.mkdir(exist_ok=True)

    for group in ("tune", "test"):
        path = out_dir / f"{args.movie}_{group}.csv"
        existing = read_labels(path)
        rows = [c for c in comments if group_of(c) == group]
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["text", "label"])
            for text in rows:
                label = existing.get(text, "")
                if not label and group == "tune":
                    label = "1" if movie.judge_text(text).spoiler else "0"
                writer.writerow([text, label])
        print(f"{path}: {len(rows)}개")


if __name__ == "__main__":
    main()
