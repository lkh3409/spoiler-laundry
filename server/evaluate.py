"""직접 정답을 표시한 CSV(text,label)로 기준값별 잡은 스포와 잘못 가린 문장을 잰다. label: 1=스포, 0=안전"""
import argparse
import csv

import pipeline


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--movie", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--llm", action="store_true", help="기준값마다 LLM 확인까지 함께 돌린다 (느림)")
    args = parser.parse_args()

    with open(args.labels, encoding="utf-8-sig", newline="") as f:
        rows = [(r["text"], int(r["label"])) for r in csv.DictReader(f)]

    movie = pipeline.get_movie(args.movie)
    print("기준값  잡은스포  놓친스포  오탐  정확도(precision)  재현율(recall)")
    for threshold in [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]:
        pipeline.SIM_THRESHOLD = threshold
        pipeline.NAME_SIM_THRESHOLD = threshold - 0.15
        tp = fp = fn = 0
        for text, label in rows:
            predicted = movie.judge_text(text, use_llm=args.llm).spoiler
            tp += predicted and label == 1
            fp += predicted and label == 0
            fn += (not predicted) and label == 1
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        print(f"{threshold:<7.2f} {tp:<9} {fn:<9} {fp:<5} {precision:<18.2f} {recall:.2f}")


if __name__ == "__main__":
    main()
