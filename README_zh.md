<p align="center">
  <img src="./.github/social-preview.png" alt="Sift — knowledge vaults that think before they store" width="100%" />
</p>

<p align="center">
  <a href="./README.md"><img src="https://img.shields.io/badge/lang-English-blue" alt="English"></a>
  <a href="./README_zh.md"><img src="https://img.shields.io/badge/lang-简体中文-red" alt="简体中文"></a>
</p>

<p align="center">
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License"></a>
  <a href="./CHANGELOG.md"><img src="https://img.shields.io/badge/spec-v0.1.0--draft-orange.svg" alt="Draft v0.1.0"></a>
  <a href="./QUICKSTART_zh.md"><img src="https://img.shields.io/badge/快速上手-10%20min-green.svg" alt="10-min quickstart"></a>
  <a href="./SPEC_zh.md"><img src="https://img.shields.io/badge/spec-machine--readable-blueviolet.svg" alt="Machine-readable spec"></a>
</p>

# Sift

一份给 AI-辅助知识库的规范,主张**沉淀之前先思考**。

> **第一次看?** 跳到 [QUICKSTART_zh.md](./QUICKSTART_zh.md) 看 10 分钟上手。想先看设计哲学就留在这页。

> 当下大多数 AI-first 知识工具都是"急切的学习者":什么都吸收、什么都相信、让知识库无限增长。Sift 走相反路线 —— **一段知识只有越过明确的门槛,才能在知识库里占一个位置**。

这是规范,不是工具。它定义:

- 每个知识库都该分开存放的 4 类卡片
- 给 AI-first 检索用的 frontmatter 规则(含关键使用标记)
- 量化的沉淀触发条件 —— 什么样的内容值得保存
- 4 条工程纪律 —— 决定什么内容**不该**被写下来

跟任何知识库工具(Obsidian、纯 markdown 文件夹、Logseq)+ 任何 AI agent(Claude Code、Cursor、自研脚本)配合使用。规范是工具无关的。

---

## 这东西为什么存在

"second brain" / AI-first 知识库这个领域 converge 在一个假设上:**越多越好**。把每篇文章、每段 transcript、每段对话都丢进知识库。让 AI 自己整理。让知识"复利"。

实际效果是:

- **虚假信任** —— 半年前的旧调研被当成权威重新引用
- **重复劳动** —— agent 反复重做同一份调查,因为没有缓存纪律
- **笔记肿胀** —— 知识库长得比读者(人或 AI)能浏览的速度快得多
- **没有工程反射** —— 每个问题都变成一次 `/save`,不管有没有价值

Sift 是这样一个产物:**一个长期用过 `go/no-go gating`、`YAGNI`、`anti-elaboration` 的工程师**,看着 second-brain 领域问自己:*如果把同样的纪律搬过来,知识管理会长成什么样?*

---

## 4 类卡片

Sift 兼容的知识库把知识分成 4 个互斥的目录:

| 目录 | 装什么 | 沉淀触发条件 |
|---|---|---|
| `research/` | 带来源、结论、过期日期的调查 | 一次并行 agent 或者多源调研,值得缓存 |
| `debug/` | 非平凡问题的解决方案,含根因 + 复现步骤 | 一次 debug 用了 5 分钟以上 |
| `scripts/` | 可复用代码片段(bash、python、配置),带使用示例 | 超过 10 行、以后还会再用的代码 |
| `decisions/` | 项目级架构 / 流程承诺 | 一个 trade-off,你希望以后记得当初的理由 |

任何不属于这 4 类的东西 **不沉淀**。它留在对话里,用一次,然后被允许遗忘。

---

## 4 条工程纪律

这几条决定什么 **不该** 写下来:

1. **Go/no-go gating** —— 沉淀前先问"这值不值得未来再读一次?"。不清楚就不写。
2. **Anti-elaboration** —— 短卡胜过长卡。沉淀是价值转移,不是写作练习。
3. **Value over process** —— 别因为"我解决了一个问题"就 sink 一张 debug 卡。是因为"下次有人撞到同样的问题,这张卡能救他一小时"才写。
4. **YAGNI** —— 投机性知识("以后可能用得上")不写。等第二次出现再说。

这 4 条直接从软件工程偷来。Sift 主张的是:**知识管理应该跟代码享有同等纪律** —— 因为两者都会复利,都会衰减,都会惩罚不严谨的人。

---

## 关键使用:知识会过期

Sift 跟其他 AI-vault 规范最不一样的特征:

**每张 research 卡都带一个 `expires` 日期和一份 `recheck-trigger` 列表。**

```yaml
---
type: research
date: 2026-05-10
expires: 2026-08-10   # default: date + 3 months
recheck-trigger:
  - upstream repository hits 5k stars
  - vault grows past 500 notes
  - the underlying tool ships a 1.0 release
---
```

未来 AI session 读到这张卡时,约定是:

- **`expires` 之前 + 没有触发条件满足** → 直接复用结论
- **过了 `expires`,或者某个触发条件满足** → 重新做调查,但**把旧卡当 baseline 喂给新 agent**,告诉它:*"之前的结论是 X,确认是不是还成立 + 找一下从那之后有什么新进展"*

这一条规则,防止 AI 知识库最常见的失败 mode:**用新调研的自信引用过期知识**。

完整 frontmatter 规则、沉淀触发条件细节、worked examples,看 [SPEC_zh.md](./SPEC_zh.md)。

---

## Sift 不是什么

- **不是工具**。没有安装器、没有 runtime、没有 daemon。它是一个你按手或按 agent 应用的规范。
- **不是知识库工具的替代品**。用 Obsidian、Logseq、纯文件夹 —— 随你。Sift 加的是纪律,不是基础设施。
- **不是给个人日记用的**。每日笔记、心情记录、随手 idea 捕获 —— 那些放别处。Sift 是给"以后会在压力下被重新读"的知识用的。
- **不是给团队用的**(暂时)。多用户知识库是 v2 问题。

---

## 示范

从一个正在按这套规范跑的知识库里抽出来的三张真实卡片(项目名 / 路径 / API 引用已脱敏)。它们展示每类卡片在真实负载下长什么样,不是空模板:

- [examples/research-example.md](./examples/research-example.md) —— Obsidian + Claude Code 生态调研(`expires` + `recheck-trigger` 在实战中怎么用)
- [examples/debug-example.md](./examples/debug-example.md) —— Obsidian 在 WSL `\\wsl.localhost\` 路径下 EISDIR 崩溃,根因追到 9P 协议
- [examples/decision-example.md](./examples/decision-example.md) —— 把个人知识库重新定位为 Claude-facing 的 SKILL 库,带 steelmanned 否决方案

每张 example 都链接到另外两张 —— 这就是 4 文件夹布局产出"图"而不是"孤立文档"的实战体现。

## Dogfood: 这个仓库自己跑这套规范

Sift 仓库本身也是个 Sift 知识库。`meta/` 目录里有几张卡片,记录 Sift 自身的开发过程,完全按这份规范写:

- [meta/research/2026-05-11-naming-com-exhausted.md](./meta/research/2026-05-11-naming-com-exhausted.md) —— 选项目名时跑的 .com 搜索,200+ 候选,4 个可买,全否,附"为什么 4 字母可读的 .com 在 2014 年就被注册光了"的分析
- [meta/decisions/2026-05-11-launch-not-perfect.md](./meta/decisions/2026-05-11-launch-not-perfect.md) —— v0.1.0 是怎么在 idea 形成的当晚就 launch 的;选项集 / 理由 / 后果 / 重新评估触发条件
- [meta/debug/2026-05-11-cdp-social-preview-upload.md](./meta/debug/2026-05-11-cdp-social-preview-upload.md) —— 怎么通过 Chrome DevTools Protocol 把 social preview banner 上传的(GitHub 没有 API 做这事),5 个坑 + 实测可行的做法

读它们当 worked examples,看这套规范在真实负载下产出什么样的东西。这几个文件本身也能用 `./lint.sh` 校验(在仓库根目录跑一次)。

## 规范是机器可读的

Frontmatter 合规可以程序化校验:

```bash
# 在仓库根目录
./lint.sh /path/to/your/vault
```

Schema 在 [spec/sift.schema.yaml](./spec/sift.schema.yaml)(JSON Schema draft-2020-12)。可以配合任何遵守标准的 validator(`yamllint`、`ajv` 等)使用,或者直接跑 `./lint.sh` 做快速检查。

依赖:`python3`、`pyyaml`、`jsonschema`。

## 状态

工作中的草稿。规范从一个真实跑过这套原则的个人知识库里抽出来。现在公开是为了邀请评审、批评、采纳。

> **项目不在于成熟,而在于出现** —— putting it out is more important than making it perfect.

欢迎通过 pull request 贡献。

---

## License

[MIT](./LICENSE)
