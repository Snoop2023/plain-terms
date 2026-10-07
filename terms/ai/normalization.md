---
id: normalization
term_zh: 归一化
term_en: normalization
category: AI 专用词
verdict: misleading
verdict_note: 中文有歧义或误导，先看英文
aliases: []
related: []
contributors: []
updated: '2026-10-05'
---

# 归一化 normalization

## 造词现场

要处理的问题是：一层的数尺度忽大忽小，往后传就越来越不稳，怎么把尺度统一。名字借 normal「标准的」—— 使符合标准。中文借「归一」：归到一个统一尺度。具体做法有好几种（缩到 0~1、调成均值 0 方差 1、让一组数加起来等于 1），看到这个词先问是哪一种。

## 人话

把一组数缩放到统一的尺度。具体缩成什么样看上下文，常见三种：缩到 0~1；调成平均 0、方差 1（BatchNorm、LayerNorm 就是这种）；让一组数加起来等于 1，变成概率（softmax 就是这种）。

## 英文释义

normal「标准的」→ normalize「使符合标准」。

## 英文来源

拉丁 *norma*「直角尺」，和 norm（范数）同根。

## 中文来源

归为「一」个统一尺度。⚠️ 英文本身就宽泛，看到这个词要问一句：是哪一种归一化？

## 评论区

_还没有评论。欢迎在 Issue / PR 里补一条你的理解。_
