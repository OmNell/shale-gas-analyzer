# 页岩气生产分析 Agent

这是一个面向页岩气井生产数据的本地多 Agent 分析系统。项目基于 CrewAI 组织数据分析、工程诊断、措施建议和报告生成流程，并提供一个本地网页控制台用于上传 CSV、启动运行、查看实时日志和最终报告。

## 当前版本

版本：`0.2.0`

主要能力：

- 网页端一键启动 Agent 流程
- 前端上传生产 CSV，不再依赖固定本地数据文件
- 自动预处理缺失值、空列、空行和常见异常占位符
- RAG 本地知识库检索，支持 Markdown 工程知识和英文论文 PDF
- 运行日志实时展示，最终报告自动刷新
- 敏感配置通过 `.env` 本地维护，不进入 Git 仓库

## 目录说明

```text
.
├── start_project.py                 # 一键启动入口，默认启动网页控制台
├── agent_console.py                 # 本地网页服务和 Agent 运行管理
├── frontend/                        # 控制台前端页面
├── src/shale_gas_analyzer/          # Agent、工具和 RAG 源码
├── data/                            # 示例或本地生产数据目录
├── knowledge_base/                  # RAG 知识库原始资料
├── vector_store/                    # 本地向量索引目录，运行产物不提交
├── shale_gas_production_report.md   # Agent 生成的分析报告
├── .env.example                     # 可提交的环境变量模板
└── .env                             # 本地私密配置，禁止提交
```

## 环境要求

- Windows / PowerShell
- Python `>=3.10,<3.14`
- 可兼容 OpenAI API 格式的大模型服务
- 一个可用的 API Key，本地写入 `.env`

## 快速启动

首次运行：

```powershell
python .\start_project.py
```

脚本会自动完成：

1. 检查 Python 版本
2. 创建或复用 `.venv`
3. 安装项目依赖
4. 检查 `.env`
5. 启动网页控制台

默认地址：

```text
http://127.0.0.1:8765/
```

如果不想自动打开浏览器：

```powershell
python .\start_project.py web --no-browser
```

如果依赖已经安装过，可以跳过安装：

```powershell
python .\start_project.py web --skip-install
```

## 配置方式

复制模板文件：

```powershell
Copy-Item .env.example .env
```

然后在 `.env` 中填写本地配置：

```text
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_API_BASE=https://api.openai.com/v1
WELL_NAME=your_well_name_here
THINKING_MAX_TOKENS=4096
REGULAR_MAX_TOKENS=2048
CREW_MAX_RPM=60
AGENT_MAX_EXECUTION_TIME=300
RAG_ENABLED=true
RAG_VECTOR_STORE_DIR=vector_store/chroma
RAG_KNOWLEDGE_DIR=knowledge_base
RAG_TOP_K=5
RAG_MIN_PDF_RESULTS=2
RAG_CANDIDATE_MULTIPLIER=6
RAG_CHUNK_SIZE=700
RAG_CHUNK_OVERLAP=100
RAG_EMBEDDING_MODEL=text-embedding-3-small
RAG_EMBEDDING_BASE_URL=${OPENAI_API_BASE}
RAG_EMBEDDING_API_KEY=${OPENAI_API_KEY}
```

注意：`.env` 已经被 `.gitignore` 忽略，不要手动加入 Git。

## 网页端使用

启动后在网页中完成以下操作：

1. 输入井名，例如 `X2`
2. 上传生产 CSV 文件
3. 选择稳定流程或层级流程
4. 选择是否在启动前更新 RAG
5. 点击“开始运行”
6. 在页面下方查看实时日志和最终报告

上传的 CSV 会被保存到 `data/uploads/`，该目录中的实际上传文件不会提交到仓库。

## 数据预处理

系统会在读取 CSV 后自动处理常见问题：

- 删除空列、空行和无意义的 `Unnamed` 列
- 识别常见空值标记，例如空字符串、`--`、`N/A`、`null`
- 清理字符串字段前后空格
- 对数字字段做容错转换
- 如果存在日期字段，会尽量解析并按日期排序

因此，即使上传的是未经清洗的生产表，也能降低因为空值或格式问题导致运行失败的概率。

## RAG 知识库

RAG 原始资料目录：

```text
knowledge_base/raw_pdfs/       # 英文或中文论文 PDF
knowledge_base/manual_notes/   # 人工整理的 Markdown 工程知识
```

更新知识库：

```powershell
python .\start_project.py rag-update
```

强制重建知识库：

```powershell
python .\start_project.py rag-rebuild
```

查看知识库状态：

```powershell
python .\start_project.py rag-status
```

直接测试检索：

```powershell
.\.venv\Scripts\python.exe -m shale_gas_analyzer.rag.retriever "井底积液 泡沫排水 产量递减" --top-k 8
```

说明：

- 英文论文 PDF 可以作为参考资料。
- 当前检索器包含中英文术语扩展，中文问题也可以召回英文论文片段。
- 如果 Chroma 向量索引不可用，系统会降级到本地关键词检索，保证 Agent 流程不中断。

## 命令行运行

稳定流程：

```powershell
python .\start_project.py run X2
```

层级流程：

```powershell
python .\start_project.py hierarchical X2
```

跳过 RAG 更新：

```powershell
python .\start_project.py run X2 --skip-rag
```

强制重建 RAG 后运行：

```powershell
python .\start_project.py run X2 --rag-rebuild
```

## 输出文件

- `shale_gas_production_report.md`：最终生产分析报告
- `crew_execution.log.txt`：运行日志，本地文件，不提交
- `vector_store/chroma/`：本地向量索引，不提交
- `knowledge_base/processed/`：知识库处理产物，不提交

## 敏感信息与提交安全

以下内容不会提交：

- `.env`
- `.venv/`
- `data/uploads/` 中的上传文件
- `vector_store/chroma/` 中的向量索引
- `knowledge_base/processed/` 中的处理产物
- 运行日志和缓存文件

提交前可以检查 `.env` 是否被忽略：

```powershell
git check-ignore -v .env
```

也可以扫描潜在敏感字段：

```powershell
rg -n "OPENAI_API_KEY|API_KEY|sk-|Bearer|SECRET|TOKEN" -S . -g "!.venv/**" -g "!vector_store/**" -g "!knowledge_base/processed/**"
```

正常情况下，仓库里只应该出现 `.env.example` 中的占位符和源码里的环境变量名，不应该出现真实密钥。

## 开发说明

安装为可编辑模式：

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

基础语法检查：

```powershell
.\.venv\Scripts\python.exe -m py_compile .\start_project.py .\agent_console.py
```

核心包语法检查：

```powershell
.\.venv\Scripts\python.exe -m compileall .\src
```
