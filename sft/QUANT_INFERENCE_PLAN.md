# 量化推理对照实验设计（Q 系列，Qwen3.5-2B）

负责人：朱衍（Derek）。设计与分析：Claude。执行：负责人在 RunPod 上运行。最后更新：2026-10-22，Claude。

范围：负责人决定（D12）量化实验只用 **Qwen3.5-2B**，不再包含 4B。已完成的 4B 零样本基线（F1 0.923）仅作历史参考，不参与量化对照。

## 1. 要回答的问题

| 编号 | 问题 | 主要指标 |
| --- | --- | --- |
| RQ1 | 不同量化方式对本任务的精度影响有多大？损失落在哪些字段、哪些写法上？ | 字段级 F1、意图准确率、schema 合规率；按字段 / style_tag 拆分 |
| RQ2 | 能换来多少速度和显存？ | 单条延迟（TTFT、TPOT、端到端）、批量吞吐、权重显存、KV cache 容量 |
| RQ3 | 校准方法和校准数据重要吗？ | 同为 W4A16：RTN vs GPTQ vs AWQ；领域内校准 vs 通用校准 |
| RQ4 | 延迟里，量化和“缩短输出”哪个贡献更大？ | 格式化 JSON vs 紧凑 JSON 的延迟与精度 |
| RQ5 | 在线量化和离线量化有差别吗？ | vLLM 加载时在线 FP8 vs llmcompressor 离线 FP8 |
| RQ6（微调后） | 微调学来的“守格式”能力在量化后能保住吗？ | 微调模型量化前后的 schema 合规率与 F1 |

## 2. 固定不变的条件（控制变量）

- 模型：Qwen/Qwen3.5-2B。
- 测试集：`test_extract_v1` + `test_intent_v1`（共 600 条，SHA-256 校验）。
- prompt：`zeroshot_v1`（RQ4 另设紧凑输出变体）；关闭思考模式；temperature 0；`max_tokens` 512；`max_model_len` 4096。
- 推理引擎：vLLM 0.32.0；同一张 GPU（RTX PRO 6000 Blackwell MIG 24GB 分片）；`gpu_memory_utilization` 0.85。
- 评测：`scripts/evaluate.py`，与零样本基线完全相同。
- 每个配置单独启动一次 vLLM；日志保存到 `results/quant/<tag>_*.log`。

## 3. 噪声基线（必须先做）

BF16 同一配置跑两次（`2b_bf16_a`、`2b_bf16_b`）。批量推理时 GPU 并行顺序会让 temperature 0 的输出也出现少量差异，两次之间的差异就是“噪声地板”。量化配置的精度差异只有明显超过噪声地板才算真实影响。`2b_bf16_a` 同时就是 2B 的零样本基线。

## 4. 实验配置

### Q1：不需要离线量化的配置

| tag | 配置 | 说明 |
| --- | --- | --- |
| `2b_bf16_a` / `2b_bf16_b` | BF16 | 参照组，跑两次测噪声；也是 2B 零样本基线 |
| `2b_fp8_online` | vLLM `quantization="fp8"` | 加载时在线量化，无需校准，W8A8 FP8 |
| `2b_nf4_bnb` | vLLM `quantization="bitsandbytes"` | QLoRA 训练用的 NF4 格式，用来说明“训练省显存的格式不一定适合部署” |
| `2b_bf16_kvfp8` | BF16 + `kv_cache_dtype="fp8"` | 只量化 KV cache |

### Q2：离线量化（llmcompressor），比较方法与校准数据

| tag | 方法 | 校准数据 |
| --- | --- | --- |
| `2b_fp8_offline` | FP8 动态（W8A8） | 无；与 `2b_fp8_online` 对比（RQ5） |
| `2b_int8` | SmoothQuant + GPTQ，INT8 W8A8 | 领域内：`train_v1` 256 条 |
| `2b_w4a16_rtn` | 直接四舍五入（RTN），W4A16，组大小 128 | 无 |
| `2b_w4a16_gptq` | GPTQ，W4A16，组大小 128 | 领域内：`train_v1` 256 条 |
| `2b_w4a16_awq` | AWQ，W4A16 非对称，组大小 128 | 领域内：`train_v1` 256 条 |
| `2b_w4a16_gptq_generic` | GPTQ，W4A16 | 通用对话数据 256 条（检验校准数据领域是否重要） |

不量化的层（与社区做法一致）：`lm_head`、视觉部分、MTP 头、线性注意力层。校准数据**只用训练集**，绝不用测试集。

### Q3：输出格式（延迟拆解）

| tag | 配置 |
| --- | --- |
| `2b_bf16_compact` | BF16 + 紧凑输出 prompt（`zeroshot_v1_compact`：只多一句“输出单行、无多余空格的 JSON”） |
| `<最优量化>_compact` | Q1、Q2 中精度最好的量化配置 + 紧凑输出 |

紧凑输出改变了 prompt，是独立因素，单独报告：`2b_bf16_compact` 对比 `2b_bf16_a`，量化配置的紧凑版对比 `2b_bf16_compact`。

### Q4：微调后（等 LoRA 训练完成）

微调模型先把 LoRA 合并进 BF16 权重，再用领域内数据做量化（`scripts/quantize.py --lora`）。重跑 Q1、Q2 中表现最好的两三种配置。

## 5. 测量方法

- **精度**：600 条全部推理，用 `evaluate.py` 评测；再用 `quant_report.py` 与参照组逐条配对比较：
  - 字段 F1 差值的 95% 置信区间（对样本做 1,000 次 bootstrap 重采样）；
  - 意图翻转：参照组对、量化组错的条数，以及反过来的条数；
  - 按字段、按 style_tag 的 F1 差值，定位损失来源。
- **速度**（预测写完之后再测，避免测速环节出错丢掉结果）：
  - 预热 5 条后，**逐条**跑 50 条：端到端延迟 p50 / p90；
  - 同样 50 条只生成 1 个 token：近似首 token 时间 TTFT；
  - 每 token 时间 TPOT ≈ (端到端 − TTFT) / (输出 token 数 − 1)；
  - 批量吞吐：300 条一次提交，输出 token/秒。
- **显存**：从 vLLM 日志读取权重与非 torch 占用、KV cache 大小。

## 6. 判定标准

- 一种量化配置“可上线”：字段 F1 下降不超过 0.5 个点、意图准确率与 schema 合规率没有超出噪声地板的下降。
- 在可上线的配置中，选单条延迟 p50 最低者；延迟相近时选显存最小者。

## 7. 预期（实验前写下，实验后对照）

1. FP8（在线或离线）精度与 BF16 的差异落在噪声地板内；INT8 W8A8 接近；在线与离线 FP8 结果接近。
2. W4A16 有可见下降，RTN 明显差于 GPTQ / AWQ；损失最可能出现在拼写错误地名、缩写户型这些难样本上。2B 参数少，4 位量化的损失可能比大模型更明显。
3. 领域内校准略好于通用校准，但差距不大。
4. NF4（bitsandbytes）省显存但推理更慢，因为反量化开销大，适合训练而不是部署。
5. 2B 在 MIG 分片上，单条延迟主要受输出长度影响：紧凑输出带来的延迟下降大于任何一种量化。

## 8. 已知风险

- Qwen3.5 是混合注意力架构，部分量化内核可能不支持；某个配置加载或量化失败时，记录报错并跳过。
- `llmcompressor` 可能要求与 vLLM 不同版本的 transformers / torch：量化在单独的虚拟环境 `/workspace/venv-quant` 中进行，推理仍用 `/workspace/venv`。
- MIG 分片只有整卡的一部分算力，延迟绝对值不能外推到整卡，只比较相对差异。

## 9. 运行方式与时间预算

```bash
source /workspace/start.sh
nohup bash scripts/run_quant.sh q1 > results/quant/run_q1.log 2>&1 &            # 5 个配置，约 40 分钟
bash scripts/run_quant.sh setup-quant                                             # 一次性，约 5 分钟
nohup bash scripts/run_quant.sh q2-quantize > results/quant/run_q2q.log 2>&1 &   # 6 个离线量化，约 40 分钟
nohup bash scripts/run_quant.sh q2 > results/quant/run_q2.log 2>&1 &            # 6 个配置，约 50 分钟
nohup bash scripts/run_quant.sh q3 2b_fp8_online > results/quant/run_q3.log 2>&1 &   # 第二个参数换成精度最好的量化配置
bash scripts/run_quant.sh report
```

每个配置约 6–10 分钟。所有阶段都可以重复执行，已完成的配置自动跳过；单个配置失败不影响其他配置。

## 10. 产出

- `results/quant/<tag>_{extract,intent}.jsonl`、`.meta.json`、`.log`
- `results/quant/report.md`：总表 + 与参照组的配对比较 + 按字段 / 风格拆分 + 结论
- 在 `PROGRESS.md` 记录当天结果与踩坑
