"""형광펜 + 오른쪽 번역 칸이 붙은 PDF를 만든다.

사용: python render.py 논문.pdf 작업폴더/sentences.json selections.json [출력.pdf]
출력을 생략하면 원본 옆에 '원본이름_형광펜.pdf'로 저장한다. 원본은 건드리지 않는다.

selections.json 형식:
{
  "summary": [{"cat": "연구 목적", "text": "...", "ids": ["S53"]}, ...],
  "items":   [{"ids": ["S49"], "cat": "연구 목적", "ko": "번역"}, ...]   # cat == "핵심"이면 노랑
}
"""
import json
import sys
from pathlib import Path

import pymupdf

import os


def _find_font(cands):
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


# 한글 글꼴: 윈도우 맑은 고딕 → 맥 애플고딕 → 리눅스 나눔·Noto → 없으면 PyMuPDF 내장 한글 글꼴
FONT_REG = _find_font([os.environ.get("PHK_FONT"),
                       "C:/Windows/Fonts/malgun.ttf",
                       "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
                       "/Library/Fonts/NanumGothic.ttf",
                       "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
                       "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                       "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"])
FONT_BOLD = _find_font([os.environ.get("PHK_FONT_BOLD"),
                        "C:/Windows/Fonts/malgunbd.ttf",
                        "/Library/Fonts/NanumGothicBold.ttf",
                        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
                        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
                        "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc"]) or FONT_REG
GREEN, GREEN_INK = (0.55, 0.88, 0.55), (0.10, 0.45, 0.18)
YELLOW, YELLOW_INK = (1.0, 0.88, 0.25), (0.62, 0.42, 0.0)
INK, MUTED = (0.12, 0.12, 0.14), (0.45, 0.45, 0.5)
FS_MAX, FS_MIN, LH, PAD, GAP = 11.0, 7.5, 1.38, 5, 6   # 번역 글씨: 쪽마다 겹치지 않는 가장 큰 크기
COL_RATIO = 0.6   # 번역 칸 폭 = 원래 페이지 폭의 60%
LEGEND = [(GREEN, "초록 = 논문 뼈대(질문·방법·결과·시사점·한계점) → 이것만 읽기"),
          (YELLOW, "노랑 = 왜 그런 결과인지 설명 → 궁금할 때만 보기")]
LEGEND_H = 30
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"

reg = pymupdf.Font(fontfile=FONT_REG) if FONT_REG else pymupdf.Font("korea")
bold = pymupdf.Font(fontfile=FONT_BOLD) if FONT_BOLD else reg


def _insert_fonts(page):
    """페이지에 한글 글꼴 등록(파일이 없으면 내장 'korea' 글꼴)."""
    if FONT_REG:
        page.insert_font(fontname="mg", fontfile=FONT_REG)
        page.insert_font(fontname="mgb", fontfile=FONT_BOLD or FONT_REG)
    else:
        page.insert_font(fontname="mg", fontbuffer=reg.buffer)
        page.insert_font(fontname="mgb", fontbuffer=reg.buffer)


def clean(text):
    """한글 글꼴에 없는 글자 바꾸기: x̄(결합 윗줄) → M (APA 평균 표기)."""
    return text.replace("x̄", "M").replace("̄", "")


def wrap(text, font, size, width):
    """한글·영어 섞인 글을 폭에 맞게 줄바꿈.
    띄어쓰기 > '·' ',' 뒤 > 글자 단위 순으로 끊는다(통계값이 줄 중간에서 잘리지 않게)."""
    import re
    text = clean(text)
    lines = []
    for para in text.split("\n"):
        # (조각, 앞에 띄어쓰기 있음?) 목록
        toks = []
        for wi, word in enumerate(para.split(" ")):
            for pi, piece in enumerate(re.split(r"(?<=[·,])", word)):
                if piece:
                    toks.append((piece, wi > 0 and pi == 0))
        cur = ""
        for piece, sp in toks:
            cand = (cur + (" " if sp and cur else "") + piece) if cur else piece
            if font.text_length(cand, size) <= width:
                cur = cand
                continue
            if cur:
                lines.append(cur)
            cur = ""
            for ch in piece:
                if font.text_length(cur + ch, size) > width and cur:
                    lines.append(cur); cur = ch
                else:
                    cur += ch
        lines.append(cur)
    return lines


class Note:
    def __init__(self, label, body, ink, want_y, anchor=None, width=0, extra=None, fs=FS_MAX):
        self.label, self.ink, self.want, self.anchor, self.fs = label, ink, want_y, anchor, fs
        FS = fs
        inner = width - 2 * PAD - 4
        self.rows = [(label, bold, ink)] if label else []
        for lab, txt in (extra or []):   # 요약: (소제목, 내용) 여러 개
            self.rows.append(("", reg, INK))
            self.rows.append((lab, bold, ink))
            self.rows += [(l, reg, INK) for l in wrap(txt, reg, FS, inner)]
        if body:
            self.rows += [(l, reg, INK) for l in wrap(body, reg, FS, inner)]
        self.h = len(self.rows) * FS * LH + 2 * PAD
        self.y = want_y


def layout(notes, top, bottom):
    notes.sort(key=lambda n: n.want)
    y = top
    for n in notes:
        n.y = max(n.want, y)
        y = n.y + n.h + GAP
    limit = bottom
    for n in reversed(notes):
        if n.y + n.h > limit:
            n.y = limit - n.h
        limit = n.y - GAP
    if notes and notes[0].y < top:   # 너무 많아 넘치면 위에서부터 다시 쌓기(겹침 허용 안 함)
        y = top
        for n in notes:
            n.y = y; y += n.h + GAP


def main(pdf, sent_json, sel_json, out=None):
    sents = json.loads(Path(sent_json).read_text(encoding="utf-8"))
    sel = json.loads(Path(sel_json).read_text(encoding="utf-8"))
    src = Path(pdf)
    out = Path(out) if out else src.with_name(src.stem + "_형광펜.pdf")
    doc = pymupdf.open(pdf)

    per_page = {}
    for it in sel["items"]:
        ids = [i for i in it["ids"] if i in sents]
        if not ids:
            print("문장 번호 없음:", it["ids"]); continue
        first_page = sents[ids[0]]["page"]
        # 걸친 쪽마다 등록: 첫 쪽엔 번역, 뒤쪽엔 '이어짐' 칸
        for pg in sorted({sents[i]["page"] for i in ids}):
            per_page.setdefault(pg, []).append((it, [i for i in ids if sents[i]["page"] == pg], first_page))

    for pno, page in enumerate(doc):
        if page.rotation:
            page.set_rotation(0)
        mb = page.mediabox
        W, H = page.rect.width, page.rect.height
        M = round(W * COL_RATIO)
        page.set_mediabox(pymupdf.Rect(mb.x0, mb.y0, mb.x1 + M, mb.y1))
        col_x0, col_x1 = W + 12, W + M - 12
        width = col_x1 - col_x0

        # 번역 칸 바탕
        sh = page.new_shape()
        sh.draw_rect(pymupdf.Rect(W, 0, W + M, H)); sh.finish(fill=(0.955, 0.958, 0.965), color=None)
        sh.draw_line((W, 0), (W, H)); sh.finish(color=(0.82, 0.83, 0.86), width=0.6)
        # 색깔 안내 띠 (모든 쪽 맨 위)
        lg = pymupdf.Rect(col_x0, 8, col_x1, 8 + LEGEND_H)
        sh.draw_rect(lg); sh.finish(fill=(1, 1, 1), color=(0.85, 0.86, 0.88), width=0.5)
        for k, (col, _) in enumerate(LEGEND):
            y = lg.y0 + 6 + k * 12
            sh.draw_rect(pymupdf.Rect(lg.x0 + 6, y, lg.x0 + 20, y + 8)); sh.finish(fill=col, color=None)
        sh.commit()

        page_rects = [r for s in sents.values() if s["page"] == pno for r in s["rects"]]
        text_right = max((r[2] for r in page_rects), default=W - 40) + 4

        specs = []   # (label, body, ink, want, anchor, badge, extra)
        if pno == 0 and sel.get("summary"):
            extra = []
            for s in sel["summary"]:
                pages = sorted({sents[i]["page"] + 1 for i in s.get("ids", []) if i in sents})
                tag = f" ({'·'.join(map(str, pages))}쪽)" if pages else ""
                extra.append((s["cat"] + tag, s["text"]))
            specs.append(("1분 요약", "", INK, 24, None, None, extra))

        for it, ids, first_page in per_page.get(pno, []):
            hot = it["cat"] == "핵심"
            color, ink = (YELLOW, YELLOW_INK) if hot else (GREEN, GREEN_INK)
            first, all_rects = None, []
            for sid in ids:
                s = sents[sid]
                rects = [pymupdf.Rect(r) for r in s["rects"]]
                a = page.add_highlight_annot(quads=[r.quad for r in rects])
                a.set_colors(stroke=color)
                a.set_info(title="논문 형광펜", content=f"[{it['cat']}] {it['ko']}")
                a.update()
                if s["page"] == pno:
                    all_rects += rects
                    if first is None:
                        first = rects[0]
            body = it["ko"] if pno == first_page else f"(앞 {first_page + 1}쪽 번역에 이어짐)"
            anchor = badge = None
            if first:
                ymid = (first.y0 + first.y1) / 2
                badge = (min(r.x0 for r in all_rects) - 7, ymid)
                # 오른쪽 끝 단(또는 한 단) 문장일 때만 연결선: 선이 다른 글을 가로지르지 않게
                if max(r.x1 for r in all_rects) > text_right - 30:
                    anchor = (text_right, ymid)
            specs.append((f"[{it['cat']}]", body, ink, (first.y0 - 3) if first else 40, anchor, badge, None))

        # 겹치지 않고 쪽 안에 다 들어가는 가장 큰 글씨 고르기
        top, bottom = 8 + LEGEND_H + 8, H - 18
        fs = FS_MAX
        while True:
            notes = []
            for lab, body, ink, want, anchor, badge, extra in specs:
                n = Note(lab, body, ink, want, anchor, width, extra, fs)
                n.badge = badge
                notes.append(n)
            need = sum(n.h for n in notes) + GAP * max(len(notes) - 1, 0)
            if need <= bottom - top or fs <= FS_MIN:
                break
            fs = round(fs - 0.25, 2)
        if need > bottom - top:
            print(f"{pno + 1}쪽: 가장 작은 글씨로도 칸이 넘침 — 형광펜이 너무 많음")
        layout(notes, top, bottom)
        num = 0
        for n in notes:
            if getattr(n, "badge", None):
                num += 1
                n.num = num
                n.rows[0] = (f"{CIRCLED[num - 1] if num <= len(CIRCLED) else num}  {n.rows[0][0]}",) + n.rows[0][1:]

        sh = page.new_shape()
        for n in notes:
            box = pymupdf.Rect(col_x0, n.y, col_x1, n.y + n.h)
            sh.draw_rect(box); sh.finish(fill=(1, 1, 1), color=(0.85, 0.86, 0.88), width=0.5)
            sh.draw_rect(pymupdf.Rect(col_x0, n.y, col_x0 + 3, n.y + n.h)); sh.finish(fill=n.ink, color=None)
            if getattr(n, "badge", None):
                bx, by = n.badge
                sh.draw_circle((bx, by), 5.2); sh.finish(fill=n.ink, color=(1, 1, 1), width=0.6)
            if n.anchor:
                ax, ay = n.anchor
                ty = n.y + PAD + n.fs * 0.7
                sh.draw_circle((ax, ay), 1.6); sh.finish(fill=n.ink, color=None)
                sh.draw_polyline([(ax, ay), (W + 4, ay), (col_x0, ty)])
                sh.finish(color=n.ink, width=0.5, stroke_opacity=0.7, closePath=False)
        sh.commit()

        _insert_fonts(page)
        lfs = min([7.6] + [7.6 * (width - 32) / reg.text_length(t, 7.6) for _, t in LEGEND])
        for n in notes:
            if getattr(n, "num", None):
                bx, by = n.badge
                t = str(n.num)
                tw = pymupdf.get_text_length(t, "hebo", 6.2)
                page.insert_text((bx - tw / 2, by + 2.2), t, fontname="hebo", fontsize=6.2, color=(1, 1, 1))
        for k, (_, txt) in enumerate(LEGEND):
            page.insert_text((col_x0 + 25, 8 + 6 + k * 12 + 7), txt, fontname="mg", fontsize=lfs, color=INK)
        for n in notes:
            y = n.y + PAD + n.fs
            for txt, font, color in n.rows:
                page.insert_text((col_x0 + PAD + 4, y), txt, fontname="mgb" if font is bold else "mg",
                                 fontsize=n.fs, color=color)
                y += n.fs * LH

    try:
        doc.save(out, garbage=3, deflate=True)
    except Exception:
        # 같은 이름 파일이 PDF 보기 프로그램에 열려 있으면 덮어쓸 수 없음 → 새 이름으로 저장
        out = out.with_name(out.stem + "_새판.pdf")
        doc.save(out, garbage=3, deflate=True)
        print("원래 파일이 열려 있어 새 이름으로 저장함")
    print("저장:", out)


if __name__ == "__main__":
    main(*sys.argv[1:5])
