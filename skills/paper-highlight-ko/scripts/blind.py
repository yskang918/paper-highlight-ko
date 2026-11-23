"""눈가림 독자용 파일을 만든다: PDF에 보이는 것(1분 요약 + 형광펜 번역)만, 쪽 순서로.

사용: python blind.py 작업폴더/sentences.json selections.json 출력.txt
"""
import json
import sys
from pathlib import Path


def main(sent_json, sel_json, out):
    S = json.loads(Path(sent_json).read_text(encoding="utf-8"))
    L = json.loads(Path(sel_json).read_text(encoding="utf-8"))
    lines = ["[색깔 안내] 초록 = 논문 뼈대(질문·방법·결과·시사점·한계점), 노랑 = 왜 그런 결과인지 설명", "", "[1분 요약]"]
    lines += [f"- {s['cat']}: {s['text']}" for s in L.get("summary", [])]
    items = [i for i in L["items"] if i["ids"] and i["ids"][0] in S]
    items.sort(key=lambda i: (S[i["ids"][0]]["page"], S[i["ids"][0]]["rects"][0][1], S[i["ids"][0]]["rects"][0][0]))
    lines += ["", "[형광펜 번역 — 쪽 순서]"]
    for i in items:
        col = "노랑" if i["cat"] == "핵심" else "초록"
        lines.append(f"({S[i['ids'][0]]['page'] + 1}쪽, {col}) [{i['cat']}] {i['ko']}")
    Path(out).write_text("\n".join(lines), encoding="utf-8")
    print(f"형광펜 {len(items)}개 → {out}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
