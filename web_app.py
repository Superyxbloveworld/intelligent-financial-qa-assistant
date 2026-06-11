from __future__ import annotations

import json
import mimetypes
import os
import shutil
import threading
import time
from hashlib import sha256
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from docqa.models import FinancialCell, to_dict
from docqa.observability import audit_event
from docqa.pipeline import ingest
from docqa.qa_agent import FinancialQAAgent
from docqa.storage import read_jsonl


ROOT = Path(__file__).parent
PDF = ROOT / "data/input/financial-report-sample.pdf"
ACTIVE_PDF = ROOT / "data/input/current-upload.pdf"
CELLS = ROOT / "artifacts/cells.jsonl"
UPLOAD_LIMIT_MB = int(os.getenv("DOCQA_UPLOAD_LIMIT_MB", "30"))
UPLOAD_LIMIT = UPLOAD_LIMIT_MB * 1024 * 1024
INGEST_LOCK = threading.RLock()


def ensure_artifacts() -> None:
    if not CELLS.exists():
        ingest(ROOT, PDF)


def load_summary() -> dict[str, object]:
    with INGEST_LOCK:
        ensure_artifacts()
        cells = read_jsonl(CELLS, FinancialCell)
        return {
            "document": load_document_status(),
            "diagnostics": json.loads((ROOT / "artifacts/diagnostics.json").read_text(encoding="utf-8")),
            "validation": json.loads((ROOT / "artifacts/validation_report.json").read_text(encoding="utf-8")),
            "cells": [asdict(cell) for cell in cells],
        }


def load_document_status() -> dict[str, object]:
    manifest_path = ROOT / "artifacts/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    source = Path(str(manifest.get("source_pdf", PDF)))
    return {
        "filename": manifest.get("original_filename", source.name),
        "source_pdf": str(source),
        "is_builtin_sample": source.resolve() == PDF.resolve() if source.exists() else False,
        "pages": manifest.get("pages", 0),
        "cells": manifest.get("cells", 0),
    }


def activate_pdf(
    pdf_bytes: bytes,
    filename: str,
    destination: Path = ACTIVE_PDF,
) -> dict[str, object]:
    if not filename.lower().endswith(".pdf"):
        raise ValueError("仅支持 PDF 文件")
    if not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("文件内容不是有效 PDF")
    if len(pdf_bytes) > UPLOAD_LIMIT:
        raise ValueError(f"PDF 大小不能超过 {UPLOAD_LIMIT_MB} MB")

    safe_name = Path(unquote(filename)).name.replace("/", "_").replace("\\", "_")
    staging = ROOT / "data/input/.uploading.pdf"
    backup = ROOT / "artifacts-upload-backup"
    with INGEST_LOCK:
        if backup.exists():
            shutil.rmtree(backup)
        if (ROOT / "artifacts").exists():
            shutil.copytree(ROOT / "artifacts", backup)
        staging.write_bytes(pdf_bytes)
        try:
            result = ingest(ROOT, staging)
            if not result["diagnostics"]:
                raise ValueError("PDF 中没有可解析页面")
            if destination.resolve() != PDF.resolve():
                destination.write_bytes(pdf_bytes)
            manifest_path = ROOT / "artifacts/manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.update(
                {
                    "source_pdf": str(destination.resolve()),
                    "original_filename": safe_name,
                    "uploaded_at": int(time.time()),
                }
            )
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            Handler.agent = FinancialQAAgent(read_jsonl(CELLS, FinancialCell))
            audit_event(
                ROOT,
                "upload_activated",
                filename=safe_name,
                pages=len(result["diagnostics"]),
                cells=len(result["cells"]),
            )
            return load_summary()
        except Exception as exc:
            if backup.exists():
                if (ROOT / "artifacts").exists():
                    shutil.rmtree(ROOT / "artifacts")
                shutil.copytree(backup, ROOT / "artifacts")
            audit_event(
                ROOT,
                "upload_failed",
                filename=safe_name,
                error_type=type(exc).__name__,
            )
            raise
        finally:
            staging.unlink(missing_ok=True)
            if backup.exists():
                shutil.rmtree(backup)


def activate_builtin_sample() -> dict[str, object]:
    summary = activate_pdf(PDF.read_bytes(), PDF.name, PDF)
    ACTIVE_PDF.unlink(missing_ok=True)
    return summary


def load_reliability_report() -> dict[str, object]:
    report = ROOT / "artifacts/reliability_report.json"
    if not report.exists():
        raise FileNotFoundError("Run `make report` to generate reliability_report.json")
    return json.loads(report.read_text(encoding="utf-8"))


class Handler(BaseHTTPRequestHandler):
    agent: FinancialQAAgent

    def _json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/reliability":
            body = RELIABILITY_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/summary":
            self._json(load_summary())
            return
        if path == "/api/document":
            self._json(load_document_status())
            return
        if path == "/api/reliability":
            self._json(load_reliability_report())
            return
        if path.startswith("/artifacts/pages/"):
            file_path = (ROOT / path.lstrip("/")).resolve()
            pages_root = (ROOT / "artifacts/pages").resolve()
            if pages_root in file_path.parents and file_path.exists():
                body = file_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(file_path.name)[0] or "application/octet-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
        self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/upload":
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size <= 0:
                    raise ValueError("请选择 PDF 文件")
                if size > UPLOAD_LIMIT:
                    raise ValueError(f"PDF 大小不能超过 {UPLOAD_LIMIT_MB} MB")
                filename = self.headers.get("X-Filename", "uploaded.pdf")
                self._json(activate_pdf(self.rfile.read(size), filename))
            except Exception as exc:
                self._json({"error": str(exc)}, 400)
            return
        if path == "/api/load-sample":
            try:
                self._json(activate_builtin_sample())
            except Exception as exc:
                self._json({"error": str(exc)}, 400)
            return
        if path != "/api/ask":
            self._json({"error": "not found"}, 404)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            question = json.loads(self.rfile.read(size)).get("question", "").strip()
            if not question:
                raise ValueError("question is required")
            started = time.perf_counter()
            answer = self.agent.ask(question)
            audit_event(
                ROOT,
                "question_answered",
                question_hash=sha256(question.encode("utf-8")).hexdigest()[:12],
                question_length=len(question),
                status=answer.status,
                citation_ids=[item.cell_id for item in answer.citations],
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            self._json(to_dict(answer))
        except (ValueError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, 400)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[web] {format % args}")


def main(host: str | None = None, port: int | None = None) -> None:
    host = host or os.getenv("DOCQA_HOST", "127.0.0.1")
    port = port or int(os.getenv("DOCQA_PORT", "8501"))
    ensure_artifacts()
    Handler.agent = FinancialQAAgent(read_jsonl(CELLS, FinancialCell))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"智能财务问答助手: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>智能财务问答助手</title>
  <style>
    :root { --ink:#14213d; --muted:#667085; --line:#d8dee9; --paper:#f5f7fb; --brand:#175cd3; --ok:#067647; --warn:#b54708; --bad:#b42318; }
    * { box-sizing:border-box; } body { margin:0; font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--ink); background:var(--paper); }
    header { color:white; background:linear-gradient(120deg,#102a56,#175cd3); padding:28px max(24px,calc((100% - 1260px)/2)); }
    header h1 { margin:0 0 5px; font-size:28px; } header p { margin:0; opacity:.82; }
    header a { display:inline-block; margin-top:12px; color:white; text-decoration:none; border:1px solid #ffffff70; border-radius:8px; padding:6px 11px; }
    main { max-width:1260px; margin:22px auto; padding:0 22px 50px; }
    .metrics { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:18px; }
    .metric,.panel { background:white; border:1px solid var(--line); border-radius:12px; box-shadow:0 2px 8px #102a5610; }
    .metric { padding:15px; } .metric b { display:block; font-size:24px; } .metric span { color:var(--muted); }
    .panel { padding:18px; margin-bottom:18px; } h2 { margin:0 0 14px; font-size:19px; }
    form { display:flex; gap:10px; } input { flex:1; border:1px solid #98a2b3; border-radius:8px; padding:11px 12px; font-size:15px; }
    button { border:0; border-radius:8px; padding:10px 18px; color:white; background:var(--brand); font-weight:650; cursor:pointer; }
    .examples { display:flex; flex-wrap:wrap; gap:7px; margin-top:10px; }.examples button { color:#344054; background:#eef2f8; padding:6px 10px; font-weight:500; }
    #answer { display:none; margin-top:16px; padding:14px; border-left:5px solid var(--brand); background:#f8faff; }
    #answer.supported { border-color:var(--ok); } #answer.needs_review { border-color:var(--warn); } #answer.no_answer,#answer.clarification_required { border-color:var(--bad); }
    .grid { display:grid; grid-template-columns:1.15fr .85fr; gap:18px; }
    table { width:100%; border-collapse:collapse; font-size:13px; } th,td { border-bottom:1px solid var(--line); padding:8px; text-align:left; vertical-align:top; } th { background:#f8fafc; }
    .scroll { overflow:auto; max-height:420px; } pre { white-space:pre-wrap; font-size:12px; }
    .badge { display:inline-block; padding:2px 8px; border-radius:999px; background:#eaf0fa; font-size:12px; margin-right:6px; }
    img { max-width:100%; border:1px solid var(--line); border-radius:8px; margin-top:12px; }
    @media(max-width:800px){ .metrics,.grid{grid-template-columns:1fr;} form{display:block;} form button{margin-top:8px;width:100%;} }
  </style>
</head>
<body>
<header><h1>智能财务问答助手</h1><p>混合 PDF 解析 · 表格证据恢复 · 可追溯问答 · 可靠性校验</p><a href="/reliability">查看可靠性与工程验证</a></header>
<main>
  <section class="panel"><h2>PDF 文档</h2>
    <p id="documentStatus">正在读取当前文档...</p>
    <form id="uploadForm"><input id="pdfFile" type="file" accept="application/pdf,.pdf"><button>上传并自动解析</button><button id="loadSample" type="button">重新加载内置样本</button></form>
    <p id="uploadStatus" class="badge">项目启动时会自动加载并解析内置样本 PDF</p>
  </section>
  <section class="metrics" id="metrics"></section>
  <section class="panel"><h2>证据问答</h2>
    <form id="form"><input id="question" value="2025 年 6 月 30 日短期借款合计是多少？"><button>开始问答</button></form>
    <div class="examples" id="examples"></div><div id="answer"></div>
  </section>
  <div class="grid">
    <section class="panel"><h2>逐页解析路由</h2><div class="scroll"><table id="diagnostics"></table></div></section>
    <section class="panel"><h2>可靠性检查失败</h2><div class="scroll"><table id="failures"></table></div></section>
  </div>
  <section class="panel"><h2>结构化财务证据</h2><div class="scroll"><table id="cells"></table></div></section>
</main>
<script>
const examples=["2025 年 6 月 30 日短期借款合计是多少？","2024 年 12 月 31 日短期借款合计是多少？","2025 年其他综合收益合计期末余额是多少？","2024 年应付债券 5 年以上是多少？","短期借款是多少？","2025 年营业收入是多少？"];
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function table(id, rows, cols){document.getElementById(id).innerHTML="<thead><tr>"+cols.map(c=>`<th>${esc(c[1])}</th>`).join("")+"</tr></thead><tbody>"+rows.map(r=>"<tr>"+cols.map(c=>`<td>${esc(r[c[0]])}</td>`).join("")+"</tr>").join("")+"</tbody>"}
async function load(){
 const s=await (await fetch("/api/summary")).json(), v=s.validation;
 document.getElementById("documentStatus").innerHTML=`当前文档：<b>${esc(s.document.filename)}</b>；PDF ${s.document.pages} 页；结构化单元格 ${s.document.cells} 个；${s.document.is_builtin_sample?"内置样本已自动加载":"用户上传文档"}`;
 document.getElementById("metrics").innerHTML=[["PDF 页数",s.diagnostics.length],["结构化单元格",v.cell_count],["执行检查",v.checks],["失败检查",v.failed_checks]].map(x=>`<div class=metric><span>${x[0]}</span><b>${x[1]}</b></div>`).join("");
 table("diagnostics",s.diagnostics,[["pdf_page","PDF 页"],["printed_page","原页码"],["page_type","类型"],["parser","解析器"],["orientation","方向"],["word_count","词数"],["warnings","告警"]]);
 table("failures",v.failures.slice(0,20),[["page","页"],["row","行"],["column","列"],["check","检查"],["detail","详情"]]);
 table("cells",s.cells.slice(0,60),[["pdf_page","页"],["period","期间"],["table","表格"],["row","行"],["column","列"],["raw_value","原始值"],["confidence","置信度"]]);
}
async function uploadFile(file){
 const status=document.getElementById("uploadStatus");status.textContent=`正在上传并解析 ${file.name}，请等待...`;
 const response=await fetch("/api/upload",{method:"POST",headers:{"Content-Type":"application/pdf","X-Filename":encodeURIComponent(file.name)},body:file});
 const result=await response.json();if(!response.ok)throw new Error(result.error||"上传失败");
 status.textContent=`${file.name} 上传和解析完成`;await load();document.getElementById("answer").style.display="none";
}
document.getElementById("uploadForm").onsubmit=async e=>{e.preventDefault();const file=document.getElementById("pdfFile").files[0];if(!file){document.getElementById("uploadStatus").textContent="请先选择 PDF 文件";return}try{await uploadFile(file)}catch(err){document.getElementById("uploadStatus").textContent=`上传失败：${err.message}`}};
document.getElementById("loadSample").onclick=async()=>{const status=document.getElementById("uploadStatus");status.textContent="正在重新加载内置样本...";try{const response=await fetch("/api/load-sample",{method:"POST"}),result=await response.json();if(!response.ok)throw new Error(result.error||"加载失败");status.textContent="内置样本已重新加载并完成解析";await load()}catch(err){status.textContent=`加载失败：${err.message}`}};
document.getElementById("examples").innerHTML=examples.map(q=>`<button type=button>${esc(q)}</button>`).join("");
document.querySelectorAll(".examples button").forEach(b=>b.onclick=()=>document.getElementById("question").value=b.textContent);
document.getElementById("form").onsubmit=async e=>{e.preventDefault();const a=await (await fetch("/api/ask",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({question:document.getElementById("question").value})})).json(), el=document.getElementById("answer");el.style.display="block";el.className=a.status;let img=a.citations?.length?`<img src="/artifacts/pages/page-${a.citations[0].pdf_page}.png" alt="来源页">`:"";el.innerHTML=`<p><span class=badge>${esc(a.status)}</span><span class=badge>confidence ${esc(a.confidence)}</span></p><strong>${esc(a.answer)}</strong><h3>自检</h3><pre>${esc(JSON.stringify(a.checks,null,2))}</pre><h3>检索证据</h3><pre>${esc(JSON.stringify(a.retrieved_evidence,null,2))}</pre>${img}`};
load();
</script>
</body></html>"""


RELIABILITY_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>可靠性与工程验证</title>
<style>
body{margin:0;background:#f5f7fb;color:#172b4d;font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
header{padding:22px 36px;color:white;background:linear-gradient(120deg,#102a56,#175cd3)}h1{margin:0;font-size:26px}header p{margin:4px 0 0;opacity:.85}header a{display:inline-block;margin-top:10px;color:white;text-decoration:none;border:1px solid #ffffff70;border-radius:8px;padding:5px 10px}
main{max-width:1320px;margin:18px auto;padding:0 22px 40px}.panel{background:white;border:1px solid #d8dee9;border-radius:12px;padding:18px;margin-bottom:16px;box-shadow:0 2px 8px #102a5610}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.metric{padding:14px;border-radius:10px;background:#eef4ff}.metric b{display:block;font-size:23px}.metric span{color:#526581}
h2{margin:0 0 13px;font-size:19px}table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:7px;border-bottom:1px solid #e3e8ef;text-align:left;vertical-align:top}th{background:#f8fafc}
.cards{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}.card{border:1px solid #d8dee9;border-radius:10px;padding:12px}.card p{margin:5px 0}.badge{display:inline-block;padding:2px 8px;border-radius:999px;background:#eef4ff;margin-right:5px}.supported{background:#e7f6ec}.needs_review{background:#fff1df}.no_answer{background:#ffeceb}
code{background:#f2f4f7;padding:2px 4px;border-radius:4px}.note{padding:10px;border-left:4px solid #175cd3;background:#f8faff}.hide{display:none}.scroll{max-height:470px;overflow:auto}
@media(max-width:800px){.metrics,.cards{grid-template-columns:1fr}}
</style></head>
<body><header><h1>可靠性与工程验证</h1><p>解析诊断 · 问答证据 · 风险校验 · 工程判断</p><a href="/">返回智能财务问答助手</a></header>
<main>
<section id="parse" class="panel"><h2>1. PDF 解析结果：正文与表格</h2><div class="metrics" id="parseMetrics"></div><p class="note">第 1-5 页存在文本层，使用 PyMuPDF 坐标解析；第 6 页原生文本为 0，自动路由至 OCR。系统共恢复 446 个可追溯财务单元格。</p><div class="scroll"><table id="diagnostics"></table></div><h2 style="margin-top:16px">结构化表格示例</h2><div class="scroll"><table id="tableExamples"></table></div></section>
<section id="qa" class="panel"><h2>2. 代表性问答与边界行为</h2><div class="cards" id="qaCards"></div></section>
<section id="checks" class="panel"><h2>3. 来源引用与自检结果</h2><div class="scroll"><table id="checksTable"></table></div><p class="note">OCR 异常值不会被静默修复。示例：<code>26.075,352,739.73</code> 被标记为 <code>needs_review</code>。</p></section>
<section id="test" class="panel"><h2>4. 测试与评估脚本运行结果</h2><div class="metrics" id="testMetrics"></div><p class="note" id="pytest"></p><div class="scroll"><table id="evalTable"></table></div></section>
<section id="reasoning" class="panel"><h2>5. 工程判断与可靠性闭环</h2><p class="note">这里展示的不是功能清单，而是实际观察如何改变方案，以及每个判断如何被反向测试和运行证据验证。</p><div class="scroll"><table id="decisionTable"></table></div><h2 style="margin-top:16px">AI Coding 校验原则</h2><ol id="aiCodingLessons"></ol></section>
</main>
<script>
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function table(id,rows,cols){document.getElementById(id).innerHTML="<thead><tr>"+cols.map(c=>`<th>${esc(c[1])}</th>`).join("")+"</tr></thead><tbody>"+rows.map(r=>"<tr>"+cols.map(c=>`<td>${esc(r[c[0]])}</td>`).join("")+"</tr>").join("")+"</tbody>"}
function metrics(id,items){document.getElementById(id).innerHTML=items.map(x=>`<div class=metric><span>${esc(x[0])}</span><b>${esc(x[1])}</b></div>`).join("")}
async function load(){const r=await(await fetch("/api/reliability")).json();
metrics("parseMetrics",[["PDF 页数",r.diagnostics.length],["原生文本页",r.diagnostics.filter(x=>x.page_type==="native").length],["扫描 OCR 页",r.diagnostics.filter(x=>x.page_type==="scanned").length],["结构化单元格",r.validation.cell_count]]);
table("diagnostics",r.diagnostics,[["pdf_page","PDF页"],["printed_page","原报告页"],["page_type","类型"],["parser","解析器"],["orientation","方向"],["native_text_chars","原生字符"],["warnings","告警"]]);
table("tableExamples",r.table_examples.slice(0,18),[["pdf_page","页"],["period","期间"],["row","行"],["column","列"],["raw_value","原始值"],["source","来源"],["confidence","置信度"],["warnings","告警"]]);
document.getElementById("qaCards").innerHTML=r.qa_results.map((x,i)=>`<article class=card><p><span class=badge>${i+1}</span><span class="badge ${x.status}">${esc(x.status)}</span>${esc(x.category)}</p><b>${esc(x.question)}</b><p>${esc(x.answer)}</p><small>confidence: ${esc(x.confidence)}</small></article>`).join("");
const checkRows=r.qa_results.map(x=>({...x,citation_text:x.citations.length?`PDF 第 ${x.citations[0].pdf_page} 页 / 原报告第 ${x.citations[0].printed_page} 页 / ${x.citations[0].cell_id}`:"无引用",check_text:x.checks.length?x.checks.map(c=>`${c.name}: ${c.passed?"通过":"失败"}`).join("；"):"无检查项"}));
table("checksTable",checkRows,[["category","类型"],["status","状态"],["question","问题"],["confidence","置信度"],["citation_text","来源引用"],["check_text","自检"]]);
metrics("testMetrics",[["自动化测试",r.pytest.summary],["黄金问题",r.evaluation.total],["黄金集通过率",Math.round(r.evaluation.pass_rate*100)+"%"],["可靠性失败项",r.validation.failed_checks]]);
document.getElementById("pytest").textContent="$ "+r.pytest.command+" → "+r.pytest.summary+"；黄金集同时校验状态、精确数值和引用页码。";
table("evalTable",r.evaluation.results,[["question","问题"],["actual_status","状态"],["passed","通过"],["citation_ok","引用正确"],["actual_answer","实际回答"]]);
table("decisionTable",r.decision_records,[["observation","实际观察"],["decision","我的判断与取舍"],["verification","验证方式"],["result","结果"]]);
document.getElementById("aiCodingLessons").innerHTML=r.ai_coding_lessons.map(x=>`<li>${esc(x)}</li>`).join("");
const section=new URLSearchParams(location.search).get("section");if(section){["parse","qa","checks","test","reasoning"].forEach(x=>document.getElementById(x).classList.toggle("hide",x!==section));}}
load();
</script></body></html>"""


if __name__ == "__main__":
    main()
