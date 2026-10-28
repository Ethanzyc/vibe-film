# 音频（Step 4）：选曲规则 + 合成 + 音效

## 选曲决策树（用户已授权按此执行，结论记进台账供 A/B 归因）

1. **默认底座 = 合成曲**（scripts/gen-audio.py）：版权干净、impact 钉转折帧、时长自由
2. **赛道签名曲《We Never》(EEYUH! x Fluxxwave, 0.9x)**：选题属宇宙/哲学/认知/时间类疏离宏大向时启用；**连续两支不用同一首**
3. **《Midnight Rush》**：We Never 之后的差异化替代（人工试听拍板后启用）
4. **の小曲系**（熵增の/Claude の/REVENGE）：选题匹配时先检索查证原曲名+音源，再请用户试听；查证不到回落合成曲
5. **硬约束**：音源只走正版渠道自行处理（ffmpeg 变速），不从二创视频扒轨；B 站定时投稿上限 14 天与版权风险互不影响

## 合成曲配方（gen-audio.py，参数化）

- 80 BPM，小节=3s；和弦走向 Am-F-C-G 循环（后半段加亮）；55Hz drone；bar thumps（转折小节重音双击）；五声音阶 shimmer（seeded）；转折点前 swell
- 参数：`--dur 135 --impacts 9,45,69,102 --heavy 102 --riser 99 --swells 45,69,102,123`
- impact=90→38Hz 扫频+噪声气口；whoosh=亮度上升的带通噪声（**峰在 0.72×dur，置于撞击前 0.45s−0.72×dur，呼吸窗起点**）；riser=指数升频、**撞击前 0.5s 收完**（内部 0.3s 快淡出）
- **吸气→静音→撞击曲线**（2026-10-27 v2，《伪》判例）：每个 impact 前 0.55s 铺垫压 ~10dB、撞击后 0.25s 放回——撞击是静音后的第一个声音。旧版 whoosh 峰在切点前 0.35s 且铺垫不停，三处转折全部测出「没有呼吸」（见下「量化自查」）
- 输出 wav→mp3 192k；响度在总装统一 loudnorm（I=-15 TP=-1.5）

## 无口播片的节奏铁律

- 没有人声，节奏全靠音乐撑：**字幕切换必须落在重拍上**（切点=3s 小节线；真曲=beats.py 网格拍线）
- 画面白闪事件按 impact 秒渲染（音频先行生成，画面照着钉）
- 最重一击留 0.15s 声音留白（黑场同步）

## 落拍三公式（2026-10-27 自 motion-showreel 工艺迁入）

1. **揭开的那一帧落在拍上**。转场若从拍点起播，新画面要过几帧才露出，观众读到「声音先到、画面后到」。倒着排：先定新画面在转场进行到哪个比例（reveal）首次露出——擦除≈0、光圈≈0.3——**转场起点 = 拍点 − reveal × 转场时长**。拍点那一帧要有整屏看得出的变化；镜头冲击（放大 2-4% 再弹回）加在整个舞台上，新旧两层一起冲
2. **whoosh 峰值对切点 / impact 落动作帧**。whoosh 最响点在其时长的 ~0.72 处，放置 = 事件秒 − 0.72 × 时长；impact 正好落在白闪帧。两者别叠在同一点：转折既有 whoosh 又有 impact 时，whoosh 是落点前的吸气（峰在呼吸窗起点），impact 是落点本身
3. **drop 前留呼吸**。用「吸气→爆发」曲线时，重拍前至少半拍铺垫（鼓/铺底/riser 全部）让位，静音后的第一个声音必须是全片最重要的声音之一。不要用这条曲线的重拍（如收尾定格）不必硬做，从 drops 清单里去掉即可

## 音效对照表（画面动作→音效，材质要对得上）

| 画面动作 | 音效 |
|---|---|
| 白闪转折 / 反色 / 落版 | impact（heavy 用大号双击），铺垫按呼吸窗让位 |
| 转场前的甩镜 / 穿越 | whoosh（峰按公式对位） |
| 字幕弹出 / 元素出现 | pop（音高随元素大小：大低小高）/ mallet 短音 |
| 数字跳动 / 计数 | tick（太密就隔几次一个） |
| 粒子聚合 / 金句点亮 | shimmer / 高音区钟琴 |
| 点击 / 吸附 / 开关 | click / rim |
| 蓄力 / 吸气 | riser（长度=到落点为止，提前收口留呼吸） |
| 消散 / 退场 | downlifter / 反镲 |

密度由风格定：极简片几乎每个动作有声、抽象片可能一个没有。内置音色是素材不是成品：改参数/换种子/叠两层，别原样用默认值。

## 事件层 SFX（C 档，2026-10-27 制作人拍板；判例 ai-studio-promo）

BGM 骨架（Step 4）只管转折 impact；**镜头内的事件音效**（节点点亮、数字跳动、卡片入光、金句点亮）走 CUES 事件层——音画同表，一处声明两边用：

```js
// timeline.js（段真相源，画面与声音同读）
export const CUES = [
  { t: 0.12, sfx: 'bell' },                       // 首星点亮
  ...Array.from({length: 16}, (_, i) => ({ t: 1.3 + i * 0.575, sfx: 'tick' })),  // 接力点亮
  { t: 10.4, sfx: 'shimmer' },                    // 全亮
  { t: 44.3, sfx: 'impact', visual: 'white flash' },  // 落版（visual 字段=白闪白名单）
];
```

工作流：**Step 6 段码写 CUES**（画面用 `cuePulse(t, CUES, 'tick')` 做点亮脉冲）→ **Step 7** `check-build.py <项目> --export-cues audio/cues.json`（审计+导出同一解析器：t 超段时长 FAIL、未知 sfx 词 WARN）→ `gen-sfx.py --cues audio/cues.json --dur <总秒> --out audio/sfx.wav` → `SFX=audio/sfx.wav sh scripts/assemble.sh …`（混在 BGM 底上，SFX_GAIN 默认 0.9）。

- 词表（sfx_lib.py 单一实现，gen-audio/gen-sfx 共用）：impact/big_impact/boom/whoosh/riser/downlifter/bell/tick/pop/click/swipe/shimmer。whoosh 峰对位公式内建（放置 = t−0.72×dur）；cue 可带 `gain/pan/note` 覆盖缺省
- **ai-studio-promo 判例（点亮密度=推进感）**：61 星接力点亮 = 16 组 tick 沿音阶上行（每 4 个加一记音阶 bell、gain 随进度 0.2→0.33 渐强、pan 交替）——「密度即推进」；bell=点亮、tick=知识星、shimmer=全亮/手机升起、impact+crash 柔配=落版。重音只给最重要的 1-2 处（「每个重拍都 impact」是默认味，见上节）
- 事件密度纪律：tick 类连发太密就隔几次一个（数字跳动判例）；一段内同类事件音色统一，别每镜换

## 声音的默认味（自 motion-showreel §12 迁入；换配方时对照）

没有方向时合成配乐会收敛成同一首歌：A 小调 i-VI-III-VII（**Am-F-C-G——现行合成曲配方就是这条基线**）、100-128 BPM 四踩、每个重拍 impact+crash、落版=钟声+shimmer 长尾、锯齿 pad 万能铺底、所有 bus 都侧链。不是不能用，是不要不假思索地用：**新片换配方时，至少在调式/律动/配器/曲线里换掉两项**（除非延续系列统一）。例外：风格本身如此（synthwave 就该四踩）时它是签名不是默认味。

戏剧曲线菜单（每支片选一条，别只用第一条）：吸气→爆发 / 累加（层层进，高潮是"全部都在"）/ 抽空（突然只剩一件乐器，抽空即记忆点）/ 波浪 / 一问一答 / 音画同形（音高跟运动走）/ 单线条 / 拟音主导 / 倒放。

## 量化自查（AI 听不见，所以只信测量；三工具均在 scripts/）

```bash
python3 scripts/check-audio.py <BGM或成片> --drops 30,60,90 --bpm 80 --out qa/audio [--premix]
python3 scripts/beats.py <真曲> --out audio/beats.json [--bpm 96] [--shift 0.5]
python3 scripts/fit-grid.py <对标视频> --out qa/grid.json
```

- **check-audio.py（impact 片总装前后各跑一次）**：量每个 drop 重拍前半拍比前一小节低多少（**<4dB=WARN 没有呼吸**，铺垫没让位或 riser 太响）、重拍抬升是否 ≥1dB；外加响度（−15±1.5 LUFS）、真峰值（≤−1.5 dBTP）、倍频程平衡（轰头/单薄/发闷/刺耳四类 WARN，通用判据，风格性偏移记台账说明即可）、意外静音段。`--premix` 口径：gen-audio 直出 BGM 响度低于目标、mp3 解码真峰值过冲都属预期（总装链路负责），只提示不 WARN
- **beats.py（只给真曲用）**：选曲定为真曲后**先跑（在写分镜表之前，第 2 步前）**，得到 BPM/拍点/下拍/每小节能量/drops；**分镜表时间列基准 = beats.json 拍线（2026-10-27 制作人拍板「要B」，演示判例：同曲同画只差网格相位，对拍段律动锁死、不对拍段肉眼可见漂移）**，时间列写小数秒，机审 `check-storyboard.py <表> --dur <总秒> --grid audio/beats.json`（边界距最近下拍超容差 FAIL，容差默认 0.06s≈2 帧，首镜 0 豁免）。检测可能锁半速/倍速——与已知 BPM 不符加 `--bpm`，拍点在反拍加 `--shift 0.5`。**边界判例（2026-10-27）**：无鼓点的环境合成曲没有可检测节拍（假 onset 来自正弦拍频），不要对它跑；合成曲网格由 gen-audio 构造已知，`--bpm 80` 只做相位核对
- **fit-grid.py（对标逆向时用）**：量参考片剪点落在什么步长网格上（4/4 内点才算有网格）；输出 BPM 候选与「每段占几步」（数字递减=切速加快拍速不变）。有曲子时与 beats.py 交叉验证：画面网格与节拍网格应一致

## 总装响度配方（2026-10-26 ×5 连跑实测，impact 瞬态片必读）

- 单遍 `loudnorm=I=-15:TP=-1.5:LRA=11`（dynamic）**控不住 impact 瞬态真峰值**（实测成片 TP +0.48）；`linear=true` 在 TP 预测超标时会**静默降级回 dynamic**——不要信返回码，总装后必须对成片复测 loudnorm
- 配方：两级 alimiter(attack=1ms) + loudnorm——前置钳瞬态、后置收真峰值：

  ```bash
  -af "alimiter=limit=0.5:attack=1:release=25:level=disabled,\
  loudnorm=I=-15:TP=-1.5:LRA=11,\
  alimiter=limit=0.52~0.62:attack=1:release=25:level=disabled"
  ```

  收尾限幅按各片音频瞬态在区间内试（每收 0.05 ≈ TP −0.5~0.7dB），复测不达标再收；五连跑实测 0.52-0.62 全部达标（I −15.2±0.2 / TP −2.0~−2.9）。默认 alimiter 的 attack=5ms 抓不住毫秒级 impact 瞬态，必须显式 attack=1ms
- `gen-audio.py --out` 必须传**绝对路径**（相对路径会把输出目录拼错）

## 耳缘策略（长期）

合成曲每支片重复同一旋律 motif（4-8 音，片头片尾各一次）——自建「耳缘」，对标开智小曲的巴甫洛夫效应；真曲（A/B 档）有现成耳缘但版权在别人手里。
