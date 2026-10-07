---
id: logits
term_zh: logits
term_en: logits
category: AI 专用词
verdict: both_hard
verdict_note: 两边都不直观，只能记住它指什么
aliases: []
related: []
contributors: []
updated: '2026-10-05'
---

# logits logits

## 人话

模型最后一层吐出来的原始分数，还没换成概率，可正可负、大小不限。送进 softmax 才变成概率。

## 英文释义

log + -it，仿照 probit 造的词。原义是「对数几率」log(p / (1−p))。深度学习里泛化成「softmax 之前的分数」，和原义已不完全一样。

## 英文来源

伯克森 1944 年造词。

## 中文来源

「对数几率」，一般直接用英文。英文母语者看名字也猜不出意思。

## 评论区

- **吐槽役**｜背景：非本专业读者｜来源：编者视角｜——
  > 别纠结名字了，英文母语者也看不懂。记住「softmax 之前的分数」就够了。

- **BMS 老电工**｜背景：动力电池 / 嵌入式｜来源：编者视角｜——
  > 类比 ADC 原始码：还没换算成电压的那个数。logits 就是还没换算成概率的分数。
