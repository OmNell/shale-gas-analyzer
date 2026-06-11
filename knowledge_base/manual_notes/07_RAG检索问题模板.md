# RAG 检索问题模板：供 Agent 自动构造 query 使用

## 设计目的

本文件用于辅助工程专家 Agent 根据生产数据指标自动构造 RAG 检索问题。建议把这些模板放入 `manual_notes/`，让 RAG 能检索到可复用 query 结构。

## 模板 1：井底积液

当数据分析结果出现“产气快速下降 + 气水比降低 + 油压波动”时，构造：

低产低压页岩气井 日产气快速下降 气水比降低 油压波动 油套压差异常 井底积液 携液能力不足 泡沫排水 柱塞气举 适用条件 风险

## 模板 2：泡沫排水采气

当疑似积液且仍有套压恢复能力时，构造：

页岩气井 低产低压 井底积液 泡沫排水采气 起泡剂 适用条件 产水 气水比 套压恢复 风险 复核指标

## 模板 3：柱塞气举

当泡排效果不稳定或产液周期性明显时，构造：

低产气井 柱塞气举 plunger lift 排水采气 井底积液 开关井制度 油压波动 柱塞到达时间 适用条件 风险

## 模板 4：自然递减与异常递减区分

当产量下降但是否异常不明确时，构造：

页岩气 产量递减 Arps 双曲递减 自然递减 异常递减 产量预测 压力变化 生产制度变化 数据异常

## 模板 5：地层能量衰竭

当压力与产气长期同步下降、压力恢复能力弱时，构造：

页岩气井 地层能量衰竭 套压下降 油压下降 产气递减 压力恢复能力 经济极限 生产制度优化

## 模板 6：裂缝导流能力下降

当压力仍有一定水平但产能恢复差时，构造：

页岩气 裂缝导流能力下降 压裂效果 产能衰减 压力动态 返排 生产预测 措施评价

## Agent 使用要求

- 检索 query 应由“当前井数据特征 + 疑似问题 + 候选措施”构成。
- 不要只检索“这个井怎么办”。
- 检索结果必须和数据依据一起使用。
- 如果检索不到知识，报告中应说明“本次未检索到外部知识库依据”，不能编造来源。

## 参考来源
- Gas well deliquification: https://en.wikipedia.org/wiki/Gas_well_deliquification
- Plunger lift: https://en.wikipedia.org/wiki/Plunger_lift
- Decline curve analysis: https://en.wikipedia.org/wiki/Decline_curve_analysis
- Hybrid data-driven shale gas production analysis: https://arxiv.org/abs/2112.04243
- Predicting gas well performance with decline curve analysis: https://arxiv.org/abs/2505.12333
- Shale gas production decline factors: https://arxiv.org/abs/1710.11464
- Shale gas production forecasting using transfer learning: https://arxiv.org/abs/2106.11051

> 备注：本知识文件是为 RAG 检索构建的“工程知识初稿”，不是现场作业标准。实际生产措施必须结合企业规范、井史资料、作业记录和现场专家复核。
