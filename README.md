# vibe-film · 哲学内核驱动的无口播知识片生产

> 一个 Agent Skill：把「硬核概念 × 半夜想的那件事」做成 2-4 分钟无口播知识情绪短片。代码逐帧渲染、双语字幕、纯音乐，全程确定性可复算。

## 它和社区同类 skill 的差异

市面上同类（awesome-claude-video-skills 收录的 340 个）几乎全部押在**渲染工艺**上；vibe-film 的核心资产在**内容层**：

- **五问选题门**：写不出「献给每一个___的人」的选题不立项（凌晨一点测试/法则测试/命名测试/反转测试/指令测试）
- **九列运动脚本级分镜**：同模型同工具的对照实验证明，成片差距 60-70% 在分镜规格——本 skill 强制九列逐镜表，不许一句话意图
- **对标帧逆向**：审美靠与对标帧并排比对收敛，不靠模型自由发挥
- **契约基准截图分段并行**：多段生产时共用 UI 像素级同构（纯文字契约已被实测证伪）
- **源码级对账**：check-build.py 把段代码字幕逐字与分镜表对账、白闪对白名单、DUR 对总时长（学 anything2explainer selfcheck：像素 QC 的盲区由源码审计补）

## 结构

```
vibe-film/
├── SKILL.md                    # 边界 + 八步流程 + 闸门 + 修订成本路由表 + 判例
├── references/
│   ├── topic-gate.md           # 五问选题门 + 锚点测试（第六问：概念的「微信气泡」）
│   ├── storyboard.md           # 九列逐镜表 + 九型菜单（含具象锚点帧）+ 双层视觉词汇 + 反 AI 味扣分制
│   ├── reverse-audit.md        # 对标逆向（学什么/不学什么）+ 九项密度清单 + 讲解设计
│   ├── audio.md                # BGM 选曲决策树 + 合成配方 + 音效对照表 + 落拍三公式 + 默认味清单 + 量化自查
│   ├── review.md               # 验收分离口径 + 审片十项 + 版本留档/四态复验 + 处方笺
│   └── workflow.md             # 标准布局 + 契约截图制 + 工单模板 + 交付清单 + 工时基线
├── scripts/
│   ├── gen-audio.py            # 参数化 BGM+音效生成器（80BPM/Am-F-C-G/impact 钉帧/吸气→静音→撞击）
│   ├── sfx_lib.py              # SFX 合成原语共享库（gen-audio/gen-sfx 单一实现防漂移）
│   ├── gen-sfx.py              # CUES 事件层 SFX 生成器（节点点亮/跳动/聚合，消费 export-cues JSON）
│   ├── beats.py                # 真曲节拍网格检测（谱通量+自相关，beats.json，只给真曲用）
│   ├── check-audio.py          # drop 呼吸/响度/倍频程量化自查（dip≥4dB/lift≥1dB 判据）
│   ├── fit-grid.py             # 对标片剪点→节拍网格拟合（BPM 候选 + 每段占几步）
│   ├── check-storyboard.py     # 表层机审（列数/时间连续性/双语/字幕时长/金句献给门槛/--grid 节拍网格）
│   ├── check-build.py          # 源码级对账（段码 COPY↔分镜表↔DUR↔白闪白名单↔CUES 词表越界↔字面量扫描，--export-cues）
│   ├── selftest.py             # 校验器 planted-fault 自测（17 例：好 fixture 必过、坏 fixture 必抓）
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
| 2:15 首支正片（RAG×记忆重构） | 2:15 | 四段并行 | 已定时发布 B 站（2026-11-08） |

v1.3-v1.6 期间产线续跑六支以上：matter.js 倒塌+WebGL 丁达尔（能力展示镜首战）、荀子性恶论多工具并行、执笔动画等主题（各自状态见各片实验目录台账；正片 check-build 对账抓出三例「工单偏差未回写表」判例）。

**v1.8.0（2026-10-27）CUES 事件层（音画同表，C 档）**：段码 timeline.js 的 `CUES=[{t,sfx}]` 一处声明、画面（scaffold `cuePulse()` 点亮脉冲）与声音（`gen-sfx.py` 事件音效轨）两边消费；`check-build.py` 校验 CUES 越界/词表并 `--export-cues` 导出；`assemble.sh` 支持 `SFX=` 第三轨混音；SFX 合成原语抽 `sfx_lib.py` 共享库（gen-audio 改引用，md5 逐字节回归验证）。判例：promo 片的节点点亮（bell=点亮/tick 上行阶梯=密度即推进/shimmer=全亮）。**v1.7.0（2026-10-27）音画卡点**：自 motion-showreel 迁入三件量化工具（`beats.py` 真曲节拍网格 / `check-audio.py` drop 呼吸与响度判据 / `fit-grid.py` 对标片剪点网格）与落拍三公式、音效对照表、声音默认味清单；gen-audio.py 改为「吸气→静音→撞击」曲线。**拍板定版：真曲片分镜时间列基准 = beats.py 检测网格**，`check-storyboard.py --grid <beats.json>` 校验边界落拍。判据与边界见 audio.md；演示判例为实验目录的 `演示-音画卡点v2.md`（真曲卡点 A/B：同曲同画只差网格相位）。

## 安装

skill 就是一个含 `SKILL.md` 的目录，复制或软链进你所用的 agent skills 目录即可：

```bash
# 用户级（zcode）
ln -s /path/to/vibe-film ~/.zcode/skills/vibe-film
# 项目级（Claude Code / 按 AGENTS 约定读取的宿主）
ln -s /path/to/vibe-film <项目>/.claude/skills/vibe-film
```

## 依赖（分层，按用到哪层装哪层）

| 层 | 依赖 | 用于 |
|---|---|---|
| 分镜机审 + 源码对账（check-storyboard / check-build / selftest） | 仅 Python 3 标准库 | 每片必跑，零第三方 |
| 音频（gen-audio / gen-sfx / beats / check-audio / fit-grid / sfx_lib） | Python 3 + numpy + ffmpeg/ffprobe | 合成 BGM、真曲节拍网格、量化自查 |
| 渲染脚手架（assets/scaffold/） | Node 18+ + Playwright（`channel:'chrome'` 即系统 Chrome）+ ffmpeg | 逐帧导出、段构建 |
| 字体子集（gen-fonts.mjs） | curl + 可达 fonts.googleapis.com（需代理时 `export https_proxy`） | 出片前自托管字形 |

装完跑 `python3 scripts/selftest.py`（17 例 planted-fault 自测）应全 PASS——这是校验器自身的健康检查，不依赖 numpy/ffmpeg。
