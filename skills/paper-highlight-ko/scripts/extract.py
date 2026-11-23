"""PDF에서 문장과 그 위치(줄 단위 사각형)를 뽑는다.

사용: python extract.py 논문.pdf 작업폴더
결과: 작업폴더/sentences.json (위치), 작업폴더/sentences.txt (Claude가 읽을 본문)
"""
import json
import re
import sys
from pathlib import Path

import pymupdf

ABBREV = {"e.g", "i.e", "et al", "al", "vs", "fig", "figs", "eq", "no", "cf", "etc",
          "dr", "mr", "ms", "prof", "approx", "vol", "pp", "p", "ed", "eds", "resp"}


REF_HEAD = re.compile(r"^(references|reference list|bibliography|works cited|literature cited)$", re.I)


def block_chars(block):
    """블록의 글자와 글자별 (bbox, 줄번호)를 이어 붙인다. 줄 끝 하이픈은 합친다."""
    text, boxes = [], []
    lines = block["lines"]
    for li, line in enumerate(lines):
        chars = [c for s in line["spans"] for c in s["chars"]]
        if not chars:
            continue
        line_txt = "".join(c["c"] for c in chars)
        if text:
            prev = "".join(text).rstrip()
            if prev.endswith(("-", "­")) and line_txt.lstrip()[:1].islower():
                # 하이픈으로 끊긴 단어: 하이픈 지우고 붙이기
                while text and text[-1] in " -­":
                    text.pop(); boxes.pop()
            elif text[-1] != " ":
                text.append(" "); boxes.append(None)
        for c in chars:
            if c["c"] == "­" and c is not chars[-1]:
                continue
            if c["c"] == " " and text and text[-1] in " ­":
                continue
            text.append(c["c"]); boxes.append((tuple(c["bbox"]), li))
    return "".join(text), boxes


def split_sentences(txt):
    """문장 경계(끝 위치) 목록."""
    ends = []
    for m in re.finditer(r"[.?!][\"”’)\]]?(?=\s+[\"“(\[]?[A-Z0-9])", txt):
        before = txt[:m.start()]
        word = re.search(r"([A-Za-z.]+)$", before)
        w = (word.group(1) if word else "").lower().rstrip(".")
        if w in ABBREV or (len(w) == 1 and w.isalpha()):
            continue
        ends.append(m.end())
    ends.append(len(txt))
    out, start = [], 0
    for e in ends:
        seg = txt[start:e]
        if seg.strip():
            s = start + (len(seg) - len(seg.lstrip()))
            out.append((s, e))
        start = e
    return out


def line_rects(boxes):
    """글자 bbox들을 줄 단위 사각형으로 합친다."""
    rects = {}
    for b in boxes:
        if b is None:
            continue
        (x0, y0, x1, y1), li = b
        if li in rects:
            r = rects[li]
            rects[li] = [min(r[0], x0), min(r[1], y0), max(r[2], x1), max(r[3], y1)]
        else:
            rects[li] = [x0, y0, x1, y1]
    return [rects[k] for k in sorted(rects)]


def main(pdf, outdir):
    out = Path(outdir); out.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(pdf)
    data, lines_txt, n = {}, [], 0
    stop = False
    for pno, page in enumerate(doc):
        if stop:
            break
        lines_txt.append(f"\n===== {pno + 1}쪽 =====")
        raw = page.get_text("rawdict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)
        for block in raw["blocks"]:
            if block.get("type") != 0:
                continue
            txt, boxes = block_chars(block)
            if not txt.strip():
                continue
            if REF_HEAD.match(txt.strip()):
                stop = True  # 참고문헌부터는 뽑지 않음
                break
            sizes = [s["size"] for l in block["lines"] for s in l["spans"]]
            size = round(max(sizes), 1) if sizes else 0
            parts = []
            for s, e in split_sentences(txt):
                seg = txt[s:e].strip()
                n += 1
                sid = f"S{n}"
                data[sid] = {"page": pno, "text": seg, "rects": line_rects(boxes[s:e])}
                parts.append(f"[{sid}] {seg}")
            lines_txt.append(f"\n(글자 {size})\n" + "\n".join(parts))
    (out / "sentences.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (out / "sentences.txt").write_text("\n".join(lines_txt), encoding="utf-8")
    print(f"{doc.page_count}쪽, 문장 {n}개 → {out}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
