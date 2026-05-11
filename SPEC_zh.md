# Sift 规范

Version: 0.1.0 (draft)

> 🌐 Languages: [English](./SPEC.md) · **简体中文**

这份文档是规范的最终定本。README 是 elevator pitch,SPEC 是契约。

---

## 1. 知识库布局

一个 Sift 兼容的知识库,至少要在根目录有这 4 个文件夹:

```
vault/
├── research/      # investigations, with expiration
├── debug/         # solutions to non-trivial problems
├── scripts/       # reusable code snippets
└── decisions/     # project-level commitments
```

可选的并列文件夹(本规范不强制):

```
vault/
├── _CLAUDE.md     # vault operating manual for the AI
├── index.md       # catalog of all cards
├── log.md         # chronological log of structural changes
└── templates/     # blank card scaffolds
```

---

## 2. 沉淀触发条件

一段知识**只有越过下面其中一个门槛才能拿到一张卡**:

| 卡片类型 | 触发条件 |
|---|---|
| `research/` | 一次需要并行 agent、多源、或者超过 30 分钟的调查 |
| `debug/` | 一个非平凡问题,诊断 + 修复用了 5 分钟以上 |
| `scripts/` | 超过 10 行、以后还会再用、带非显然 flag 或 setup 的代码 |
| `decisions/` | 一个 trade-off,在 2 个或更多架构 / 流程方案之间选择,未来的你会想看到当初的理由 |

**没越过门槛的知识不沉淀。** 它被允许遗忘。

这是规范的核心。大多数知识库工具优化"捕获",Sift 优化**不捕获**。

---

## 3. Frontmatter 规则

每张卡片**必须**在顶部有 YAML frontmatter。

### 3.1 必填字段(所有卡片类型)

```yaml
---
type: research | debug | scripts | decisions
date: YYYY-MM-DD
tags: [hyphenated-english, 中文也可以, 日本語もok]
ai-first: true
---
```

**标签规则**:

- 用 hyphen 分隔,不含空格,不含特殊标点
- 推荐用小写 ASCII(跨知识库迁移更稳)
- **支持 CJK 字符(汉字 / 平假名 / 片假名 / 한글)** —— 多语言用户可以直接用母语写标签,不必转拉丁拼音
- 完整 regex:`^[a-zA-Z0-9一-鿿぀-ゟ゠-ヿ가-힯][a-zA-Z0-9一-鿿぀-ゟ゠-ヿ가-힯-]*$`

### 3.2 按类型的字段

#### `research/`(强制)

```yaml
---
type: research
date: YYYY-MM-DD
tags: [...]
ai-first: true
problem: one-line statement of the question
solution-summary: one-line statement of the conclusion
expires: YYYY-MM-DD          # default: date + 3 months
recheck-trigger:
  - specific condition 1
  - specific condition 2
---
```

`expires` 和 `recheck-trigger` 字段对 research 卡是不可妥协的。规范的核心就是:**研究的结论会衰减**,知识库应该知道自己的知识什么时候已经过期。

#### `debug/`

```yaml
---
type: solution
date: YYYY-MM-DD
tags: [...]
ai-first: true
problem: symptom as observed
solution-summary: one-line fix
---
```

卡片正文必须含这几个段:`## Problem`、`## Root Cause`、`## Solution`、`## Pitfalls`。看 [templates/debug.template.md](./templates/debug.template.md)。

#### `scripts/`

```yaml
---
type: script
date: YYYY-MM-DD
tags: [...]
ai-first: true
purpose: one-line statement of what the script does
---
```

卡片正文含代码、依赖、至少一个使用示例。

#### `decisions/`

```yaml
---
type: decision
date: YYYY-MM-DD
tags: [...]
ai-first: true
context: what situation forced the decision
choice: the option that was picked
---
```

卡片正文必须含 `## Options Considered`、`## Choice + Rationale`、`## Consequences`。

---

## 4. 写作硬规则

### 4.1 `## For future Claude` 起手段

每张卡都以一段 2-3 句的开场白起步,写给未来读它的 AI 看:

```markdown
## For future Claude

This card is about X. Read it when: [trigger conditions]. Skip it when: [non-triggers].
```

这段开场白存在的理由:**知识库是给 AI 检索设计的,不是给人读的**。未来 agent 加载知识库时,会扫每张卡的开场白决定要不要读全文。

### 4.2 实体一律用 wikilinks

正文里出现的每个人、项目、概念、命名决策,都要用 `[[wikilinks]]` 包起来:

> "We chose [[postgres]] over [[mongodb]] because [[ali]] argued for SQL composability." 

理由两条:
- 图谱视图(Obsidian 等工具)能看出关系
- 未来 agent 能 grep `[[postgres]]` 找全跟它相关的卡

### 4.3 外部信息一律标 recency

任何关于外部系统(某个库的版本、某个工具的行为、市场状态)的论断,都要带一个 recency 标记:

> "mcp-obsidian has 3.4k stars but has been untouched for 17 months (as of 2026-05)"

不标记,论断就会默默过期。

### 4.4 源 URL 行内、原样保留

来源在论断的位置标,不是文末:

> "The benchmark in [Karpathy's gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) shows that LLMs reading raw markdown outperform RAG retrieval for vaults under 500 notes."

URL 原样保留,这样从知识库 copy 出去仍能跑。

---

## 5. 工程纪律

这 4 条原则从软件工程偷过来,决定什么**不该**写:

### 5.1 Go/no-go gating

沉淀前先问:"未来再读一次的成本,是不是低于我现在想保存的价值?" 不清楚就跳过。一个有 100 张卡每张你都会再读的知识库,比一个 1000 张卡你都只瞄一眼的知识库有价值得多。

### 5.2 Anti-elaboration

短卡胜过长卡。沉淀是价值转移,不是写作练习。如果你发现自己在加段落只是因为"觉得该有这一段",停。

### 5.3 Value over process

别因为"我解决了一个问题"就 sink 一张 debug 卡。是因为**下一个**撞到这个问题的人(或者下一次的你)节省下来的时间,比读一次卡的成本高,才写。检验标准:你希不希望陌生人找到这张卡,觉得它救了自己一小时?

### 5.4 YAGNI

投机性知识("以后可能用得上")不写。等第二次再说。第一次发生是事件,第二次发生是 pattern。**只有 pattern 才配卡片**。

---

## 6. 关键使用协议

AI agent 用知识库回答问题时,**必须**对每张被引用的 research 卡执行这套协议:

1. 检查 `expires`。如果今天已过 `expires`,这张卡 *过期了* —— 不要直接引用。
2. 检查 `recheck-trigger`。如果有任何条件已触发,这张卡 *被触发了* —— 同样处理。
3. 如果过期或被触发,这张卡仍可以当 **baseline** 用 —— 但 agent 必须:
   - 在回答中说明来源已经老了
   - 要么重新做相关调查,要么明确标注"答案是 provisional 的"

这套协议防止 AI 知识库最常见的失败 mode:**用新调研的自信引用过期知识**。

---

## 7. Cache-first agent 行为

派一次新调查(并行 agent、web search、deep research)之前,agent **必须**:

1. 在 `research/` 文件夹 grep 相关关键词
2. 读到任何未过期、未触发的卡,直接用结论
3. 如果有过期或触发的卡命中

如果有过期或触发的卡命中,agent 可以派新调查 **但必须把旧卡当 baseline 上下文喂给新 agent**。这样防止重复从零做同一份调查。

---

## 8. 这份规范故意没说的

- **工具**。没有安装器、没有 daemon、没有 plugin。规范是契约,不是 runtime。
- **个人日记**。每日笔记、心情记录、idea 捕获 —— 不在范围。用任何你喜欢的工具。
- **多用户 / 团队知识库**。v2 问题。
- **特定 AI agent**。规范是 agent 无关的。本仓库例子用 Claude Code,但 Cursor / Cline / Codex / 自研 agent 都一样跑。
- **搜索基础设施**。对一个 markdown 文件夹的 plain grep 就是 baseline。如果你的知识库大到超过这个,你也就超过这份规范了。

---

## 9. 版本号

遵循 [Semantic Versioning](https://semver.org)。版本号在文件头部。

- MAJOR:对 frontmatter schema 或沉淀触发条件的破坏性变更
- MINOR:新增可选字段或新增卡片类型
- PATCH:澄清、示例、typo

v0.x 表示规范不稳定,v1.0 之前可能有变更。

---

## 10. 致谢

Sift 是作者从零设计的,提炼自一段时间内在生产环境跑 Claude Code + markdown 知识库的真实积累。规范受这些工作影响:

- **Andrej Karpathy 的 "LLM as compiler" 论点**([gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)) —— markdown 文本直接喂进 LLM context,在 ~500 笔记以下的知识库里比 RAG / 向量检索更稳
- **软件工程沉淀下来的工程纪律** —— `YAGNI`、`go/no-go gating`、`value over process`、`anti-elaboration`。Sift 的核心主张是:**知识管理应该跟代码享有同等工程纪律**,因为两者都会复利,都会衰减,都会惩罚不严谨的人。

如果你对 AI-vault 这领域不熟,先去读 Karpathy 那个 gist —— 它解释了为什么这整个范畴值得思考。
