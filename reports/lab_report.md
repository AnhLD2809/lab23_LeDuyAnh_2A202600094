# Báo Cáo Bài Thực Hành Ngày 08 — LangGraph Agentic Orchestration

## 1. Thông tin sinh viên

- Họ và tên: Lê Duy Anh
- Mã số sinh viên: 2A202600094
- Repo/commit: https://github.com/AnhLD2809/lab23_LeDuyAnh_2A202600094.git
- Ngày nộp: 2026-05-11

## 2. Kiến trúc hệ thống

Hệ thống được xây dựng dưới dạng một đồ thị trạng thái (StateGraph) sử dụng LangGraph, bao gồm 11 node xử lý:

- **`intake`** — Chuẩn hoá truy vấn đầu vào (loại bỏ khoảng trắng thừa, che giấu thông tin nhạy cảm PII) và ghi lại sự kiện kiểm toán.
- **`classify`** — Phân loại truy vấn thành một trong 5 tuyến (route) dựa trên chính sách ưu tiên từ khoá: `risky` → `tool` → `missing_info` → `error` → `simple`.
- **`tool`** — Gọi công cụ giả lập (mock tool); mô phỏng lỗi tạm thời cho các kịch bản thuộc tuyến `error` để minh hoạ vòng lặp thử lại.
- **`evaluate`** — Kiểm tra kết quả từ `tool` để quyết định thử lại hay chuyển sang trả lời. Đây là bước kiểm tra "đã xong chưa?" — ưu thế chính của LangGraph so với LCEL.
- **`retry`** — Ghi nhận lần thử lại, tăng biến đếm `attempt`. Nếu `attempt ≥ max_attempts` thì chuyển sang `dead_letter`.
- **`answer`** — Tạo câu trả lời cuối cùng dựa trên kết quả từ công cụ và trạng thái phê duyệt.
- **`clarify`** — Yêu cầu người dùng bổ sung thông tin khi truy vấn quá mơ hồ hoặc khi hành động rủi ro bị từ chối.
- **`risky_action`** — Chuẩn bị hành động có mức rủi ro cao (ví dụ: hoàn tiền, xoá tài khoản) kèm theo bằng chứng và lý do đánh giá rủi ro.
- **`approval`** — Bước phê duyệt của con người (Human-in-the-Loop). Hỗ trợ chế độ `interrupt()` thực tế khi đặt biến môi trường `LANGGRAPH_INTERRUPT=true`; mặc định sử dụng phê duyệt giả lập để chạy tự động trong CI/test.
- **`dead_letter`** — Ghi lại các yêu cầu không thể xử lý sau khi đã vượt quá số lần thử lại tối đa, phục vụ xem xét thủ công.
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
| `route`, `risk_level`, `attempt`, `approval`, `evaluation_result` | ghi đè (overwrite) | Chỉ cần giữ giá trị quyết định/trạng thái mới nhất |
| `messages` | nối thêm (append) | Lưu toàn bộ lịch sử hội thoại phục vụ kiểm toán |
| `tool_results` | nối thêm (append) | Lưu lịch sử kết quả từ công cụ để phục vụ gỡ lỗi |
| `errors` | nối thêm (append) | Theo dõi lịch sử lỗi qua các vòng thử lại |
| `events` | nối thêm (append) | Ghi lại toàn bộ chuỗi sự kiện trong luồng xử lý để giám sát và chấm điểm |

## 4. Kết quả chạy kịch bản

### Tổng quan

- Tổng số kịch bản: **7**
- Tỷ lệ thành công: **100,00%**
- Số node trung bình mỗi lần chạy: **6,43**
- Tổng số lần thử lại: **3**
- Tổng số lần ngắt HITL: **2**
- Khôi phục sau ngắt: **thành công**

### Chi tiết từng kịch bản

| Kịch bản | Tuyến kỳ vọng | Tuyến thực tế | Thành công | Thử lại | Ngắt HITL |
|---|---|---|---:|---:|---:|
| S01_simple | simple | simple | ✅ | 0 | 0 |
| S02_tool | tool | tool | ✅ | 0 | 0 |
| S03_missing | missing_info | missing_info | ✅ | 0 | 0 |
| S04_risky | risky | risky | ✅ | 0 | 1 |
| S05_error | error | error | ✅ | 2 | 0 |
| S06_delete | risky | risky | ✅ | 0 | 1 |
| S07_dead_letter | error | error | ✅ | 1 | 0 |

## 5. Phân tích lỗi và trường hợp biên

1. **Vòng lặp thử lại và lỗi công cụ:**
   - Kịch bản S05 (`error`) mô phỏng lỗi tạm thời (transient failure) trong 2 lần gọi đầu tiên. Hệ thống tự động thử lại và thành công ở lần thứ 3. Cơ chế giới hạn thử lại (`attempt < max_attempts`) đảm bảo vòng lặp không chạy vô hạn.
   - Kịch bản S07 (`dead_letter`) đặt `max_attempts=1`, khiến yêu cầu bị chuyển thẳng sang `dead_letter` ngay sau lần thử đầu tiên — đúng như thiết kế.

2. **Hành động rủi ro khi không được phê duyệt:**
   - Kịch bản S04 và S06 yêu cầu hành động có rủi ro cao (hoàn tiền, xoá tài khoản). Đồ thị bắt buộc dừng tại node `approval` trước khi thực thi. Trong chế độ HITL thực (`LANGGRAPH_INTERRUPT=true`), nếu bị từ chối, luồng sẽ chuyển sang `clarify` để yêu cầu người dùng đưa ra phương án thay thế an toàn hơn.

3. **Truy vấn mơ hồ:**
   - Kịch bản S03 ("Can you fix it?") được nhận diện là thiếu thông tin nhờ kiểm tra số lượng từ (< 5 từ) kết hợp với sự hiện diện của đại từ mơ hồ ("it", "this", "that"). Hệ thống yêu cầu bổ sung ngữ cảnh thay vì đoán mò.

## 6. Bằng chứng về lưu trữ trạng thái và khôi phục (Persistence & Recovery)

- Sử dụng `MemorySaver` làm checkpointer mặc định khi phát triển. Đường dẫn `SqliteSaver` với chế độ WAL (Write-Ahead Logging) đã được chuẩn bị sẵn cho các bản demo khôi phục sau sự cố.
- Mỗi kịch bản được gán một `thread_id` riêng biệt (ví dụ: `thread-S04_risky`), đảm bảo lịch sử trạng thái được lưu trữ độc lập cho từng luồng.
- Kết quả kiểm tra khôi phục: sau khi `interrupt()` được kích hoạt tại node `approval`, hệ thống tiếp tục xử lý thành công bằng `Command(resume=...)` mà không mất dữ liệu trạng thái (`resume_success: true`).

## 7. Các phần mở rộng đã thực hiện

1. **HITL thực tế (Human-in-the-Loop):** Hỗ trợ `interrupt()` của LangGraph tại node `approval` khi đặt biến môi trường `LANGGRAPH_INTERRUPT=true`. Người dùng có thể phê duyệt, từ chối hoặc chỉnh sửa quyết định thông qua giao diện.
2. **Giao diện Streamlit:** Xây dựng giao diện web cho phép nhập truy vấn, xem luồng xử lý theo thời gian thực, và thao tác phê duyệt/từ chối rồi tiếp tục luồng bằng `Command(resume=...)`.
3. **SQLite Checkpointer:** Cấu hình `SqliteSaver` với `sqlite3.connect()` và chế độ WAL, sẵn sàng cho demo khôi phục sau sự cố (crash-recovery).

## 8. Kế hoạch cải tiến

1. **Nâng cấp bộ đánh giá:** Thay thế phương pháp đánh giá kết quả công cụ bằng heuristic hiện tại bằng bộ xác thực có cấu trúc (structured validator) hoặc chính sách LLM-as-judge để tăng độ chính xác.
2. **Tích hợp công cụ thực tế:** Thêm các bộ điều hợp công cụ thật (kết nối cơ sở dữ liệu phiếu hỗ trợ / API) kèm theo khoá đảm bảo tính idempotent.
3. **Hệ thống cảnh báo Dead-Letter:** Tích hợp hàng đợi dead-letter hoặc hệ thống quản lý phiếu để gửi cảnh báo tự động khi có yêu cầu không thể xử lý.
4. **Bộ kiểm thử hồi quy:** Bổ sung bộ kịch bản kiểm thử dạng diễn giải lại (paraphrase) tương tự các kịch bản ẩn trong bài chấm để đảm bảo hệ thống không bị cứng hoá theo đầu vào cụ thể.
