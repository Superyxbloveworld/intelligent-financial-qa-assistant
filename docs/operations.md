# 运行保障与故障处理

## 配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DOCQA_HOST` | `127.0.0.1` | Web 服务监听地址 |
| `DOCQA_PORT` | `8501` | Web 服务端口 |
| `DOCQA_UPLOAD_LIMIT_MB` | `30` | PDF 上传大小限制 |

示例：

```bash
DOCQA_PORT=8600 DOCQA_UPLOAD_LIMIT_MB=50 make run
```

## 可观测性与定位

- `artifacts/diagnostics.json`：定位页面类型判断、解析器选择和 OCR 告警。
- `artifacts/cells.jsonl`：定位表格行列映射、原值、置信度和坐标。
- `artifacts/validation_report.json`：定位数字格式、低置信度和勾稽失败。
- `artifacts/evaluation_report.json`：定位问答状态、数值或引用回归。
- `artifacts/events.jsonl`：记录解析、上传、问答状态、引用和耗时；不记录问题正文。

## 常见故障与替代方案

| 现象 | 检查方法 | 当前处理 | 生产建议 |
| --- | --- | --- | --- |
| 扫描页没有结果 | 查看 `diagnostics.json` 中 parser/warnings | 非 macOS 明确标记 OCR 不可用，不生成假结果 | 接入 PaddleOCR/云 OCR，并做双引擎比对 |
| OCR 数字标点异常 | 查看 `validation_report.json` 的 `numeric_format` | 保留原始值，回答为 `needs_review` | 人工复核或第二 OCR 引擎确认 |
| 上传 PDF 解析失败 | 页面显示错误，查看 `events.jsonl` | 回滚至上一份成功 artifacts | 使用后台任务、对象存储和版本化索引 |
| 回答缺少依据 | 查看检索证据和引用 | 返回 `no_answer` 或要求澄清 | 扩充 schema、检索策略和黄金集 |
| 新版本出现回归 | 运行 `make all` | 校验测试、黄金集、引用页码和解析风险 | CI 中设置阈值并保存历史评估报告 |

## 安全与隐私边界

- 不写入或记录 API Key、密码和账号。
- 上传文件当前保存在本机 `data/input/current-upload.pdf`；生产环境必须增加访问控制、隔离、保留周期和删除策略。
- 审计日志默认只记录问题哈希，不记录问题正文和 PDF 内容。
- 当前 Web 原型没有鉴权，不应直接暴露到公网。
