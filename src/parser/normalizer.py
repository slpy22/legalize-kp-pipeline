"""
normalizer.py — Raw text normalization for North Korean law PDFs.

normalize_text(text) applies a deterministic, ordered pipeline of cleaning
steps to prepare raw extracted text for downstream parsing.
"""
import re

# Hangul syllable block: U+AC00 – U+D7A3
_HANGUL_RE = re.compile(r"[\uAC00-\uD7A3]")

# Rule 1: NIS page header  e.g. "123 북한법령집 上"
_HEADER_RE = re.compile(r"^\d+\s+북한\s*법령집\s*[上下]$")

# Rule 2: NIS page footer  e.g. "조선민주주의인민공화국 로동법 45"  (< 80 chars)
_FOOTER_RE = re.compile(r"^조선민주주의인민공화국\s+.+\s+\d+$")

# Rule 3: Standalone page number  1–4 digits only
_PAGE_NUM_RE = re.compile(r"^\d{1,4}$")

# Rule 4: Tab followed by optional whitespace then newline  →  space
#   Handled via re.sub before splitting into lines
_TAB_NL_RE = re.compile(r"\t[^\S\n]*\n")

# Rule 6: Hangul-to-Hangul line join
#   Match end of one line (Hangul) + newline + start of next line (Hangul)
#   BUT do NOT join when the next line starts with a structural marker
#   (제N장, 제N조, 제N편, 제N절, 제N관, 부칙, 서문)
_HANGUL_JOIN_RE = re.compile(
    r"([\uAC00-\uD7A3])\n"
    r"(?!제\d+[장조편절관]|부\s*칙|서\s*문)"
    r"([\uAC00-\uD7A3])"
)

# Rule 4b: 줄 첫머리 구조 표지의 숫자 앞뒤 공백(전각 포함) 없애기 — 법무부 HWP 일부
#   예: "제 1 조　조선…", "제 6 조(…)", "제5 장", "제 6절" → "제1조　조선…", "제6조(…)", "제5장", "제6절"
#   (8차 #75·#77: 헌법 2010·2012, 녀성권리보장법 2010 등 — 조문·장 머리로 인식되지 않아 앞 조문에 섞였다)
_SPACED_MARKER_RE = re.compile(
    r"(?m)^([ \t　]*)제(?:[ \t　]+(\d+)[ \t　]*|(\d+)[ \t　]+)([조장절편관])"
)

# Rule 4c: 마크다운 굵게 표시로 감싼 줄 "**제163조 (…)**" → 표시만 뺀다(법무부 변환본 일부, 8차 #75)
_BOLD_LINE_RE = re.compile(r"(?m)^([ \t]*)\*\*(.+?)\*\*[ \t]*$")

# Rule 4d: 표지만 있는 줄 + 한글로 시작하는 다음 줄 → 공백으로 잇는다.
#   Rule 6(한글 줄 잇기)이 '제2조⏎이법은' 을 '제2조이법은' 으로 붙이면 '이' 가 조사로 걸러지고,
#   '제1장⏎합영법의기본' 은 '제1장합영법의기본' 이 되어 장 머리로 안 잡힌다(외국인투자법·합영법 1999).
_BARE_MARKER_NL_RE = re.compile(r"(?m)^([ \t　]*제\d+[조장절편관])[ \t　]*\n(?=[ \t　]*[가-힣])")

# Rule 9: Three or more consecutive newlines  →  two newlines
_MULTI_NL_RE = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    """Return a clean version of *text* suitable for structured parsing.

    Processing order (matches spec):
      1. Remove NIS page headers
      2. Remove NIS page footers
      3. Remove standalone page numbers
      4. Convert tab+newline to space          (before general tab handling)
      5. Convert remaining tabs to space
      6. Join broken Korean words across lines
      7. Collapse multiple spaces to one       (per line)
      8. Strip leading/trailing whitespace     (per line)
      9. Collapse 3+ newlines to 2
     10. Strip overall text
    """
    # --- Rule 4: \t followed by optional non-newline whitespace then \n → space
    text = _TAB_NL_RE.sub(" ", text)

    # --- Rules 4b, 4c: 구조 표지 공백·굵게 표시 정리 (줄 잇기 전에 해야 표지로 보호된다) ---
    text = _BOLD_LINE_RE.sub(r"\1\2", text)
    text = _SPACED_MARKER_RE.sub(lambda m: f"{m.group(1)}제{m.group(2) or m.group(3)}{m.group(4)}", text)
    text = _BARE_MARKER_NL_RE.sub(r"\1 ", text)

    # --- Rules 1, 2, 3: line-level removals ---
    lines = text.split("\n")
    kept = []
    for line in lines:
        # Rule 1: NIS page header
        if _HEADER_RE.match(line.strip()):
            continue
        # Rule 2: NIS page footer (only short lines)
        stripped = line.strip()
        if len(stripped) < 80 and _FOOTER_RE.match(stripped):
            continue
        # Rule 3: standalone page number
        if _PAGE_NUM_RE.match(stripped):
            continue
        kept.append(line)
    text = "\n".join(kept)

    # --- Rule 5: remaining tabs → space ---
    text = text.replace("\t", " ")

    # --- Rule 6: join Hangul-to-Hangul line breaks ---
    # Must iterate because matches do not overlap (consume chars between them).
    # A simple loop handles cases where multiple joins are needed sequentially.
    prev = None
    while prev != text:
        prev = text
        text = _HANGUL_JOIN_RE.sub(r"\1\2", text)

    # --- Rules 7 & 8: per-line space collapsing and stripping ---
    lines = text.split("\n")
    lines = [re.sub(r" {2,}", " ", line).strip() for line in lines]
    text = "\n".join(lines)

    # --- Rule 9: collapse 3+ newlines to 2 ---
    text = _MULTI_NL_RE.sub("\n\n", text)

    # --- Rule 10: strip overall ---
    return text.strip()
