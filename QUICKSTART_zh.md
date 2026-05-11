# 快速上手

10 分钟把你的知识库改造成 Sift 兼容。适配任何 Obsidian + Claude Code 配置。

这是"我读完 README 了,接下来到底要干什么"那一页。

> 🌐 Languages: [English](./QUICKSTART.md) · **简体中文**

## 准备

- 一个 Obsidian 知识库(或者任何你想整理的 markdown 文件夹)
- 装好 Claude Code(`claude` CLI) —— 不过这个规范跟任何 AI agent 都能用
- 10 分钟

## Step 1: 建 4 个卡片目录

在你的知识库里建 4 个必备目录:

```bash
cd /path/to/your/vault
mkdir -p skills/{research,debug,scripts,decisions}
```

如果你的知识库是新建的,顶层目录可以不同。**重点是 4 个卡片类型分开存放**,具体在什么路径下不强制。

## Step 2: 复制模板

把仓库里的模板文件拷到你知识库的 templates 位置:

```bash
# 在 sift 仓库根目录下
cp templates/*.template.md /path/to/your/vault/templates/
```

每次要 sink 第一张卡时,复制对应模板,重命名为 `YYYY-MM-DD-slug.md`,然后填进去。

## Step 3: 在知识库根目录加 `_CLAUDE.md` 和 `index.md`

这两个文件告诉未来的 AI session 你的知识库是什么、怎么组织的。最简版本:

```markdown
<!-- _CLAUDE.md -->
---
type: vault-manual
date: 2026-05-11
ai-first: true
audience: claude
---

## For future Claude

This vault follows the Sift spec (https://github.com/HuanNan520/sift).
Four card types in `skills/{research,debug,scripts,decisions}/`.
Frontmatter rules: see Sift SPEC.md §3.

Sink triggers:
- research: parallel-agent or multi-source investigation > 30 min
- debug: non-trivial problem fix > 5 min  
- scripts: reusable code > 10 lines
- decisions: trade-off you'd want the rationale for
```

```markdown
<!-- index.md -->
---
type: index
date: 2026-05-11
ai-first: true
---

## For future Claude

Catalog of cards. Read this first to know what exists without grepping everything.

### research/
(none yet)

### debug/
(none yet)

### scripts/
(none yet)

### decisions/
(none yet)
```

每次新建卡片时,这两个文件都要更新。

## Step 4: 告诉 Claude Code 这个知识库的存在

在你的 `~/CLAUDE.md`(全局那份)加一段,让任何新 session 都知道知识库在哪、怎么用:

```markdown
## My private SKILL library at ~/vault/

Before dispatching a research agent on a topic, first grep `~/vault/skills/research/`.
If a non-stale, non-triggered card exists, reuse the conclusion.
If a stale or triggered card exists, pass it to the new agent as baseline.

Sink a new card when one of these triggers fires:
- research: parallel-agent investigation > 30 min
- debug: > 5 min to solve a non-trivial bug
- scripts: > 10 lines, reusable
- decisions: trade-off with multiple viable options

Cards must follow https://github.com/HuanNan520/sift SPEC.md.
```

## Step 5: Sink 第一张卡

等下次你(或者 Claude 替你)解决了一件越过某个触发条件的事,然后:

1. 复制对应模板(`templates/debug.template.md` 等)
2. 重命名:`vault/skills/debug/2026-05-11-thing-you-solved.md`
3. 填 frontmatter + 各段内容
4. 更新 `vault/index.md` 加一行指向这张新卡

搞定。知识库现在有一张卡 + 一行索引。下次触发再来一次。

## 几周后会发生什么

具体能感觉到的变化:

- **Claude 会话起步更快了**。新对话里你问起以前做过的事,Claude 一 grep `skills/` 就能调出对应卡片。不用重新解释。
- **调研开始累积**。几周前跑过的调查,话题再出现时自动浮上来。`expires` + `recheck-trigger` 这套纪律意味着过期的结论会被标出来,不会被默默引用。
- **Debug 经验复利**。同一类 bug pattern(token 过期、文件 watcher 挂了、依赖版本不对)在不同项目里重复出现。sink 两三张之后,Claude 早期就能认出这个 pattern。
- **决策变得可读**。三个月后你想知道"当初为什么选 X 不选 Y",答案就在 `decisions/`,是当时上下文还新鲜时你自己写下的。

变化是渐进的 —— 不是"Claude 忽略我的笔记"突然变成"Claude 是我的第二大脑"。更像每段新对话都比上一段少 20-30% 的重新解释。

## 什么情况下别用 Sift

跳过这套规范如果:

- 你是重度个人日记作者。Sift 是给工程 / 调研知识用的,不是日常心情记录或意识流写作。
- 你的知识库是一个人用且永远只有一个人。这套纪律的回报要几个月才显现 —— 如果你一周后就弃用知识库,这点 overhead 不值。
- 你的"知识"主要是书签。Sift 想要的是带根因和重核条件的合成卡片,不是链接堆。
- 你想要团队 wiki。Sift 是单用户的。多用户知识库还是个开放问题。

## 可以抄的示范

从一个真正按这套规范跑的知识库里抽出来的三张真实卡片(私密细节已脱敏):

- [examples/research-example.md](./examples/research-example.md)
- [examples/debug-example.md](./examples/debug-example.md)
- [examples/decision-example.md](./examples/decision-example.md)

Sift 仓库本身也按这套规范跑自己:

- [meta/research/](./meta/research/) —— 作者做 Sift 时跑的调研
- [meta/decisions/](./meta/decisions/) —— 这一路上的设计决策
- [meta/debug/](./meta/debug/) —— 开发中解决的非平凡问题

这些是模板填出来的实例,不是另一套独立文档。读它们当作 Sift 卡片在真实负载下长什么样的 worked examples。

## 求助

- 提 issue:https://github.com/HuanNan520/sift/issues
- 完整规范:[SPEC_zh.md](./SPEC_zh.md)(中文) / [SPEC.md](./SPEC.md)(英文)
- 设计哲学:[README_zh.md](./README_zh.md)(中文) / [README.md](./README.md)(英文)
