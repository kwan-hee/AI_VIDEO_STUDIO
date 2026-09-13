#!/usr/bin/env python3
"""post.json -> 네이버 블로그 복붙용 본문(.txt) + 완성형 HTML(.html)

두 결과물을 같은 데이터에서 만들기 때문에 내용이 어긋나지 않는다.

사용법:
    python3 build_post.py post.json --outdir outputs/
"""

import argparse
import html
import json
import re
import sys
from datetime import date
from pathlib import Path

REQUIRED_TOP = ["book", "titles", "meta", "body"]
BLOCK_TYPES = {"p", "h3", "quote", "callout", "image", "info", "divider"}


# ---------------------------------------------------------------- 검증

def fail(msg):
    print(f"[오류] {msg}", file=sys.stderr)
    sys.exit(1)


def validate(data):
    for key in REQUIRED_TOP:
        if key not in data:
            fail(f"'{key}' 항목이 없습니다. book(도서 정보), titles(제목 후보), "
                 f"meta(메타 정보), body(본문 블록)는 모두 필요합니다.")

    book = data["book"]
    if not book.get("title"):
        fail("book.title(책 제목)이 비어 있습니다.")
    if not book.get("author"):
        fail("book.author(저자)가 비어 있습니다.")

    titles = data["titles"]
    options = titles.get("options") or []
    if len(options) < 3:
        fail("titles.options에 제목 후보 3개가 필요합니다. "
             "정보형·질문형·대비형으로 각각 하나씩 작성합니다.")
    rec = titles.get("recommended", 0)
    if not isinstance(rec, int) or not 0 <= rec < len(options):
        fail("titles.recommended는 options의 인덱스(0부터 시작)여야 합니다.")

    body = data["body"]
    if not isinstance(body, list) or not body:
        fail("body는 블록의 배열이어야 합니다.")
    for i, block in enumerate(body):
        btype = block.get("type")
        if btype not in BLOCK_TYPES:
            fail(f"body[{i}]의 type '{btype}'을 알 수 없습니다. "
                 f"사용 가능한 값: {', '.join(sorted(BLOCK_TYPES))}")
        if btype == "image":
            ref = block.get("ref")
            images = data.get("images") or []
            if not any(img.get("no") == ref for img in images):
                fail(f"body[{i}]가 참조하는 이미지 번호 {ref}가 images에 없습니다.")


# ---------------------------------------------------------------- 집계

def body_text_length(body):
    """본문 글자 수. 이미지 안내와 구분선은 제외한다."""
    chunks = []
    for block in body:
        if block.get("type") in {"p", "h3", "quote", "callout"}:
            chunks.append(block.get("text", ""))
        elif block.get("type") == "info":
            for row in block.get("rows", []):
                chunks.append(" ".join(str(c) for c in row))
    joined = "".join(chunks)
    with_space = len(joined)
    without_space = len(re.sub(r"\s", "", joined))
    return with_space, without_space


def keyword_counts(body, keywords):
    text = "".join(
        b.get("text", "") for b in body
        if b.get("type") in {"p", "h3", "quote", "callout"}
    )
    return {kw: text.count(kw) for kw in keywords}


def section_lengths(body):
    """h3 섹션별 글자 수(공백 포함)를 순서대로 돌려준다."""
    sections, current, name = [], [], None
    for block in body:
        if block.get("type") == "h3":
            if name is not None:
                sections.append((name, len("".join(current))))
            name, current = block.get("text", ""), []
        elif block.get("type") in {"p", "quote", "callout"}:
            current.append(block.get("text", ""))
    if name is not None:
        sections.append((name, len("".join(current))))
    return sections


def warnings_for(data):
    body = data["body"]
    meta = data.get("meta", {})
    out = []

    with_space, _ = body_text_length(body)
    if with_space < 2000:
        out.append(f"본문이 {with_space}자로 목표치 2,000자에 못 미칩니다. "
                   f"맥락 보강 → 장면 추가 → 인용 추가 순서로 늘립니다.")

    h3_count = sum(1 for b in body if b.get("type") == "h3")
    if h3_count < 3:
        out.append(f"소제목이 {h3_count}개입니다. 최소 3개가 필요합니다.")

    for name, length in section_lengths(body):
        if length < 400:
            out.append(f"'{name}' 섹션이 {length}자로 짧습니다. 400자 이상을 권장합니다.")

    images = data.get("images") or []
    if len(images) < 2:
        out.append(f"이미지가 {len(images)}건입니다. 최소 2건을 권장합니다.")
    for img in images:
        missing = [k for k in ("url", "source", "caption") if not img.get(k)]
        if missing:
            out.append(f"이미지 {img.get('no')}번에 {', '.join(missing)}가 없습니다.")

    tags = meta.get("hashtags") or []
    if len(tags) < 10:
        out.append(f"해시태그가 {len(tags)}개입니다. 10~15개를 권장합니다.")

    banned = ["살펴보겠습니다", "알아보겠습니다", "알아보도록", "소개해 드리겠습니다",
              "매우 중요합니다", "결론적으로"]
    text = "".join(b.get("text", "") for b in body)
    hit = [w for w in banned if w in text]
    if hit:
        out.append(f"기계적인 표현이 남아 있습니다: {', '.join(hit)}")

    if not data.get("fact_check"):
        out.append("fact_check가 비어 있습니다. 확인한 사실과 출처를 남깁니다.")

    return out


# ---------------------------------------------------------------- 본문 텍스트

def render_text(data):
    book = data["book"]
    titles = data["titles"]
    meta = data.get("meta", {})
    images = {img.get("no"): img for img in (data.get("images") or [])}

    lines = [titles["options"][titles["recommended"]], ""]

    for block in data["body"]:
        btype = block["type"]
        if btype == "p":
            lines += [block["text"], ""]
        elif btype == "h3":
            lines += [block["text"], ""]
        elif btype == "quote":
            lines += [f'"{block["text"]}"', ""]
            if block.get("attr"):
                lines += [f'— {block["attr"]}', ""]
        elif btype == "callout":
            lines += [f'💡 {block["text"]}', ""]
        elif btype == "image":
            img = images.get(block["ref"], {})
            lines += [f'[ 이미지 {block["ref"]} 삽입 ]',
                      f'▲ {img.get("caption", "")} / 출처: {img.get("source", "")}', ""]
        elif btype == "info":
            for row in block.get("rows", []):
                lines.append(" · ".join(str(c) for c in row))
            lines.append("")
        elif btype == "divider":
            lines += ["ㅡㅡㅡㅡㅡㅡㅡㅡㅡㅡ", ""]

    info_bits = [f'{book["title"]} / {book["author"]}']
    for key, label in (("translator", "옮김"), ("publisher", "출판사"),
                       ("published_kr", "국내 출간"), ("pages", "쪽수")):
        if book.get(key):
            info_bits.append(f'{label}: {book[key]}')
    lines += ["📖 도서 정보", " / ".join(info_bits), ""]

    if data.get("sources"):
        lines.append("📎 참고한 자료")
        for s in data["sources"]:
            lines.append(f'- {s.get("label", "")}: {s.get("url", "")}')
        lines.append("")

    tags = meta.get("hashtags") or []
    if tags:
        lines.append(" ".join(t if t.startswith("#") else f"#{t}" for t in tags))

    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------- HTML

CSS = """
:root{--ink:#1a1a2e;--paper:#f8f5ef;--card:#fff;--accent:#c0392b;--accent2:#2c6fad;
--gold:#b8952a;--muted:#6b6b7b;--border:#d8d0c4;}
*{box-sizing:border-box;}
body{margin:0;background:var(--paper);color:var(--ink);
font-family:'Noto Sans KR',-apple-system,BlinkMacSystemFont,'Malgun Gothic',sans-serif;
line-height:1.75;}
.wrap{max-width:860px;margin:0 auto;padding:0 16px 80px;}
header.top{background:var(--ink);color:#fff;padding:28px 0;margin-bottom:24px;}
header.top .wrap{padding-bottom:0;}
header.top h1{font-family:'Noto Serif KR',serif;font-size:24px;margin:0 0 8px;line-height:1.4;}
header.top .sub{color:#b9b9c8;font-size:13px;}
.btnrow{margin-top:16px;display:flex;gap:8px;flex-wrap:wrap;}
button{font:inherit;font-size:13px;padding:9px 16px;border-radius:4px;border:1px solid var(--border);
background:var(--card);color:var(--ink);cursor:pointer;}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff;}
.card{background:var(--card);border:1px solid var(--border);border-radius:6px;margin-bottom:24px;}
.summary{padding:20px 24px;}
.summary table{width:100%;border-collapse:collapse;font-size:14px;}
.summary th{text-align:left;width:120px;color:var(--gold);font-weight:600;padding:6px 0;vertical-align:top;}
.summary td{padding:6px 0;}
.tabs{display:flex;border-bottom:1px solid var(--border);flex-wrap:wrap;}
.tab-btn{border:none;border-bottom:2px solid transparent;background:none;border-radius:0;
padding:14px 18px;color:var(--muted);}
.tab-btn.active{color:var(--accent);border-bottom-color:var(--accent);font-weight:700;}
.tab-pane{display:none;padding:24px;}
.tab-pane.active{display:block;}
.title-option{border:1px solid var(--border);border-radius:4px;padding:12px 16px;margin-bottom:8px;font-size:15px;}
.title-option.recommended{border-color:var(--accent);background:#fff8f8;font-weight:700;}
.blog-body h3{font-family:'Noto Serif KR',serif;font-size:19px;margin:34px 0 14px;
padding-left:12px;border-left:4px solid var(--accent);}
.blog-body p{margin:0 0 18px;font-size:15.5px;}
.blog-body blockquote{margin:22px 0;padding:14px 20px;background:#f5f2ec;
border-left:3px solid var(--gold);font-family:'Noto Serif KR',serif;font-size:16px;}
.blog-body blockquote .attr{display:block;margin-top:8px;font-size:13px;color:var(--muted);font-family:inherit;}
.callout{background:#f6f3ff;border-left:3px solid #8a5cf6;padding:14px 18px;margin:24px 0;border-radius:0 4px 4px 0;}
.imgslot{background:#fffbf0;border-left:3px solid var(--gold);padding:12px 18px;margin:22px 0;font-size:13.5px;color:#6b5a20;}
.infobox{background:#f4f6f9;border:1px solid var(--border);border-radius:4px;padding:14px 18px;margin:22px 0;font-size:14px;}
.infobox div{margin:3px 0;}
.imgcard{border:1px solid var(--border);border-radius:4px;margin-bottom:18px;overflow:hidden;}
.imgcard img{width:100%;display:block;background:#eee;}
.imgcard .body{padding:12px 16px;font-size:13.5px;}
.imgcard .cap{font-weight:600;margin-bottom:6px;}
.imgcard a{color:var(--accent2);word-break:break-all;}
.tag{display:inline-block;background:#eef1f6;color:var(--accent2);border-radius:12px;
padding:4px 11px;margin:3px 4px 3px 0;font-size:12.5px;}
.fact{width:100%;border-collapse:collapse;font-size:14px;}
.fact th,.fact td{border-bottom:1px solid var(--border);padding:10px 8px;text-align:left;vertical-align:top;}
.fact th{color:var(--gold);width:130px;}
.fact a{color:var(--accent2);word-break:break-all;}
.warn{background:#fff6f6;border-left:3px solid var(--accent);padding:12px 18px;font-size:13.5px;margin-bottom:20px;}
.warn ul{margin:6px 0 0 18px;padding:0;}
textarea.rawtext{width:100%;height:280px;font-family:ui-monospace,Menlo,monospace;font-size:12.5px;
border:1px solid var(--border);border-radius:4px;padding:12px;line-height:1.6;}
footer{color:var(--muted);font-size:12.5px;text-align:center;padding:30px 0;}
@media (max-width:520px){.tab-btn{padding:12px 12px;font-size:13px;}.tab-pane{padding:18px 14px;}}
"""

JS = """
function switchTab(btn, pane){
  document.querySelectorAll('.tab-btn').forEach(function(b){b.classList.remove('active');});
  btn.classList.add('active');
  document.querySelectorAll('.tab-pane').forEach(function(p){p.classList.remove('active');});
  document.getElementById(pane).classList.add('active');
}
function copyBody(){
  var ta = document.getElementById('rawtext');
  ta.select(); ta.setSelectionRange(0, 999999);
  try { document.execCommand('copy'); alert('본문을 복사했습니다. 네이버 에디터에 붙여 넣으세요.'); }
  catch(e){ alert('복사에 실패했습니다. 본문 탭에서 직접 선택해 주세요.'); }
}
function downloadHTML(){
  var blob = new Blob([document.documentElement.outerHTML], {type:'text/html;charset=utf-8'});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = DOWNLOAD_NAME;
  a.click(); URL.revokeObjectURL(a.href);
}
"""


def e(x):
    return html.escape(str(x if x is not None else ""))


def render_html(data, raw_text, warns):
    book = data["book"]
    titles = data["titles"]
    meta = data.get("meta", {})
    images = {img.get("no"): img for img in (data.get("images") or [])}
    slug = data.get("slug") or "book-review"
    rec_title = titles["options"][titles["recommended"]]
    with_space, no_space = body_text_length(data["body"])

    # --- 본문 블록
    body_html = []
    for block in data["body"]:
        t = block["type"]
        if t == "p":
            body_html.append(f"<p>{e(block['text'])}</p>")
        elif t == "h3":
            body_html.append(f"<h3>{e(block['text'])}</h3>")
        elif t == "quote":
            attr = f"<span class='attr'>— {e(block['attr'])}</span>" if block.get("attr") else ""
            body_html.append(f"<blockquote>{e(block['text'])}{attr}</blockquote>")
        elif t == "callout":
            body_html.append(f"<div class='callout'>💡 {e(block['text'])}</div>")
        elif t == "image":
            img = images.get(block["ref"], {})
            body_html.append(
                f"<div class='imgslot'>[ 이미지 {e(block['ref'])} 삽입 ] "
                f"▲ {e(img.get('caption'))} / 출처: {e(img.get('source'))}</div>")
        elif t == "info":
            rows = "".join(f"<div>{e(' · '.join(str(c) for c in row))}</div>"
                           for row in block.get("rows", []))
            body_html.append(f"<div class='infobox'>{rows}</div>")
        elif t == "divider":
            body_html.append("<hr>")

    # --- 제목 후보
    title_html = []
    for i, opt in enumerate(titles["options"]):
        cls = "title-option recommended" if i == titles["recommended"] else "title-option"
        mark = "✅ 추천 — " if i == titles["recommended"] else ""
        title_html.append(f"<div class='{cls}'>{mark}{e(opt)} <span style='color:#6b6b7b;font-size:12px'>({len(opt)}자)</span></div>")
    if titles.get("reason"):
        title_html.append(f"<p style='font-size:13.5px;color:#6b6b7b'>추천 이유: {e(titles['reason'])}</p>")

    # --- 이미지 탭
    img_html = []
    for img in (data.get("images") or []):
        lic = f" ({e(img['license'])})" if img.get("license") else ""
        img_html.append(
            "<div class='imgcard'>"
            f"<img src='{e(img.get('url'))}' alt='{e(img.get('caption'))}' loading='lazy'>"
            "<div class='body'>"
            f"<div class='cap'>이미지 {e(img.get('no'))} — {e(img.get('caption'))}</div>"
            f"<div>삽입 위치: {e(img.get('position', '본문 중간'))}</div>"
            f"<div>출처: {e(img.get('source'))}{lic}</div>"
            f"<div><a href='{e(img.get('url'))}' target='_blank' rel='noopener'>{e(img.get('url'))}</a></div>"
            "</div></div>")
    if not img_html:
        img_html.append("<p>수집한 이미지가 없습니다.</p>")

    # --- 메타 탭
    tags = meta.get("hashtags") or []
    tag_html = "".join(f"<span class='tag'>{e(t if str(t).startswith('#') else '#' + str(t))}</span>" for t in tags)
    kw = meta.get("keywords") or []
    kw_counts = keyword_counts(data["body"], [k if isinstance(k, str) else k.get("word", "") for k in kw])
    kw_rows = "".join(f"<tr><th>{e(k)}</th><td>본문 {v}회 등장</td></tr>" for k, v in kw_counts.items())
    sent_html = "".join(f"<li>{e(s)}</li>" for s in (meta.get("key_sentences") or []))

    meta_html = (
        f"<p style='font-size:14px'><strong>메타 설명</strong> ({len(meta.get('description',''))}자)<br>{e(meta.get('description'))}</p>"
        f"<p style='font-size:14px'><strong>해시태그</strong> {len(tags)}개</p><div>{tag_html}</div>"
        f"<p style='font-size:14px;margin-top:20px'><strong>핵심 키워드</strong></p>"
        f"<table class='fact'>{kw_rows}</table>"
        + (f"<p style='font-size:14px;margin-top:20px'><strong>대표 문장</strong></p><ul style='font-size:14px'>{sent_html}</ul>" if sent_html else "")
    )

    # --- 사실 확인 탭
    fact_rows = "".join(
        f"<tr><th>{e(f.get('item'))}</th><td>{e(f.get('value'))}<br>"
        f"<a href='{e(f.get('source'))}' target='_blank' rel='noopener'>{e(f.get('source'))}</a></td></tr>"
        for f in (data.get("fact_check") or []))
    src_rows = "".join(
        f"<tr><th>{e(s.get('label'))}</th><td><a href='{e(s.get('url'))}' target='_blank' rel='noopener'>{e(s.get('url'))}</a></td></tr>"
        for s in (data.get("sources") or []))
    fact_html = (f"<table class='fact'>{fact_rows}</table>" if fact_rows else "<p>검증 기록이 없습니다.</p>")
    if src_rows:
        fact_html += f"<p style='font-size:14px;margin-top:22px'><strong>참고 자료</strong></p><table class='fact'>{src_rows}</table>"
    if data.get("unverified"):
        items = "".join(f"<li>{e(u)}</li>" for u in data["unverified"])
        fact_html += f"<div class='warn' style='margin-top:22px'><strong>확인하지 못해 글에서 뺀 정보</strong><ul>{items}</ul></div>"

    warn_html = ""
    if warns:
        items = "".join(f"<li>{e(w)}</li>" for w in warns)
        warn_html = f"<div class='warn'><strong>점검이 필요한 항목</strong><ul>{items}</ul></div>"

    info_rows = ""
    for key, label in (("title", "제목"), ("original_title", "원제"), ("author", "저자"),
                       ("translator", "옮긴이"), ("publisher", "출판사"),
                       ("published_kr", "국내 출간"), ("published_original", "원서 출간"),
                       ("pages", "쪽수"), ("genre", "분류"), ("awards", "수상")):
        if book.get(key):
            info_rows += f"<tr><th>{label}</th><td>{e(book[key])}</td></tr>"
    if data.get("axis"):
        info_rows += f"<tr><th>리뷰의 축</th><td>{e(data['axis'])}</td></tr>"
    info_rows += f"<tr><th>본문 분량</th><td>{with_space:,}자 (공백 제외 {no_space:,}자)</td></tr>"

    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(rec_title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;600;700&family=Noto+Sans+KR:wght@300;400;500;700&display=swap" rel="stylesheet">
<style>{CSS}</style></head>
<body>
<header class="top"><div class="wrap">
<h1>{e(rec_title)}</h1>
<div class="sub">{e(book['title'])} · {e(book['author'])} · 작성일 {date.today().isoformat()}</div>
<div class="btnrow">
<button class="primary" onclick="copyBody()">본문 복사</button>
<button onclick="downloadHTML()">HTML 다운로드</button>
</div></div></header>

<div class="wrap">
{warn_html}
<div class="card summary"><table>{info_rows}</table></div>

<div class="card">
<div class="tabs">
<button class="tab-btn active" onclick="switchTab(this,'pane-body')">블로그 본문</button>
<button class="tab-btn" onclick="switchTab(this,'pane-img')">이미지 자료</button>
<button class="tab-btn" onclick="switchTab(this,'pane-meta')">메타 정보</button>
<button class="tab-btn" onclick="switchTab(this,'pane-fact')">사실 확인</button>
<button class="tab-btn" onclick="switchTab(this,'pane-raw')">복붙용 원문</button>
</div>

<div class="tab-pane active" id="pane-body">
{''.join(title_html)}
<div class="blog-body">{''.join(body_html)}</div>
</div>

<div class="tab-pane" id="pane-img">{''.join(img_html)}</div>
<div class="tab-pane" id="pane-meta">{meta_html}</div>
<div class="tab-pane" id="pane-fact">{fact_html}</div>
<div class="tab-pane" id="pane-raw">
<p style='font-size:13.5px;color:#6b6b7b'>아래 내용을 그대로 네이버 에디터에 붙여 넣으세요. 이미지 자리에는 안내 문구가 들어 있습니다.</p>
<textarea class="rawtext" id="rawtext" readonly>{e(raw_text)}</textarea>
</div>
</div>

<footer>naver-book-review 스킬로 생성 · 이미지는 URL과 출처만 제공합니다</footer>
</div>
<script>var DOWNLOAD_NAME = "{e(slug)}.html";{JS}</script>
</body></html>
"""


# ---------------------------------------------------------------- 진입점

def main():
    ap = argparse.ArgumentParser(description="독후감 post.json을 본문 텍스트와 HTML로 변환한다.")
    ap.add_argument("post_json")
    ap.add_argument("--outdir", default="outputs")
    args = ap.parse_args()

    path = Path(args.post_json)
    if not path.exists():
        fail(f"{path} 파일을 찾을 수 없습니다.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"JSON 형식이 잘못되었습니다: {exc}")

    validate(data)
    warns = warnings_for(data)
    raw_text = render_text(data)
    page = render_html(data, raw_text, warns)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    slug = data.get("slug") or re.sub(r"[^\w가-힣-]+", "-", data["book"]["title"])[:40]
    txt_path = outdir / f"{slug}.txt"
    html_path = outdir / f"{slug}.html"
    txt_path.write_text(raw_text, encoding="utf-8")
    html_path.write_text(page, encoding="utf-8")

    with_space, no_space = body_text_length(data["body"])
    print(f"본문 {with_space:,}자 (공백 제외 {no_space:,}자)")
    print(f"소제목 {sum(1 for b in data['body'] if b.get('type') == 'h3')}개 · "
          f"이미지 {len(data.get('images') or [])}건 · "
          f"해시태그 {len(data.get('meta', {}).get('hashtags') or [])}개")
    for name, length in section_lengths(data["body"]):
        print(f"  - {name}: {length}자")
    if warns:
        print("\n점검이 필요한 항목:")
        for w in warns:
            print(f"  ! {w}")
    print(f"\n생성 완료:\n  {txt_path}\n  {html_path}")


if __name__ == "__main__":
    main()
