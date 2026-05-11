# Báo Cáo Bài Thực Hành Ngày 08 — LangGraph Agentic Orchestration

## 1. Thông tin sinh viên

- Họ và tên: Lê Duy Anh
- Mã số sinh viên: 2A202600094
- Repo/commit: https://github.com/AnhLD2809/lab23_LeDuyAnh_2A202600094.git
- Ngày nộp: (fill submission date)

## 2. Kiến trúc hệ thống

Hệ thống được xây dựng dưới dạng một đồ thị trạng thái (StateGraph) sử dụng LangGraph, bao gồm 11 node xử lý:

- **`intake`** — Chuẩn hoá truy vấn đầu vào (loại bỏ khoảng trắng thừa, che giấu PII qua regex) và ghi lại sự kiện kiểm toán.
- **`classify`** — Phân loại truy vấn theo chính sách ưu tiên: injection → `risky` → `tool` → `missing_info` → `error` → `simple`.
- **`tool`** — Gọi công cụ giả lập với khoá idempotent; mô phỏng lỗi tạm thời cho tuyến `error`.
- **`evaluate`** — Kiểm tra kết quả từ `tool` (bước "done?" — ưu thế chính của LangGraph so với LCEL).
- **`retry`** — Ghi nhận lần thử lại, tăng `attempt`, kèm metadata exponential-backoff.
- **`answer`** — Tạo câu trả lời cuối cùng được ground trong tool_results và approval context.
- **`clarify`** — Yêu cầu người dùng bổ sung thông tin khi truy vấn mơ hồ hoặc khi bị từ chối.
- **`risky_action`** — Chuẩn bị hành động rủi ro cao kèm evidence và risk justification.
- **`approval`** — Bước phê duyệt HITL; hỗ trợ `interrupt()` thực khi `LANGGRAPH_INTERRUPT=true`.
- **`dead_letter`** — Ghi lại yêu cầu không thể xử lý kèm severity level.
- **`finalize`** — Kết thúc luồng xử lý và ghi lại sự kiện kiểm toán cuối cùng.

### Sơ đồ luồng xử lý

```
START → intake → classify → [định tuyến có điều kiện]
  simple       → answer → finalize → END
  tool         → tool → evaluate → answer → finalize → END
  missing_info → clarify → finalize → END
  risky        → risky_action → approval → tool → evaluate → answer → finalize → END
  error        → retry → tool → evaluate → [vòng lặp thử lại hoặc answer]
  vượt quá retry → dead_letter → finalize → END
```

## 3. Lược đồ trạng thái (State Schema)

| Trường | Kiểu reducer | Lý do |
|---|---|---|
| `route`, `risk_level`, `attempt`, `approval`, `evaluation_result` | ghi đè | Chỉ cần giá trị quyết định mới nhất |
| `messages` | nối thêm | Lưu toàn bộ lịch sử hội thoại phục vụ kiểm toán |
| `tool_results` | nối thêm | Lưu lịch sử kết quả từ công cụ để phục vụ gỡ lỗi |
| `errors` | nối thêm | Theo dõi lịch sử lỗi qua các vòng thử lại |
| `events` | nối thêm | Ghi lại toàn bộ chuỗi sự kiện phục vụ giám sát và chấm điểm |

## 4. Kết quả chạy kịch bản

### Tổng quan

- Tổng số kịch bản: **13**
- Tỷ lệ thành công: **100.00%**
- Số node trung bình: **7.00**
- Tổng số lần thử lại: **7**
- Tổng số lần ngắt HITL: **5**
- Độ trễ trung bình: **5 ms**
- Khôi phục sau ngắt: **thành công**

### Phân bố theo tuyến

| simple | tool | risky | error | missing_info |
|---:|---:|---:|---:|---:|
| 1 | 2 | 5 | 3 | 2 |

### Chi tiết từng kịch bản

| Kịch bản | Tuyến kỳ vọng | Tuyến thực tế | Thành công | Thử lại | Ngắt HITL | Latency (ms) |
|---|---|---|---:|---:|---:|---:|
| S01_simple | simple | simple | ✅ | 0 | 0 | 7 |
| S02_tool | tool | tool | ✅ | 0 | 0 | 4 |
| S03_missing | missing_info | missing_info | ✅ | 0 | 0 | 3 |
| S04_risky | risky | risky | ✅ | 0 | 1 | 5 |
| S05_error | error | error | ✅ | 3 | 0 | 7 |
| S06_delete | risky | risky | ✅ | 0 | 1 | 4 |
| S07_dead_letter | error | error | ✅ | 1 | 0 | 3 |
| H01_multi_intent | risky | risky | ✅ | 0 | 1 | 5 |
| H02_ambiguous_missing | missing_info | missing_info | ✅ | 0 | 0 | 2 |
| H03_prompt_injection | risky | risky | ✅ | 0 | 1 | 5 |
| H04_tool_disguised | tool | tool | ✅ | 0 | 0 | 4 |
| H05_fake_approval | risky | risky | ✅ | 0 | 1 | 5 |
| H06_error_trigger | error | error | ✅ | 3 | 0 | 7 |

## 5. Phân tích lỗi và trường hợp biên

- All scenarios passed in the last run.
- Retry behavior observed with total retries = 7.
- Interrupt/HITL path observed with total interrupts = 5.

### Cơ chế phòng thủ

- **Prompt Injection**: Phát hiện các mẫu "ignore previous instructions", "[SYSTEM:" → luôn route sang `risky` với approval bắt buộc.
- **Đa ý định (multi-intent)**: Khi câu hỏi chứa cả từ khoá risky và tool, ưu tiên risky để đảm bảo an toàn.
- **Thiếu ngữ cảnh (ambiguous)**: Truy vấn ngắn + đại từ mơ hồ → route sang `missing_info` thay vì đoán.
- **Dead-letter**: Khi vượt quá `max_attempts` → ghi log kèm severity level cho ops team.

## 6. Bằng chứng về lưu trữ trạng thái và khôi phục

- Sử dụng `MemorySaver` cho phát triển; `SqliteSaver` (WAL mode) cho demo crash-recovery.
- Mỗi kịch bản được gán `thread_id` riêng biệt.
- Resume probe succeeded (interrupt → Command(resume=...) → completion).

## 7. Các phần mở rộng đã thực hiện

1. **HITL thực tế**: Hỗ trợ `interrupt()` tại node `approval` khi `LANGGRAPH_INTERRUPT=true`.
2. **Giao diện Streamlit**: UI cho phép nhập truy vấn, xem luồng xử lý, approve/reject.
3. **SQLite Checkpointer**: `SqliteSaver` với WAL mode, sẵn sàng cho crash-recovery demo.
4. **PII Masking**: Tự động che giấu email, phone, SSN, card number trong intake.
5. **Idempotency Keys**: Tool execution có idempotency key dạng SHA-256.
6. **Exponential Backoff**: Retry metadata bao gồm backoff timing (cap 30s).
7. **Hard Scenarios**: Bộ kịch bản khó bao gồm prompt injection, multi-intent, system spoofing.

## 8. Kế hoạch cải tiến

1. Thay thế heuristic evaluation bằng structured validator hoặc LLM-as-judge.
2. Thêm tool adapter thực tế (ticket DB/API) với idempotency keys.
3. Tích hợp dead-letter sink (queue hoặc ticketing system).
4. Bổ sung regression suite cho paraphrase-style hidden scenarios.
5. Thêm OpenTelemetry tracing cho observability production-grade.
