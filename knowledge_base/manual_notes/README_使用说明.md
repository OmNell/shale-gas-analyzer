# RAG 手工知识库使用说明

## 放置位置建议

把本文件夹中的 Markdown 文件复制到你的项目：

```text
knowledge_base/manual_notes/
```

把 `00_可下载论文清单.md` 中列出的 PDF 下载后，放入：

```text
knowledge_base/raw_pdfs/
```

## 推荐入库顺序

1. 先放入本文件夹里的 Markdown 文件；
2. 再下载 3～5 篇最相关论文；
3. 运行：
   ```bash
   python -m shale_gas_analyzer.rag.build_index --mode update
   ```
4. 测试检索：
   ```bash
   python -m shale_gas_analyzer.rag.retriever "井底积液 泡沫排水 气水比降低"
   ```

## 第一批优先下载 PDF

优先建议下载：

1. Hybrid Data-driven Framework for Shale Gas Production Performance Analysis...
2. Predicting Gas Well Performance with Decline Curve Analysis...
3. What Factors Control Shale Gas Production and Production Decline Trend...
4. Towards Better Shale Gas Production Forecasting Using Transfer Learning
5. Physics-Informed Graph Neural Network for Spatial-temporal Production Forecasting

## 注意

这些 Markdown 是为了让你的 Agent 先跑通“知识库依据”这一环节。后续如果要提高严谨性，应继续加入企业规范、现场案例和经过审核的工艺资料。
