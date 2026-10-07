#!/usr/bin/env python3
"""把 terms/ 下的词条生成静态站点：首页是信息流，每个词一页。

只依赖 Python 标准库 + pyyaml。零前端依赖：不需要 node、不需要 npm。
用法：python3 tools/build_site.py [输出目录]     默认 _site
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
FIELD_ORDER = ["造词现场", "人话", "英文释义", "英文来源", "中文来源"]
DETAIL_FIELDS = ["英文释义", "英文来源", "中文来源"]
FEED_REPLIES = 2  # 信息流里一条推先亮几条顶层评论
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
    return (yaml.safe_load(text[3:end]) or {}), text[end + 4 :].lstrip("\n")


def parse_comments(lines):
    flat, cur = [], None
    for line in lines:
        m = BULLET_RE.match(line)
        if m:
            cur = {
                "level": 1 if len(m.group("indent")) >= 2 else 0,
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
        return {"kind": "essay", "meta": meta,
                "items": [ln[2:].strip() for ln in body.split("\n") if ln.startswith("- ")]}

    fields, comments, current = {}, {}, None
    for line in body.split("\n"):
        if line.startswith("## "):
            current = line[3:].strip()
            comments[current] = [] if current == "评论区" else None
            if current != "评论区":
                fields[current] = []
            continue
        if current is None:
            continue
        (comments[current] if current == "评论区" else fields[current]).append(line)

    return {
        "kind": "term",
        "meta": meta,
        "fields": {k: "\n".join(v).strip() for k, v in fields.items()},
        "comments": parse_comments(comments.get("评论区", [])),
        "path": os.path.relpath(path, ROOT),
    }


def load_all():
    terms, essays = [], []
    for dirpath, _dirs, files in os.walk(os.path.join(ROOT, "terms")):
        for name in sorted(files):
            if not name.endswith(".md"):
                continue
            item = parse_term(os.path.join(dirpath, name))
            (essays if item["kind"] == "essay" else terms).append(item)
    return terms, essays


# ---------- 渲染小工具 ----------

def esc(text):
    return html.escape(text, quote=False)


def inline(text):
    out = esc(text)
    out = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', out)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", out)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    return out.replace("\n", "<br>")


def paras(text):
    if not text.strip():
        return ""
    return "\n".join("<p>%s</p>" % inline(p) for p in text.split("\n\n") if p.strip())


def clip(text, n):
    text = re.sub(r"[*`]", "", text).replace("\n", " ").strip()
    if len(text) <= n:
        return text
    cut = text[:n]
    for stop in "。！？；":
        i = cut.rfind(stop)
        if i >= n * 0.45:
            return cut[: i + 1]
    for stop in "，、：":
        i = cut.rfind(stop)
        if i >= n * 0.45:
            return cut[:i] + "……"
    return cut + "…"


def fill(template, values):
    out = template
    for key, value in values.items():
        out = out.replace("{{%s}}" % key, str(value))
    return out


def read_template(name):
    with open(os.path.join(ROOT, "templates", name), encoding="utf-8") as fh:
        return fh.read()


def name_pair(meta):
    zh = (meta.get("term_zh") or "").strip()
    en = (meta.get("term_en") or "").strip()
    if zh.lower() == en.lower():
        return zh, ""
    return zh or en, en if zh else ""


def cat_slug(meta, cfg):
    return cfg["categories"].get(meta.get("category", ""), "ai")


def initial(meta):
    zh = (meta.get("term_zh") or meta.get("term_en") or "?").strip()
    return esc(zh[0].upper())


def n_comments(term):
    return len(term["comments"]) + sum(len(c.get("replies", [])) for c in term["comments"])


def repo_edit(cfg, path=None):
    base = cfg["repo"]["url"].strip("/")
    branch = cfg["repo"].get("branch", "main")
    return "%s/edit/%s/%s" % (base, branch, path) if path else base


def page(template, cfg, content, root="", title=None):
    return fill(template, {
        "title": title or cfg["site"]["title"],
        "description": cfg["site"]["description"],
        "site_title": esc(cfg["site"]["title"]),
        "site_tagline": esc(cfg["site"]["tagline"]),
        "footer_note": esc(cfg["site"]["footer_note"]),
        "root": root,
        "content": content,
    })


# ---------- 评论区 ----------

def render_thread(c, idx):
    src_class = "src quoted" if c["source"].startswith("引述") else "src"
    subs = "".join(
        '<div class="sub"><div class="cm">%s<p>%s</p></div></div>'
        % (meta_line(r), inline(r["text"]))
        for r in c.get("replies", [])
    )
    return (
        '<div class="thread" id="c%d"><div class="cm">%s<p>%s</p></div>%s</div>'
        % (idx, meta_line(c, src_class), inline(c["text"]), subs)
    )


def meta_line(c, src_class="src"):
    return (
        '<div class="meta"><span class="who">%s</span><span class="tagchip">%s</span>'
        '<span class="%s">%s</span></div>' % (esc(c["who"]), esc(c["background"]), src_class, esc(c["source"]))
    )


def render_reply(c):
    """信息流里那条短回复。"""
    src = ' <span class="quoted">%s</span>' % esc(c["source"]) if c["source"].startswith("引述") else ""
    return (
        '<div class="reply"><span class="rav">%s</span><div class="rt">'
        '<div class="rm"><b>%s</b> · %s%s</div><p>%s</p></div></div>'
        % (esc(c["who"][:1]), esc(c["who"]), esc(c["background"]), src, inline(clip(c["text"], 160)))
    )


# ---------- 信息流的推 ----------

def render_post(term, cfg):
    meta = term["meta"]
    disp_zh, disp_en = name_pair(meta)
    n = n_comments(term)
    search = " ".join(
        [meta.get("term_zh", ""), meta.get("term_en", ""), meta.get("category", "")]
        + list(term["fields"].values())
        + [c["text"] for c in term["comments"]]
    ).lower().replace('"', " ")

    replies = ""
    for c in term["comments"][:FEED_REPLIES]:
        replies += render_reply(c)
        for r in c.get("replies", [])[:1]:
            replies += render_reply(r)
    if term["comments"]:
        replies = '<div class="replies">%s</div>' % replies

    origin = term["fields"].get("造词现场", "")
    return (
        '<article class="post" id="%s" data-cat="%s" data-search="%s">'
        '<a class="avatar %s" href="t/%s.html">%s</a>'
        '<div class="body">'
        '<div class="ph"><a class="name" href="t/%s.html">%s</a>'
        '<span class="handle">@%s</span><span class="cat">%s</span>'
        '<span class="mk">%s</span></div>'
        '<p class="hook">%s</p>'
        '<div class="origin clip"><span class="olabel">造词现场</span>%s</div>'
        "%s"
        '<div class="pf"><a href="t/%s.html#comments">💬 %d 条评论</a>'
        '<a href="t/%s.html">🔗 单独链接</a>'
        '<a href="%s">✏️ 改这个词</a></div>'
        "</div></article>"
    ) % (
        meta.get("id", ""), cat_slug(meta, cfg), esc(search),
        cat_slug(meta, cfg), meta.get("id", ""), initial(meta),
        meta.get("id", ""), esc(disp_zh),
        esc(meta.get("id", "")), esc(meta.get("category", "")),
        VERDICT_MARK.get(meta.get("verdict", ""), "✅"),
        inline(clip(term["fields"].get("人话", ""), 150)),
        inline(clip(origin, 110)),
        replies,
        meta.get("id", ""), n, meta.get("id", ""), repo_edit(cfg, term["path"]),
    )


def render_pinned(cfg):
    return (
        '<article class="post" data-cat="pinned" id="why">'
        '<span class="avatar a-me">越</span><div class="body">'
        '<div class="ph"><span class="name">周越</span><span class="handle">@stitch</span>'
        '<span class="pin">置顶</span><span class="mk">📌</span></div>'
        '<p class="hook">%s</p>'
        '<p class="hook">%s</p>'
        '<p class="hook">%s</p>'
        '<div class="pf"><a href="method.html">📌 完整方法论</a>'
        '<a href="%s">💬 在 GitHub 上讨论</a></div>'
        "</div></article>"
    ) % (
        inline("概念是倒着来的：先有人解决一个具体问题，事后才给这件事取了个名字。所以每个词条的第一段是**造词现场** —— 造这个词之前，人们在解决什么。"),
        inline("评论区里说话的是普通人，跟你一样。大脑是预测机器：看到相似的人懂了，它就会推出「我也能懂」。教科书只给你一个样本，评论给的是好几个。"),
        inline("从上往下读：造词现场 → 人话 → 词源 → 评论区。觉得哪条讲得好就点赞，觉得自己那版更好就留一条。"),
        cfg["repo"]["url"].strip("/") + "/discussions",
    )


# ---------- 词条页 ----------

def giscus_snippet(cfg, term_id):
    g = cfg.get("giscus") or {}
    if not g.get("repo_id"):
        return '<p class="empty">讨论区还没接上。</p>'
    return (
        '<script src="https://giscus.app/client.js"\n'
        '        data-repo="%(repo)s"\n'
        '        data-repo-id="%(repo_id)s"\n'
        '        data-category="%(category)s"\n'
        '        data-category-id="%(category_id)s"\n'
        '        data-mapping="specific"\n'
        '        data-term="%(term)s"\n'
        '        data-reactions-enabled="1"\n'
        '        data-emit-metadata="0"\n'
        '        data-input-position="top"\n'
        '        data-theme="preferred_color_scheme"\n'
        '        data-lang="zh-CN"\n'
        '        data-loading="lazy"\n'
        '        crossorigin="anonymous" async></script>'
    ) % {"repo": g["repo"], "repo_id": g["repo_id"], "category": g["category"],
         "category_id": g["category_id"], "term": term_id}


def render_term_page(term, cfg, tpl):
    meta = term["meta"]
    disp_zh, disp_en = name_pair(meta)
    aliases = "".join('<span class="tagchip">也叫 %s</span>' % esc(a) for a in (meta.get("aliases") or []))

    fields_html = []
    for name in DETAIL_FIELDS + [k for k in term["fields"] if k not in FIELD_ORDER]:
        if term["fields"].get(name):
            fields_html.append(
                '<section class="field"><h2>%s</h2>%s</section>' % (esc(name), paras(term["fields"][name]))
            )

    comments = "".join(render_thread(c, i) for i, c in enumerate(term["comments"], 1))
    if not comments:
        comments = '<p class="empty">还没有评论。第一条留给你。</p>'

    content = fill(tpl, {
        "id": meta.get("id", ""),
        "cat_slug": cat_slug(meta, cfg),
        "initial": initial(meta),
        "disp_zh": esc(disp_zh),
        "disp_en": esc(disp_en),
        "category": esc(meta.get("category", "")),
        "verdict_mark": VERDICT_MARK.get(meta.get("verdict", ""), "✅"),
        "verdict_note": esc(meta.get("verdict_note", "")),
        "aliases": aliases,
        "origin": paras(term["fields"].get("造词现场", "")),
        "plain": paras(term["fields"].get("人话", "")),
        "fields": "\n".join(fields_html),
        "comment_count": " · %d 条" % n_comments(term),
        "comments": comments,
        "giscus": giscus_snippet(cfg, meta.get("id", "")),
        "new_comment_url": cfg["repo"]["url"].strip("/") + "/issues/new",
        "edit_url": repo_edit(cfg, term["path"]),
        "repo_url": cfg["repo"]["url"].strip("/"),
        "path": term["path"],
    })
    return page(read_template("base.html"), cfg, content, root="../",
                title="%s · %s" % (disp_zh, cfg["site"]["title"]))


# ---------- Markdown（只给方法论页用） ----------

def md_to_html(md):
    out, i = [], 0
    lines = md.split("\n")
    while i < len(lines):
        line = lines[i]
        if line.startswith("| ") and i + 1 < len(lines) and set(lines[i + 1]) <= set("|-: "):
            head = [c.strip() for c in line.strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and lines[i].startswith("| "):
                rows.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            out.append("<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (
                "".join("<th>%s</th>" % inline(h) for h in head),
                "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % inline(c) for c in r) for r in rows)))
            continue
        if line.startswith(">"):
            block = []
            while i < len(lines) and lines[i].startswith(">"):
                block.append(lines[i].lstrip(">").strip())
                i += 1
            out.append("<blockquote>%s</blockquote>" % paras("\n".join(block)))
            continue
        if line.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append("<li>%s</li>" % inline(lines[i][2:]))
                i += 1
            out.append("<ul>%s</ul>" % "".join(items))
            continue
        if line.startswith("#"):
            lvl = len(line) - len(line.lstrip("#"))
            out.append("<h%d>%s</h%d>" % (lvl, inline(line[lvl:].strip()), lvl))
            i += 1
            continue
        if not line.strip():
            i += 1
            continue
        block = []
        while i < len(lines) and lines[i].strip() and not lines[i].startswith(("#", ">", "- ", "| ")):
            block.append(lines[i])
            i += 1
        out.append("<p>%s</p>" % inline(" ".join(block)))
    return "\n".join(out)


# ---------- 构建 ----------

def build(out_dir):
    cfg = load_config()
    terms, essays = load_all()
    order = list(cfg["categories"].keys())
    terms.sort(key=lambda t: (order.index(t["meta"]["category"])
                              if t["meta"].get("category") in order else 99,
                              t["meta"].get("term_zh", "")))

    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(os.path.join(out_dir, "t"))
    shutil.copy(os.path.join(ROOT, "templates", "style.css"), os.path.join(out_dir, "style.css"))

    # 词条页
    for term in terms:
        with open(os.path.join(out_dir, "t", term["meta"]["id"] + ".html"), "w", encoding="utf-8") as fh:
            fh.write(render_term_page(term, cfg, read_template("post.html")))

    # 信息流
    chips = "".join(
        '<button class="chipbtn" data-cat="%s">%s %d</button>'
        % (slug, esc(cat), sum(1 for t in terms if t["meta"].get("category") == cat))
        for cat, slug in cfg["categories"].items()
    )
    items = "\n".join(render_post(t, cfg) for t in terms)
    patterns = ""
    for essay in essays:
        patterns = '<div class="patterns"><h2>%s</h2><ul>%s</ul></div>' % (
            esc(essay["meta"].get("title", "")),
            "".join("<li>%s</li>" % inline(i) for i in essay["items"]))
    feed = fill(read_template("feed.html"), {
        "total": len(terms),
        "chips": chips,
        "pinned": render_pinned(cfg),
        "items": items,
        "patterns": patterns,
        "new_term_url": cfg["repo"]["url"].strip("/") + "/issues/new",
    })
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(page(read_template("base.html"), cfg, feed))

    # 方法论
    with open(os.path.join(ROOT, "METHOD.md"), encoding="utf-8") as fh:
        md = fh.read()
    md = "\n".join(l for l in md.split("\n") if not l.startswith("# 为什么这么排"))
    with open(os.path.join(out_dir, "method.html"), "w", encoding="utf-8") as fh:
        fh.write(page(read_template("base.html"), cfg,
                      fill(read_template("method.html"), {"content": md_to_html(md)}),
                      title="为什么这么排 · %s" % cfg["site"]["title"]))

    with open(os.path.join(out_dir, "search.json"), "w", encoding="utf-8") as fh:
        json.dump([{"id": t["meta"]["id"], "zh": t["meta"].get("term_zh", ""),
                    "en": t["meta"].get("term_en", ""), "category": t["meta"].get("category", ""),
                    "verdict": t["meta"].get("verdict", ""),
                    "origin": t["fields"].get("造词现场", ""),
                    "plain": t["fields"].get("人话", "")} for t in terms],
                  fh, ensure_ascii=False, indent=1)

    print("词条页：%d 个" % len(terms))
    print("评论：%d 条" % sum(n_comments(t) for t in terms))
    print("输出：%s" % out_dir)


if __name__ == "__main__":
    build(os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "_site"))
