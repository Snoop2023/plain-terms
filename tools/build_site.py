#!/usr/bin/env python3
"""把 terms/ 下的词条生成静态站点。

只用 Python 标准库 + pyyaml。零前端依赖：不需要 node、不需要 npm。
用法：python3 tools/build_site.py
产物：_site/（index.html、t/<id>.html、search.json、style.css）—— 直接可发布。
"""
import html
import json
import os
import re
import shutil
import sys

try:
    import yaml
except ImportError:
    sys.exit("需要 pyyaml：pip install pyyaml")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERDICT_MARK = {"accurate": "✅", "misleading": "⚠️", "both_hard": "🔁"}
FIELD_ORDER = ["人话", "英文释义", "英文来源", "中文来源"]
BULLET_RE = re.compile(
    r"^(?P<indent> *)- \*\*(?P<who>.+?)\*\*｜背景：(?P<bg>.*?)｜来源：(?P<src>.*?)(?:｜(?P<note>.*))?$"
)


# ---------- 读取 ----------

def load_config():
    with open(os.path.join(ROOT, "site.yaml"), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def split_front_matter(text):
    if not text.startswith("---"):
        return {}, text
    end = text.index("\n---", 3)
    meta = yaml.safe_load(text[3:end]) or {}
    body = text[end + 4 :].lstrip("\n")
    return meta, body


def parse_comments(lines):
    """把 ## 评论区 下的结构化列表解析成两级评论树。"""
    flat = []
    cur = None
    for line in lines:
        m = BULLET_RE.match(line)
        if m:
            level = 1 if len(m.group("indent")) >= 2 else 0
            cur = {
                "level": level,
                "who": m.group("who").strip(),
                "background": m.group("bg").strip(),
                "source": m.group("src").strip(),
                "text": [],
            }
            flat.append(cur)
            continue
        stripped = line.strip()
        if stripped.startswith(">") and cur is not None:
            cur["text"].append(stripped[1:].strip())
    for c in flat:
        c["text"] = "\n".join(c["text"]).strip()

    tree = []
    for c in flat:
        if c["level"] == 0 or not tree:
            c["replies"] = []
            tree.append(c)
        else:
            tree[-1]["replies"].append(c)
    return tree


def parse_term(path):
    with open(path, encoding="utf-8") as fh:
        meta, body = split_front_matter(fh.read())

    if meta.get("type") == "essay":
        items = [ln[2:].strip() for ln in body.split("\n") if ln.startswith("- ")]
        return {"kind": "essay", "meta": meta, "items": items}

    fields = {}
    comments = {}
    current = None
    for line in body.split("\n"):
        if line.startswith("## "):
            current = line[3:].strip()
            if current == "评论区":
                comments[current] = []
            else:
                fields[current] = []
            continue
        if current is None:
            continue
        if current == "评论区":
            comments[current].append(line)
        else:
            fields[current].append(line)

    return {
        "kind": "term",
        "meta": meta,
        "fields": {k: "\n".join(v).strip() for k, v in fields.items()},
        "comments": parse_comments(comments.get("评论区", [])),
        "path": os.path.relpath(path, ROOT),
    }


def load_terms():
    terms, essays = [], []
    for dirpath, _dirnames, filenames in os.walk(os.path.join(ROOT, "terms")):
        for name in sorted(filenames):
            if not name.endswith(".md"):
                continue
            item = parse_term(os.path.join(dirpath, name))
            (essays if item["kind"] == "essay" else terms).append(item)
    return terms, essays


# ---------- 渲染 ----------

def esc(text):
    return html.escape(text, quote=False)


def inline(text):
    """极简 markdown 行内语法：**粗** *斜* `码`。先转义再替换，避免注入。"""
    out = esc(text)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", out)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    return out.replace("\n", "<br>")


def paras(text, css_class=""):
    if not text.strip():
        return ""
    cls = ' class="%s"' % css_class if css_class else ""
    return "\n".join("<p%s>%s</p>" % (cls, inline(p)) for p in text.split("\n\n") if p.strip())


def fill(template, values):
    out = template
    for key, value in values.items():
        out = out.replace("{{%s}}" % key, str(value))
    return out


def read_template(name):
    with open(os.path.join(ROOT, "templates", name), encoding="utf-8") as fh:
        return fh.read()


def github_url(cfg, path, branch=None):
    base = cfg["repo"]["url"].strip("/")
    branch = branch or cfg["repo"].get("branch", "main")
    return "%s/edit/%s/%s" % (base, branch, path) if path else base


def name_pair(meta):
    """返回 (显示名, 英文名)。纯英文词条不重复显示两遍。"""
    zh = (meta.get("term_zh") or "").strip()
    en = (meta.get("term_en") or "").strip()
    if zh.lower() == en.lower():
        return zh, ""
    return zh or en, en if zh else ""


def render_comment(c):
    replies = "".join(render_comment(r) for r in c.get("replies", []))
    src_class = "src quoted" if c["source"].startswith("引述") else "src"
    return (
        '<div class="comment">'
        '<div class="meta"><span class="who">%s</span><span class="chip">%s</span>'
        '<span class="%s">%s</span></div>'
        '<p class="text">%s</p>%s</div>'
    ) % (
        esc(c["who"]),
        esc(c["background"]),
        src_class,
        esc(c["source"]),
        inline(c["text"]),
        '<div class="replies">%s</div>' % replies if replies else "",
    )


def render_term_page(term, base, cfg, term_tpl):
    meta = term["meta"]
    parent = "../" if term["path"] else ""
    fields_html = []
    for name in FIELD_ORDER[1:]:
        text = term["fields"].get(name)
        if text:
            fields_html.append(
                '<section class="field"><h2>%s</h2>%s</section>' % (esc(name), paras(text))
            )
    for name, text in term["fields"].items():
        if name in FIELD_ORDER:
            continue
        fields_html.append(
            '<section class="field"><h2>%s</h2>%s</section>' % (esc(name), paras(text))
        )

    aliases = "".join(
        '<span class="chip">也叫 %s</span>' % esc(a) for a in (meta.get("aliases") or [])
    )
    disp_zh, disp_en = name_pair(meta)
    n = sum(1 for _ in term["comments"])
    n_all = len(term["comments"]) + sum(len(c.get("replies", [])) for c in term["comments"])
    comments_html = "".join(render_comment(c) for c in term["comments"])
    if not comments_html:
        comments_html = '<p class="empty">还没有评论。第一条留给你。</p>'

    content = fill(
        term_tpl,
        {
            "term_zh": esc(disp_zh),
            "term_en": esc(disp_en),
            "verdict": meta.get("verdict", "accurate"),
            "verdict_mark": VERDICT_MARK.get(meta.get("verdict", ""), "✅"),
            "verdict_note": esc(meta.get("verdict_note", "")),
            "category": esc(meta.get("category", "")),
            "aliases": aliases,
            "plain": inline(term["fields"].get("人话", "（待补）")),
            "fields": "\n".join(fields_html),
            "comment_count": " · %d 条" % n_all if n_all else "",
            "comments": comments_html,
            "edit_url": github_url(cfg, term["path"]),
            "new_comment_url": github_url(cfg, cfg["repo"]["new_comment_path"]),
            "related_url": "%sindex.html#%s" % (parent, meta.get("category", "")),
        },
    )

    out = fill(
        base,
        {
            "title": "%s · %s" % (disp_zh, cfg["site"]["title"]),
            "description": cfg["site"]["description"],
            "site_title": esc(cfg["site"]["title"]),
            "site_tagline": esc(cfg["site"]["tagline"]),
            "footer_note": esc(cfg["site"]["footer_note"]),
            "root": parent,
            "content": content,
        },
    )
    return out


def render_card(term, cfg):
    meta = term["meta"]
    plain = term["fields"].get("人话", "")
    disp_zh, disp_en = name_pair(meta)
    n = len(term["comments"]) + sum(len(c.get("replies", [])) for c in term["comments"])
    search = " ".join(
        [meta.get("term_zh", ""), meta.get("term_en", ""), meta.get("category", "")]
        + [term["fields"].get(k, "") for k in FIELD_ORDER]
        + [c["text"] for c in term["comments"]]
    ).lower()
    en_html = '<span class="en">%s</span>' % esc(disp_en) if disp_en else ""
    return (
        '<a class="card" data-search="%s" href="t/%s.html">'
        '<div class="head"><span class="zh">%s</span>%s'
        '<span class="badge %s">%s</span></div>'
        '<p class="plain">%s</p>'
        '<div class="stats">%s · %d 条评论</div></a>'
    ) % (
        esc(search.replace('"', " ")),
        meta.get("id", ""),
        esc(disp_zh),
        en_html,
        meta.get("verdict", ""),
        VERDICT_MARK.get(meta.get("verdict", ""), "✅"),
        inline(plain[:110] + ("…" if len(plain) > 110 else "")),
        esc(meta.get("category", "")),
        n,
    )


def build():
    cfg = load_config()
    terms, essays = load_terms()
    terms.sort(key=lambda t: (list(cfg["categories"].keys()).index(t["meta"]["category"])
                              if t["meta"].get("category") in cfg["categories"] else 99,
                              t["meta"].get("term_zh", "")))

    out_dir = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "_site")
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(os.path.join(out_dir, "t"))
    shutil.copy(os.path.join(ROOT, "templates", "style.css"), os.path.join(out_dir, "style.css"))

    base = read_template("base.html")
    term_tpl = read_template("term.html")

    # 词条页
    for term in terms:
        page = render_term_page(term, base, cfg, term_tpl)
        with open(os.path.join(out_dir, "t", term["meta"]["id"] + ".html"), "w", encoding="utf-8") as fh:
            fh.write(page)

    # 首页
    sections = []
    for cat, slug in cfg["categories"].items():
        group = [t for t in terms if t["meta"].get("category") == cat]
        if not group:
            continue
        cards = "\n".join(render_card(t, cfg) for t in group)
        sections.append(
            '<h2 class="cat" data-cat="%s">%s <span style="opacity:.6">%d</span></h2>'
            '<div class="cards" data-cat="%s">%s</div>' % (slug, esc(cat), len(group), slug, cards)
        )

    patterns_html = ""
    for essay in essays:
        items = "".join("<li>%s</li>" % inline(i) for i in essay["items"])
        patterns_html = (
            '<div class="patterns"><h2>%s</h2><ul>%s</ul></div>'
            % (esc(essay["meta"].get("title", "")), items)
        )

    content = fill(
        read_template("index.html"),
        {
            "intro": inline(cfg["site"]["intro"].strip()),
            "legend_accurate": "中文其实准，知道字的本义就懂",
            "legend_misleading": "中文有歧义或误导，先看英文",
            "legend_both_hard": "两边都不直观，只能记住它指什么",
            "sections": "\n".join(sections),
            "patterns": patterns_html,
            "new_term_url": github_url(cfg, cfg["repo"]["new_term_path"]),
        },
    )
    index = fill(
        base,
        {
            "title": cfg["site"]["title"],
            "description": cfg["site"]["description"],
            "site_title": esc(cfg["site"]["title"]),
            "site_tagline": esc(cfg["site"]["tagline"]),
            "footer_note": esc(cfg["site"]["footer_note"]),
            "root": "",
            "content": content,
        },
    )
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(index)

    # 搜索索引（给以后接搜素引擎用）
    search = [
        {
            "id": t["meta"]["id"],
            "zh": t["meta"].get("term_zh", ""),
            "en": t["meta"].get("term_en", ""),
            "category": t["meta"].get("category", ""),
            "verdict": t["meta"].get("verdict", ""),
            "plain": t["fields"].get("人话", ""),
        }
        for t in terms
    ]
    with open(os.path.join(out_dir, "search.json"), "w", encoding="utf-8") as fh:
        json.dump(search, fh, ensure_ascii=False, indent=1)

    n_comments = sum(
        len(t["comments"]) + sum(len(c.get("replies", [])) for c in t["comments"]) for t in terms
    )
    print("词条页：%d 个" % len(terms))
    print("评论：%d 条" % n_comments)
    print("输出：%s" % out_dir)


if __name__ == "__main__":
    build()
