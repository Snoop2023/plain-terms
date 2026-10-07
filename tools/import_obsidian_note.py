#!/usr/bin/env python3
"""一次性迁移脚本：把 Obsidian 笔记《数学与 AI 术语 · 词源对照》拆成一条术语一个文件。

保留在仓库里作为迁移记录，以后不用再跑。
用法：python3 tools/import_obsidian_note.py <源.md> <输出目录>
"""
import os
import re
import sys

try:
    import yaml
except ImportError:
    sys.exit("需要 pyyaml：pip install pyyaml")

VERDICT = {"✅": "accurate", "⚠️": "misleading", "🔁": "both_hard"}
VERDICT_LABEL = {
    "accurate": "中文其实准，知道字的本义就懂",
    "misleading": "中文有歧义或误导，先看英文",
    "both_hard": "两边都不直观，只能记住它指什么",
}
CATEGORY_ID = {
    "基础数学": "math",
    "微积分": "calculus",
    "线性代数": "linear-algebra",
    "概率与信息": "probability",
    "AI 专用词": "ai",
}

# 角色笔名 → 真实背景。开源版靠背景标签让人对号入座，笔名只是昵称。
BACKGROUND = {
    "吐槽役": "非本专业读者",
    "吐槽役 2": "非本专业读者",
    "C 语言老兵": "底层软件 / C",
    "数学系路人": "数学专业",
    "古籍爱好者": "中文古籍 / 翻译史",
    "自动化差生": "自动化 / 控制",
    "自动化同学": "自动化 / 控制",
    "自动化老师": "自动化 / 控制",
    "BMS 老电工": "动力电池 / 嵌入式",
    "炼丹师": "AI 训练 / 工程",
    "登山爱好者": "户外 / 非本专业读者",
    "3B1B 观众": "自学者",
    "振动工程师": "结构 / 振动工程",
    "物理系路人": "物理专业",
    "信息论路人": "信息论",
    "天气预报员": "气象",
    "冷知识": "科普爱好者",
    "赌场保安": "概率 / 赌博",
    "侦探小说迷": "推理爱好者",
    "考生": "学生",
    "数据库工程师": "数据库",
    "嵌入式老兵": "嵌入式 / 固件",
    "网友": "网友",
}

REPLY_RE = re.compile(r"^　?└\s*回复\s*·\s*(?P<who>.+)$")
SPEAKER_RE = re.compile(r"^\*\*(?P<who>.+?)\*\*：(?P<text>.*)$")
FIELD_RE = re.compile(r"^- \*\*(?P<key>.+?)\*\*：(?P<value>.*)$")
HEADING_RE = re.compile(r"^###\s+(?P<rest>.+)$")
CATEGORY_RE = re.compile(r"^##\s+[一二三四五六七八九十]+、\s*(?P<name>.+?)\s*$")


def norm_comment(who):
    """返回 (昵称, 背景, 来源类型)。来源类型：quoted=真实原话，editorial=编者视角。"""
    origin = "editorial"
    if "原推" in who:
        origin = "quoted"
    who = who.replace("（原推）", "").replace("(原推)", "").strip()
    who = REPLY_RE.sub(lambda m: m.group("who").strip(), who)
    return who, BACKGROUND.get(who, "网友"), origin


def yaml_front(matter):
    return "---\n" + yaml.safe_dump(
        matter, allow_unicode=True, sort_keys=False, default_flow_style=False, width=200
    ) + "---\n"


def parse(path):
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().split("\n")

    terms = []
    patterns = []
    category = None
    cur = None
    last_comment = None  # 用于把「└ 回复」挂到父评论上
    in_patterns = False

    for raw in lines:
        line = raw.rstrip()

        mcat = CATEGORY_RE.match(line)
        if mcat:
            category = mcat.group("name").strip()
            cur = None
            in_patterns = False
            continue

        if line.startswith("## 几条串起来的规律"):
            in_patterns = True
            cur = None
            continue

        mhead = HEADING_RE.match(line)
        if mhead and mhead.group("rest").startswith("### "):
            pass
        if line.startswith("### ") and not in_patterns:
            rest = line[4:].strip()
            verdict = "accurate"
            for mark, name in VERDICT.items():
                if mark in rest:
                    verdict = name
                    rest = rest.replace(mark, "").strip()
            # 中文名 + 末尾一段英文名（可能多个词，如 activation function）
            men = re.search(
                r"^(?P<zh>.*?)\s*(?P<en>[A-Za-z][A-Za-z0-9\-]*(?:\s+[A-Za-z][A-Za-z0-9\-]*)*)$", rest
            )
            if men:
                term_zh = men.group("zh").strip()
                term_en = men.group("en").strip()
            else:
                term_zh, term_en = rest, ""
            if not term_en and " / " in term_zh:
                # 形如「token / 词元」：英文在前、中文在后
                term_en, term_zh = [p.strip() for p in term_zh.split(" / ", 1)]
            if not term_zh:
                term_zh = term_en
            cur = {
                "id": re.sub(r"[^a-z0-9]+", "-", term_en.lower()).strip("-")
                or "term-%d" % (len(terms) + 1),
                "term_zh": term_zh,
                "term_en": term_en,
                "category": category,
                "verdict": verdict,
                "fields": [],
                "comments": [],
                "aliases": [],
            }
            terms.append(cur)
            last_comment = None
            continue

        if in_patterns:
            if line.startswith("- "):
                patterns.append(line[2:].strip())
            continue

        if cur is None:
            continue

        if line.startswith("> [!quote]"):
            continue

        if line.startswith("> "):
            body = line[2:].strip()
            if not body:
                continue
            ms = SPEAKER_RE.match(body)
            if ms:
                who, background, origin = norm_comment(ms.group("who"))
                if REPLY_RE.search(ms.group("who")):
                    entry = {
                        "who": who,
                        "background": background,
                        "origin": origin,
                        "reply_to": len(cur["comments"]) - 1,
                        "text": ms.group("text").strip(),
                    }
                else:
                    entry = {
                        "who": who,
                        "background": background,
                        "origin": origin,
                        "reply_to": None,
                        "text": ms.group("text").strip(),
                    }
                cur["comments"].append(entry)
                last_comment = entry
            elif last_comment is not None:
                last_comment["text"] += "\n" + body
            continue

        mf = FIELD_RE.match(line)
        if mf:
            cur["fields"].append((mf.group("key").strip(), mf.group("value").strip()))
            continue
        if line.startswith("- ") and cur["fields"]:
            key, value = cur["fields"][-1]
            cur["fields"][-1] = (key, value + "\n" + line[2:].strip())
            continue

    return terms, patterns


COMMENT_META = "｜".join(["**%s**", "背景：%s", "来源：%s", "%s"])

ORIGIN_LABEL = {"quoted": "引述原话", "editorial": "编者视角"}


def render(term, out_root):
    fields = dict(term["fields"])
    order = ["人话", "英文释义", "英文来源", "中文来源"]
    body = []
    for key in order:
        if key in fields:
            body.append("## %s\n\n%s\n" % (key, fields[key]))
    for key, value in term["fields"]:
        if key not in order:
            body.append("## %s\n\n%s\n" % (key, value))

    body.append("## 评论区\n")
    if not term["comments"]:
        body.append("_还没有评论。欢迎在 Issue / PR 里补一条你的理解。_\n")
    else:
        for i, c in enumerate(term["comments"]):
            indent = "" if c["reply_to"] is None else "  "
            note = "待补出处" if c["origin"] == "quoted" else "——"
            body.append(
                "%s- " % indent
                + COMMENT_META % (c["who"], c["background"], ORIGIN_LABEL[c["origin"]], note)
            )
            for para in c["text"].split("\n"):
                body.append("%s  > %s" % (indent, para))
            body.append("")

    matter = {
        "id": term["id"],
        "term_zh": term["term_zh"],
        "term_en": term["term_en"],
        "category": term["category"],
        "verdict": term["verdict"],
        "verdict_note": VERDICT_LABEL[term["verdict"]],
        "aliases": term["aliases"],
        "related": [],
        "contributors": [],
        "updated": "2026-10-05",
    }

    cat_dir = CATEGORY_ID.get(term["category"], "misc")
    out_dir = os.path.join(out_root, cat_dir)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, term["id"] + ".md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(yaml_front(matter))
        fh.write("\n# %s %s\n\n" % (term["term_zh"], term["term_en"]))
        fh.write("\n".join(body))
    return path


def main():
    src = sys.argv[1]
    out_root = sys.argv[2]
    terms, patterns = parse(src)
    for t in terms:
        render(t, out_root)

    seen = {}
    for t in terms:
        seen[t["id"]] = seen.get(t["id"], 0) + 1
    dupes = {k: v for k, v in seen.items() if v > 1}

    if patterns:
        os.makedirs(out_root, exist_ok=True)
        with open(os.path.join(out_root, "_patterns.md"), "w", encoding="utf-8") as fh:
            fh.write(yaml_front({"type": "essay", "title": "几条串起来的规律"}))
            fh.write("\n# 几条串起来的规律\n\n")
            for p in patterns:
                fh.write("- %s\n" % p)

    n_comments = sum(len(t["comments"]) for t in terms)
    print("术语：%d 条" % len(terms))
    print("评论：%d 条（其中引述原话 %d 条）" % (
        n_comments,
        sum(1 for t in terms for c in t["comments"] if c["origin"] == "quoted"),
    ))
    print("章节：%s" % " / ".join(sorted({t["category"] for t in terms})))
    print("无评论的词条：%s" % ", ".join(t["term_zh"] for t in terms if not t["comments"]))
    if dupes:
        print("!! id 重复：%s" % dupes)


if __name__ == "__main__":
    main()
