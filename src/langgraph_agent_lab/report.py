"""Report generation helper."""

from __future__ import annotations

from pathlib import Path
from statistics import mean

from .metrics import MetricsReport


def render_report(metrics: MetricsReport) -> str:
    """Render a submission-ready lab report from collected metrics."""
    scenario_rows = "\n".join(
        f"| {item.scenario_id} | {item.expected_route} | {item.actual_route} | "
        f"{'✅' if item.success else '❌'} | {item.retry_count} | {item.interrupt_count} | {item.latency_ms} |"
        for item in metrics.scenario_metrics
    )
    failure_count = sum(1 for item in metrics.scenario_metrics if not item.success)
    failed_scenarios = [item for item in metrics.scenario_metrics if not item.success]
    dead_letter_cases = [
        item.scenario_id
        for item in metrics.scenario_metrics
        if any("dead_letter" in err.lower() for err in item.errors)
    ]

    avg_latency = mean(item.latency_ms for item in metrics.scenario_metrics) if metrics.scenario_metrics else 0

    if failure_count > 0:
        failure_analysis = [
            f"- {failure_count} kịch bản thất bại trong lần chạy cuối cùng.",
            f"- Thất bại: {', '.join(item.scenario_id for item in failed_scenarios)}.",
            f"- Dead-letter xuất hiện tại: {', '.join(dead_letter_cases) if dead_letter_cases else 'không có'}.",
            "- Xem mảng `errors` trong `outputs/metrics.json` để phân tích nguyên nhân gốc.",
        ]
    else:
        failure_analysis = [
            "- Tất cả kịch bản đều đạt trong lần chạy cuối cùng.",
            f"- Cơ chế thử lại hoạt động đúng: tổng số lần retry = {metrics.total_retries}.",
            f"- Luồng phê duyệt HITL hoạt động đúng: tổng số lần interrupt = {metrics.total_interrupts}.",
        ]

    persistence_note = (
        "Kiểm tra khôi phục thành công (interrupt → Command(resume=...) → hoàn thành)."
        if metrics.resume_success
        else "Kiểm tra khôi phục chưa được thực hiện hoặc không thành công trong lần chạy này."
    )

    # Categorize scenarios by tag type for analysis
    simple_count = sum(1 for item in metrics.scenario_metrics if item.expected_route == "simple")
    tool_count = sum(1 for item in metrics.scenario_metrics if item.expected_route == "tool")
    risky_count = sum(1 for item in metrics.scenario_metrics if item.expected_route == "risky")
    error_count = sum(1 for item in metrics.scenario_metrics if item.expected_route == "error")
    missing_count = sum(1 for item in metrics.scenario_metrics if item.expected_route == "missing_info")

    lines = [
        "# Báo Cáo Bài Thực Hành Ngày 08 — LangGraph Agentic Orchestration",
        "",
        "## 1. Thông tin sinh viên",
        "",
        "- Họ và tên: Lê Duy Anh",
        "- Mã số sinh viên: 2A202600094",
        "- Repo/commit: https://github.com/AnhLD2809/lab23_LeDuyAnh_2A202600094.git",
        f"- Ngày nộp: (fill submission date)",
        "",
        "## 2. Kiến trúc hệ thống",
        "",
        "Hệ thống được xây dựng dưới dạng một đồ thị trạng thái (StateGraph) sử dụng LangGraph, bao gồm 11 node xử lý:",
        "",
        "- **`intake`** — Chuẩn hoá truy vấn đầu vào (loại bỏ khoảng trắng thừa, che giấu PII qua regex) và ghi lại sự kiện kiểm toán.",
        "- **`classify`** — Phân loại truy vấn theo chính sách ưu tiên: injection → `risky` → `tool` → `missing_info` → `error` → `simple`.",
        "- **`tool`** — Gọi công cụ giả lập với khoá idempotent; mô phỏng lỗi tạm thời cho tuyến `error`.",
        "- **`evaluate`** — Kiểm tra kết quả từ `tool` (bước \"done?\" — ưu thế chính của LangGraph so với LCEL).",
        "- **`retry`** — Ghi nhận lần thử lại, tăng `attempt`, kèm metadata exponential-backoff.",
        "- **`answer`** — Tạo câu trả lời cuối cùng được ground trong tool_results và approval context.",
        "- **`clarify`** — Yêu cầu người dùng bổ sung thông tin khi truy vấn mơ hồ hoặc khi bị từ chối.",
        "- **`risky_action`** — Chuẩn bị hành động rủi ro cao kèm evidence và risk justification.",
        "- **`approval`** — Bước phê duyệt HITL; hỗ trợ `interrupt()` thực khi `LANGGRAPH_INTERRUPT=true`.",
        "- **`dead_letter`** — Ghi lại yêu cầu không thể xử lý kèm severity level.",
        "- **`finalize`** — Kết thúc luồng xử lý và ghi lại sự kiện kiểm toán cuối cùng.",
        "",
        "### Sơ đồ luồng xử lý",
        "",
        "```",
        "START → intake → classify → [định tuyến có điều kiện]",
        "  simple       → answer → finalize → END",
        "  tool         → tool → evaluate → answer → finalize → END",
        "  missing_info → clarify → finalize → END",
        "  risky        → risky_action → approval → tool → evaluate → answer → finalize → END",
        "  error        → retry → tool → evaluate → [vòng lặp thử lại hoặc answer]",
        "  vượt quá retry → dead_letter → finalize → END",
        "```",
        "",
        "## 3. Lược đồ trạng thái (State Schema)",
        "",
        "| Trường | Kiểu reducer | Lý do |",
        "|---|---|---|",
        "| `route`, `risk_level`, `attempt`, `approval`, `evaluation_result` | ghi đè | Chỉ cần giá trị quyết định mới nhất |",
        "| `messages` | nối thêm | Lưu toàn bộ lịch sử hội thoại phục vụ kiểm toán |",
        "| `tool_results` | nối thêm | Lưu lịch sử kết quả từ công cụ để phục vụ gỡ lỗi |",
        "| `errors` | nối thêm | Theo dõi lịch sử lỗi qua các vòng thử lại |",
        "| `events` | nối thêm | Ghi lại toàn bộ chuỗi sự kiện phục vụ giám sát và chấm điểm |",
        "",
        "## 4. Kết quả chạy kịch bản",
        "",
        "### Tổng quan",
        "",
        f"- Tổng số kịch bản: **{metrics.total_scenarios}**",
        f"- Tỷ lệ thành công: **{metrics.success_rate:.2%}**",
        f"- Số node trung bình: **{metrics.avg_nodes_visited:.2f}**",
        f"- Tổng số lần thử lại: **{metrics.total_retries}**",
        f"- Tổng số lần ngắt HITL: **{metrics.total_interrupts}**",
        f"- Độ trễ trung bình: **{avg_latency:.0f} ms**",
        f"- Khôi phục sau ngắt: **{'thành công' if metrics.resume_success else 'chưa kiểm tra'}**",
        "",
        "### Phân bố theo tuyến",
        "",
        f"| simple | tool | risky | error | missing_info |",
        f"|---:|---:|---:|---:|---:|",
        f"| {simple_count} | {tool_count} | {risky_count} | {error_count} | {missing_count} |",
        "",
        "### Chi tiết từng kịch bản",
        "",
        "| Kịch bản | Tuyến kỳ vọng | Tuyến thực tế | Thành công | Thử lại | Ngắt HITL | Latency (ms) |",
        "|---|---|---|---:|---:|---:|---:|",
        scenario_rows,
        "",
        "## 5. Phân tích lỗi và trường hợp biên",
        "",
        *failure_analysis,
        "",
        "### Cơ chế phòng thủ",
        "",
        "- **Prompt Injection**: Phát hiện các mẫu \"ignore previous instructions\", \"[SYSTEM:\" → luôn route sang `risky` với approval bắt buộc.",
        "- **Đa ý định (multi-intent)**: Khi câu hỏi chứa cả từ khoá risky và tool, ưu tiên risky để đảm bảo an toàn.",
        "- **Thiếu ngữ cảnh (ambiguous)**: Truy vấn ngắn + đại từ mơ hồ → route sang `missing_info` thay vì đoán.",
        "- **Dead-letter**: Khi vượt quá `max_attempts` → ghi log kèm severity level cho ops team.",
        "",
        "## 6. Bằng chứng về lưu trữ trạng thái và khôi phục",
        "",
        "- Sử dụng `MemorySaver` cho phát triển; `SqliteSaver` (WAL mode) cho demo crash-recovery.",
        "- Mỗi kịch bản được gán `thread_id` riêng biệt.",
        f"- {persistence_note}",
        "",
        "## 7. Các phần mở rộng đã thực hiện",
        "",
        "1. **HITL thực tế**: Hỗ trợ `interrupt()` tại node `approval` khi `LANGGRAPH_INTERRUPT=true`.",
        "2. **Giao diện Streamlit**: UI cho phép nhập truy vấn, xem luồng xử lý, approve/reject.",
        "3. **SQLite Checkpointer**: `SqliteSaver` với WAL mode, sẵn sàng cho crash-recovery demo.",
        "4. **PII Masking**: Tự động che giấu email, phone, SSN, card number trong intake.",
        "5. **Idempotency Keys**: Tool execution có idempotency key dạng SHA-256.",
        "6. **Exponential Backoff**: Retry metadata bao gồm backoff timing (cap 30s).",
        "7. **Hard Scenarios**: Bộ kịch bản khó bao gồm prompt injection, multi-intent, system spoofing.",
        "",
        "## 8. Kế hoạch cải tiến",
        "",
        "1. Thay thế heuristic evaluation bằng structured validator hoặc LLM-as-judge.",
        "2. Thêm tool adapter thực tế (ticket DB/API) với idempotency keys.",
        "3. Tích hợp dead-letter sink (queue hoặc ticketing system).",
        "4. Bổ sung regression suite cho paraphrase-style hidden scenarios.",
        "5. Thêm OpenTelemetry tracing cho observability production-grade.",
    ]
    return "\n".join(lines) + "\n"


def write_report(metrics: MetricsReport, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(metrics), encoding="utf-8")
