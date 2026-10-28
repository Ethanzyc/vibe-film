# vibe-film

> 一个 Agent Skill：把一个「硬核概念 × 半夜想的那件事」做成 2-4 分钟**无口播知识情绪短片**。
> 全片由代码逐帧画出——确定性渲染、双语字幕、纯音乐、帧级音画对位。

![菌潮翻过三道抗性墙：能力展示镜（千级粒子梯度场）](docs/screenshots/hero-bacterial-tide.jpg)

分工铁律：**人管选题、逐镜表、方向确认和验收；agent 管对标逆向、写码渲染和自查返工。**
八个步骤、四道人工闸门、三个机器校验器——质量来自分镜表规格和验收闸门，不来自模型自由发挥。

## 出来的片子长这样

| | |
|---|---|
| ![粒子文字签名镜：2,900 粒子聚散成句，seeded 可复算](docs/screenshots/particles-typography.jpg) | ![界面仿真镜：像素级还原收藏夹与搜索框](docs/screenshots/library-ui.jpg) |
| 粒子文字签名镜（2,900 粒子，跨渲染序确定） | 界面仿真镜（真实感来自像素级还原） |
| ![微缩场景镜：线稿城市与人物剪影](docs/screenshots/wall-city.jpg) | ![粒子金字镜：金句大字与剪影观众](docs/screenshots/gold-title.jpg) |
| 微缩场景镜（剪影城市 + 人物） | 粒子金字镜（金句帧 + 献给观众） |
| ![单光源隐喻镜：雨巷、情理之线与光锥](docs/screenshots/light-cone.jpg) | ![几何道具镜：可手算的期望游戏](docs/screenshots/coin-wheel.jpg) |
| 单光源隐喻镜（光锥指向哪，观众看哪） | 几何道具镜（一个能手算的数） |
| ![具象锚点镜：fit 的本义是一件衣服的合身](docs/screenshots/coat-fit.jpg) | |
| 具象锚点镜（外行一眼认得的形象演概念） | |

全部帧为 1920×1080/30fps，画面只由时间 t 决定（`render(t)` 契约），同一帧跨渲染序像素级一致。

## 为什么不是「会动的 PPT」

同一个模型、同一套工具，一句话意图的分镜出「单主体+换字幕」，规格化分镜能追平对标成片的执行层——对照实验证明**成片差距 60-70% 在分镜规格**。vibe-film 把这个差距做成机制：

- **五问选题门**：写不出「献给每一个___的人」的选题不立项；第六问锚点测试——这颗概念的「微信气泡」是什么，找不到外行认得的具象形象就回选题层换
- **九列运动脚本级分镜**：时间/镜头类型/双语字幕/背景/中景/微文案/转场/情绪色逐镜锁死，不许一句话意图；机审（`check-storyboard.py`）FAIL 清零才准人审
- **对标帧逆向先于写码**：4-6 张同功能对标帧逐张看图，写成可执行规范，审美靠比对收敛
- **契约基准截图分段并行**：多段生产时共用 UI 像素级同构（纯文字契约已被实测证伪）
- **源码级对账**：`check-build.py` 把段代码字幕逐字与分镜表对账、白闪对白名单、CUES 事件对段时长——四个看帧的 QC 全漏掉的数字改动，源码审计抓得到
- **校验器自测**：改任何校验器先跑 `selftest.py`（17 例 planted-fault：好 fixture 必过、坏 fixture 必抓）——控制组不失败=检查器坏了

## 音画：先出声，画面迁就它

- 合成 BGM（`gen-audio.py`）：80BPM/Am-F-C-G/impact 钉转折秒，**吸气→静音→撞击**曲线——重拍前半拍全部让位，静音后的第一个声音是最重要的声音
- 真曲模式（`beats.py`）：谱通量+自相关量出节拍网格，分镜表时间列直接写拍线小数秒，机审校验边界落拍
- **CUES 事件层**（音画同表）：段码里一处声明 `CUES=[{t,sfx}]`，画面读它做点亮脉冲、音频层用同一份出声（`gen-sfx.py` 合成节点点亮/跳动/聚合），`--export-cues` 导出对接总装
- 量化自查（`check-audio.py`）：drop 呼吸凹陷/抬升、响度、倍频程平衡——AI 听不见，所以只信测量

## 工作流

```
0 环境检查（一次）
1 一次问清 ──────── 最多 5 问，能推断的就不问
2 选题门+逐镜表 ─── 五问门+锚点测试 → 三候选结构 → 九列表 → 🛑 人审
3 对标逆向 ───────── 逐张看对标帧，写可执行规范（先于写码）
4 音频先行 ───────── 🛑 BGM 选曲小样试听确认 → 生成，impact 钉转折秒
5 风格帧+样片 ───── 🛑 风格帧拼图 + 能力展示镜 3-8s 无声样片
6 分段渲染 ──────── 段1 先行+契约基准截图 → 其余段并行 → 段内自查≥2轮
7 总装 ──────────── concat → 混音 → loudnorm
8 验收+交付 ─────── 技术检查（程序判，FAIL 不能交付）+ 审片（写观察，用户终审）
```

修订成本路由表随 SKILL.md 下发：哪里错了从哪重来，能局部修不全局重渲。

## 安装

skill 就是一个含 `SKILL.md` 的目录，复制或软链进你所用的 agent skills 目录即可：

```bash
# 用户级（zcode）
ln -s /path/to/vibe-film ~/.zcode/skills/vibe-film
# 项目级（Claude Code / 按 AGENTS 约定读取的宿主）
ln -s /path/to/vibe-film <项目>/.claude/skills/vibe-film
```

### 依赖（分层，按用到哪层装哪层）

| 层 | 依赖 | 用于 |
|---|---|---|
| 分镜机审 + 源码对账（check-storyboard / check-build / selftest） | 仅 Python 3 标准库 | 每片必跑，零第三方 |
| 音频（gen-audio / gen-sfx / beats / check-audio / fit-grid / sfx_lib） | Python 3 + numpy + ffmpeg/ffprobe | 合成 BGM、真曲节拍网格、量化自查 |
| 渲染脚手架（assets/scaffold/） | Node 18+ + Playwright（`channel:'chrome'` 即系统 Chrome）+ ffmpeg | 逐帧导出、段构建 |
| 字体子集（gen-fonts.mjs） | curl + 可达 fonts.googleapis.com（需代理时 `export https_proxy`） | 出片前自托管字形 |

装完跑 `python3 scripts/selftest.py` 应全 PASS——这是校验器自身的健康检查。

## 结构

```
vibe-film/
├── SKILL.md                    # 边界 + 八步流程 + 闸门 + 修订成本路由表 + 判例
├── references/
│   ├── topic-gate.md           # 五问选题门 + 锚点测试（第六问：概念的「微信气泡」）
│   ├── storyboard.md           # 九列逐镜表 + 九型镜头菜单 + 渲染技术选型 + 反 AI 味扣分制
│   ├── reverse-audit.md        # 对标逆向 + 九项密度清单 + 讲解设计
│   ├── audio.md                # 选曲决策树 + 合成配方 + 落拍三公式 + CUES 事件层 + 量化自查
│   ├── review.md               # 验收分离口径 + 审片十项 + 版本留档/四态复验 + 处方笺
│   └── workflow.md             # 标准布局 + 契约截图制 + 工单模板 + 交付清单 + 工时基线
├── scripts/
│   ├── gen-audio.py            # 参数化 BGM 生成器（80BPM/impact 钉帧/吸气→静音→撞击）
│   ├── sfx_lib.py              # SFX 合成原语共享库（gen-audio/gen-sfx 单一实现防漂移）
│   ├── gen-sfx.py              # CUES 事件层 SFX 生成器（点亮/跳动/聚合）
│   ├── beats.py                # 真曲节拍网格检测（谱通量+自相关）
│   ├── check-audio.py          # drop 呼吸/响度/倍频程量化自查
│   ├── fit-grid.py             # 对标片剪点→节拍网格拟合
│   ├── check-storyboard.py     # 表层机审（列数/时间连续性/双语/落拍）
│   ├── check-build.py          # 源码级对账（COPY↔分镜表↔DUR↔白闪↔CUES，--export-cues）
│   ├── selftest.py             # 校验器 planted-fault 自测（17 例）
│   └── assemble.sh             # 多段总装（concat+混音+BGM×SFX 双轨+loudnorm+faststart）
└── assets/
    ├── scaffold/               # 最小渲染脚手架：render(t) 契约页（含规则 helper）/逐帧导出器/build.sh/字体子集器
    ├── contrast.md             # 正反例对照资产（指针化，越用越厚）
    ├── evals.md                # 端到端验收样例（expected=闸门证据清单）
    └── field-notes.md          # 实战笔记 + 被推翻规则销账（交付后回写，越用越厚）
```

## 已验证战绩

| 片 | 时长 | 生产 | 结果 |
|---|---|---|---|
| 90s 首跑验证片（图灵停机问题） | 90s | 两段并行 | 三项工艺未验证项全部关闭 |
| 2:15 首支正片（RAG×记忆重构） | 2:15 | 四段并行 | 已定时发布（2026-11-08） |

v1.3-v1.8 期间产线续跑六支以上：matter.js 真刚体倒塌 + WebGL 体积光（能力展示镜首战）、荀子性恶论多工具并行、执笔动画、千级粒子菌潮梯度场等主题；`check-build.py` 对账在真实项目里抓出三例「工单偏差未回写表」。本页截图均出自产线成片。

## 适用范围

| 用户想要 | 用这个？ |
|---|---|
| 无口播知识情绪片（概念×情绪，双语字幕，纯音乐） | ✅ |
| 哲学/科学概念的「凌晨一点」向短片 | ✅ |
| 口播讲解、逐句教学、教程录屏 | ❌ 口播产线（TTS 驱动） |
| 剪辑/混剪已有素材 | ❌ |
| 写实镜头为主（真人/实拍质感>50%） | ❌ 混合路线（生素材+代码动效），另议 |

时长：90-135s 单项目（1-4 段，每段 ≤45s）；竖屏不支持（构图原生横屏）。

## License

待定（见仓库讨论）。
