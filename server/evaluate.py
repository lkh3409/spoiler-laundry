"""직접 정답을 표시한 CSV(text,label)로 기준값별 잡은 스포와 잘못 가린 문장을 잰다. label: 1=스포, 0=안전

tune 데이터로 기준값을 고른 뒤, test 데이터에는 --threshold로 그 값 하나만 적용한다.
"""
import argparse
import csv

import pipeline

NAME_THRESHOLD_GAP = 0.15
DEFAULT_THRESHOLDS = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]


def measure(movie, rows, threshold, use_llm):
    pipeline.SIM_THRESHOLD = threshold
    pipeline.NAME_SIM_THRESHOLD = threshold - NAME_THRESHOLD_GAP
    missed, false_alarms = [], []
    tp = 0
    for text, label in rows:
        predicted = movie.judge_text(text, use_llm=use_llm).spoiler
        if predicted and label == 1:
            tp += 1
        elif predicted:
            false_alarms.append(text)
        elif label == 1:
            missed.append(text)
    return tp, missed, false_alarms


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--movie", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--llm", action="store_true", help="LLM 확인까지 함께 돌린다 (느림)")
    parser.add_argument("--threshold", type=float, help="이 기준값 하나만 측정하고 틀린 문장을 보여 준다")
    args = parser.parse_args()

    with open(args.labels, encoding="utf-8-sig", newline="") as f:
        all_rows = list(csv.DictReader(f))
    rows = [(r["text"], int(r["label"])) for r in all_rows if r["label"].strip()]
    skipped = [r["text"] for r in all_rows if not r["label"].strip()]
    print(f"측정 {len(rows)}개 (스포 {sum(l for _, l in rows)}개), 정답 없어 제외 {len(skipped)}개")
    for text in skipped:
        print("  제외:", text[:60])

    movie = pipeline.get_movie(args.movie)
    print("기준값  잡은스포  놓친스포  오탐  정확도(precision)  재현율(recall)")
    for threshold in [args.threshold] if args.threshold else DEFAULT_THRESHOLDS:
        tp, missed, false_alarms = measure(movie, rows, threshold, args.llm)
        precision = tp / (tp + len(false_alarms)) if tp + len(false_alarms) else 0.0
        recall = tp / (tp + len(missed)) if tp + len(missed) else 0.0
        print(f"{threshold:<7.2f} {tp:<9} {len(missed):<9} {len(false_alarms):<5} {precision:<18.2f} {recall:.2f}")

    if args.threshold:
        for text in missed:
            print("놓침:", text[:80])
        for text in false_alarms:
            print("오탐:", text[:80])


if __name__ == "__main__":
    main()
