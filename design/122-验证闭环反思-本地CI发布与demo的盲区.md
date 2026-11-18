# 122-验证闭环反思：本地测试、远端 CI、发布副本与 demo 的盲区

> 状态基线：2026-11-18。触发：远端 CI 在 Wellspring-Agent 报红，而 Windows 本地全绿——一次典型的"本地证据覆盖不到的环境"。
> 本轮不做新功能，只把这次故障的因果、修复与仍然存在的盲区写清。

---

## 1. 发生了什么

| 环境 | 结果 |
| --- | --- |
| Windows 本地（root） | pinned 套件 99 项全过 |
| Windows 本地（Wellspring 副本） | 99 项全过 |
| GitHub Actions（Linux, Python 3.11） | `python` 失败：`site_copy_drift` 三条 |
| 真实 Linux 检出（WSL + ext4，git clone 后 checkout） | **复现失败**，与 CI 一致 |

根因：`site/docs/16|17|18` 是构建时字节拷贝；Linux 检出时一边 LF、一边 CRLF，`repo_hygiene` 按字节哈希比较 → 误报 drift。Windows 文件系统不区分这两种换行，所以本地永远看不到。

---

## 2. 修复（三层）

1. **比较层**：`repo_hygiene` 对文本副本先归一换行再比较（二进制仍字节哈希）；检查关心内容，不关心检出转换。
2. **发布层**：`build_release` 同步 `demo/` 源；`repo_hygiene` 读 MANIFEST 的 release-owned 段，跳过"bundle README 与源 README 合法不同"。
3. **CI 层**：`python-full` 在缺少本地数据时**明确跳过**而不是红；advisory job 每次红会训练人忽略 CI。

---

## 3. 仍然存在的盲区（必须写下来）

1. **全量测试不在 CI 跑**：需要 `research_agent/web/data`、astradraw vendor 等本地数据；CI 现在跳过，意味着**这些测试的回归只能靠本地检出发现**。缓解：每月本地全量跑一次并记录日期/结果。
2. **字节哈希与 git 转换冲突**：MANIFEST / artifact sha256 对 CRLF/LF 敏感；只要仓库存在文本文件，跨平台 checkout 就可能变化。规则：**哈希对象只用于二进制或构建产物；文本一致性用归一化比较**。
3. **release-owned 文件是"合法分叉"**：README 等在 bundle 与源仓库不同；必须由 MANIFEST 标记，否则要么误报 drift，要么放过真漂移。
4. **CI 绿灯不等于系统正确**：它只证明 pinned 子集在 Linux/Py3.11 通过；demo 上的能力指标（held-out 12/14、+1.25）不在 CI 里，也不能靠 CI 证明。
5. **本地文件系统保真度**：Windows 大小写不敏感、换行宽松；涉及路径/大小写/换行的检查必须在 Linux 检出上验证。

---

## 4. 与 demo/论文表述的关系

- demo 不应写"CI 全绿"这类会过期的状态；可以在**生成式面板**里由构建脚本读取最近一次 run 的 commit hash 与结果（未做，属 roadmap）。
- 论文/组会讲"验证"时，应区分：本地测试（可复跑）、远端 CI（环境证据）、发布副本（打包一致性）、真实运行（研究读数）——四者不能互相替代。

---

## 5. 验收

| 项 | 结果 |
| --- | --- |
| 真实 Linux 检出 | pinned 套件 99 项 OK（7 skip） |
| research-agent CI（fff2cc3） | ci 全绿：python / python-full / release-surface / web |
| Wellspring CI（dbcb380） | ci 全绿：同上 |
| release 一致性 | content_drift 0；repo_hygiene 0 blocker（Linux 检出下亦通过） |

---

## 6. 一句话

这次红不是"代码错了"，而是**本地证据的观测面不够**：Windows 看不出换行差异，本地副本看不出 CI 环境。修复的意义不是让 CI 变绿，而是让"本地—远端—发布—demo"四层验证的边界变得明确、可复述。
