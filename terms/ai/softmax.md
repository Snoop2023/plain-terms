---
id: softmax
term_zh: softmax
term_en: softmax
category: AI 专用词
verdict: accurate
verdict_note: 中文其实准，知道字的本义就懂
aliases: []
related: []
contributors: []
updated: '2026-10-05'
---

# softmax softmax

## 人话

把一组任意大小的分数变成概率：全变成正数，加起来等于 1。分最高的拿到最大的概率，但不独占，其他选项也留一点机会。

## 英文释义

soft「柔和的」+ max「取最大」= 柔和版的取最大。普通的 max（hard max）只留最大那个、其余全扔；softmax 是平滑过渡的版本。

## 英文来源

Bridle 1990 年命名。

## 中文来源

一般不翻译，直接用英文。英文自带解释。

## 评论区

- **吐槽役**｜背景：非本专业读者｜来源：编者视角｜——
  > 难得一个名字自带说明书的词。max 是赢家通吃，softmax 是赢家多拿，其他人也分一点。

  - **炼丹师**｜背景：AI 训练 / 工程｜来源：编者视角｜——
    > 为什么要先取指数？两个原因：保证全是正数；把分数上的小差距放大成概率上的明显差距。
