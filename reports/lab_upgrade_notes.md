# Ghi Chú Nâng Cấp Bài Thực Hành Ngày 08 (Theo Rubric trong README)

## 1) Mục tiêu nâng cấp

Tài liệu này tổng hợp các cải tiến đã thực hiện dựa trên tiêu chí chấm điểm trong README:

- Kiến trúc và lược đồ trạng thái (Architecture & State Schema)
- Hành vi đồ thị (Graph Behavior)
- Lưu trữ và khôi phục (Persistence & Recovery)
- Chỉ số và kiểm thử (Metrics & Tests)
- Báo cáo và bằng chứng demo (Report & Demo Evidence)
- Quy chuẩn sản xuất (Production Hygiene)

## 2) Các cải tiến đã thực hiện

### A. Hành vi đồ thị (Graph Behavior)

- Bộ phân loại (`classify`) đã được nâng cấp theo chính sách từ khoá có thứ tự ưu tiên:
  - `risky` → `tool` → `missing_info` → `error` → `simple`
- Có vòng lặp thử lại (retry loop) giới hạn bởi `attempt < max_attempts`.
- Có đường dẫn dead-letter khi vượt quá số lần thử lại tối đa.
- Có tính năng HITL (Human-in-the-Loop) với `interrupt()` trong `approval_node`.
- Có nhánh từ chối (reject) trong phê duyệt để yêu cầu hành động an toàn hơn.

Các file chính:

- `src/langgraph_agent_lab/nodes.py`
- `src/langgraph_agent_lab/routing.py`
- `src/langgraph_agent_lab/graph.py`

### B. Lưu trữ và khôi phục (Persistence & Recovery)

- Checkpointer bộ nhớ (Memory) hoạt động cho các lần chạy cục bộ.
- Checkpointer SQLite sử dụng `sqlite3.connect(..., check_same_thread=False)` kết hợp `PRAGMA journal_mode=WAL`.
- Thêm cơ chế kiểm tra khôi phục tự động (resume probe) trong CLI:
  - Chạy `interrupt` tại node phê duyệt
  - Tiếp tục bằng `Command(resume=...)`
  - Xác nhận luồng xử lý tiếp tục cho đến khi hoàn tất

Các file chính:

- `src/langgraph_agent_lab/persistence.py`
- `src/langgraph_agent_lab/cli.py`
- `src/langgraph_agent_lab/metrics.py` (trường `resume_success`)

### C. Giao diện Streamlit HITL

- Thêm ứng dụng Streamlit để demo phê duyệt/từ chối các trường hợp nguy hiểm.
- Giao diện hỗ trợ:
  - Chọn loại checkpointer (Memory / SQLite)
  - Nhập Thread ID
  - Chạy truy vấn
  - Xem nội dung ngắt (interrupt payload)
  - Gửi quyết định phê duyệt và tiếp tục luồng xử lý

File:

- `src/langgraph_agent_lab/streamlit_app.py`

### D. Chỉ số và báo cáo (Metrics & Report)

- File `outputs/metrics.json` bao gồm:
  - Kết quả đạt/không đạt của từng kịch bản
  - Số lần thử lại (retry count)
  - Số lần ngắt HITL (interrupt count)
  - Trạng thái khôi phục (`resume_success`)
- File `reports/lab_report.md` được sinh tự động theo mẫu sẵn sàng nộp bài:
  - Kiến trúc hệ thống
  - Lược đồ trạng thái
  - Bảng kết quả kịch bản
  - Phân tích lỗi
  - Bằng chứng lưu trữ trạng thái
  - Các phần mở rộng
  - Kế hoạch cải tiến

File:

- `src/langgraph_agent_lab/report.py`

### E. Sản phẩm demo bổ sung (Bonus)

- Thêm lệnh xuất sơ đồ Mermaid của đồ thị:
  - `python -m langgraph_agent_lab.cli export-graph --output outputs/graph.mmd`

File:

- `src/langgraph_agent_lab/cli.py`
- `Makefile` (lệnh `export-graph`)

## 3) Kết quả kiểm thử

Đã xác minh thành công:

- `python -m pytest -q`: ✅ đạt
- `python -m langgraph_agent_lab.cli run-scenarios --config configs/lab.yaml --output outputs/metrics.json`: ✅ đạt
- `python -m langgraph_agent_lab.cli validate-metrics --metrics outputs/metrics.json`: ✅ đạt
- `python -m langgraph_agent_lab.cli export-graph --output outputs/graph.mmd`: ✅ đạt

Các giá trị hiện tại:

- Tỷ lệ thành công: **100%**
- Tổng số lần thử lại: **3**
- Tổng số lần ngắt HITL: **2**
- Khôi phục sau ngắt: **thành công (true)**

## 4) Kịch bản demo để bảo vệ bài lab chi tiết

**A. Kiểm thử Graph qua dòng lệnh (CLI):**

1. Chạy benchmark 7 kịch bản tự động:
   - `python -m langgraph_agent_lab.cli run-scenarios --config configs/lab.yaml --output outputs/metrics.json`
2. Xác thực cấu trúc chỉ số đầu ra:
   - `python -m langgraph_agent_lab.cli validate-metrics --metrics outputs/metrics.json`
3. Xuất sơ đồ Mermaid của đồ thị:
   - `python -m langgraph_agent_lab.cli export-graph --output outputs/graph.mmd`

**B. Demo luồng hoạt động thông qua Streamlit HITL:**

Mở giao diện UI bằng lệnh:
`python -m streamlit run src/langgraph_agent_lab/streamlit_app.py`

**Kiểm thử các kịch bản bình thường (Checkpointer: `memory`):**
1. Nhập truy vấn đơn giản: `How do I reset my password?` -> Bấm "Run query".
   - *Kỳ vọng:* Hệ thống chạy tới `answer` -> hiển thị câu trả lời cuối cùng.
2. Nhập truy vấn thiếu thông tin: `Can you fix it?` -> Bấm "Run query" (trên một Thread mới).
   - *Kỳ vọng:* Tuyến `missing_info` được gọi, trả về câu hỏi yêu cầu làm rõ (clarify).
3. Nhập truy vấn lỗi: `Timeout failure while processing request` -> Bấm "Run query" (trên một Thread mới).
   - *Kỳ vọng:* Graph chạy báo lỗi, tự động thử lại (`retry` 2 lần) rồi mới thành công.

**C. Demo tính năng "Lưu trữ và Khôi phục sau sự cố" (Crash Recovery):**

1. **Khởi tạo trạng thái ngắt:**
   - Trên Sidebar, chọn **Checkpointer: `sqlite`**.
   - Bấm **"New thread"** để tạo một phiên xử lý mới và lưu lại mã **Thread ID** (ví dụ: `ui-thread-1234abcd`).
   - Nhập một truy vấn có độ rủi ro cao: `Refund this customer and send confirmation email`.
   - Bấm **"Run query"**.
   - Màn hình sẽ hiện cảnh báo màu vàng (*"Human approval required..."*) kèm JSON payload của hành động cần phê duyệt. Lúc này đồ thị đã dừng lại tại node `approval` và trạng thái đã được lưu vào file `checkpoints.db`.

2. **Giả lập sự cố ngắt kết nối (Crash):**
   - Quay lại Terminal đang chạy Streamlit, nhấn `Ctrl+C` để tắt hẳn ứng dụng (giả lập server bị sập).
   - Đóng hoàn toàn tab trình duyệt.

3. **Khôi phục trạng thái và tiếp tục (Resume):**
   - Mở lại server Streamlit bằng lệnh: `python -m streamlit run src/langgraph_agent_lab/streamlit_app.py`
   - Trên Sidebar, chắc chắn rằng **Checkpointer** vẫn đang chọn là `sqlite`.
   - Nhập lại đúng **Thread ID** vừa nãy (`ui-thread-1234abcd`) vào ô Thread ID.
   - Bấm **"Continue existing thread"**.
   - Giao diện sẽ tự động tải lại trạng thái cũ từ SQLite: thông báo *"Next node(s): approval"* xuất hiện cùng với bảng quyết định Approve/Reject.
   - Chọn `approve` và bấm **"Submit approval decision"**.
   - Đồ thị sẽ tiếp tục chạy từ điểm bị ngắt, đi qua `tool` -> `evaluate` -> `answer` và hoàn thành luồng xử lý thành công!