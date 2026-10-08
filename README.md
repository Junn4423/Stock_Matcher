# Stock Script Matcher

Tool Python 3.10 chạy local trên Windows, dùng transcript để tạo shot list và tìm video stock tương ứng trên Pexels.

## Kết quả đầu ra

Mỗi job tạo một file ZIP gồm:

- `*_stock_plan.docx`: bảng đẹp gồm transcript, visual query, thumbnail, link Pexels, direct MP4, timing và score.
- `timeline.csv`: dữ liệu timeline để import hoặc xử lý tiếp.
- `manifest.json`: toàn bộ kết quả có cấu trúc.
- `subtitles.srt`: phụ đề tự sinh theo thời lượng đọc ước tính.
- `videos/`: các clip đã chọn nếu bật tải video.
- `rough_cut.mp4`: video B-roll tự ghép nếu bật rough-cut.

## Khởi động trên Windows

1. Giải nén project vào thư mục không có quyền hạn chế.
2. Double-click `START_STOCK_MATCHER.bat`.
3. Lần chạy đầu tool sẽ tự tạo `.venv` và cài dependencies.
4. Trình duyệt mở tại `http://127.0.0.1:8765`.
5. Nhập Pexels API key, chọn transcript và chạy.

Python 3.10 trở lên là đủ. API key có thể nhập mỗi lần hoặc đặt trong `.env`:

```env
PEXELS_API_KEY=your_key_here
```

Lấy key tại: https://www.pexels.com/api/

## Chạy bằng CLI

```bat
.venv\Scripts\activate
python cli.py sample_transcript.txt --api-key YOUR_KEY --orientation landscape
```

Tải video và ghép rough-cut:

```bat
python cli.py sample_transcript.txt --api-key YOUR_KEY --download --compose
```

## Thuật toán matching

Pipeline mặc định không cần dịch vụ AI trả phí:

1. Đọc `DOCX`, `TXT`, `MD`, `PDF`, `SRT`, `VTT`.
2. Chuẩn hóa văn bản và giữ ranh giới đoạn.
3. Tách câu có xử lý viết tắt, bullet, câu quá dài và đoạn quá ngắn.
4. Ước lượng thời lượng đọc dựa trên số từ/phút.
5. Dùng semantic bridge Việt–Anh để chuyển ý trừu tượng thành cảnh quay cụ thể.
6. Xác định category, mood, keywords và tạo truy vấn Pexels.
7. Tìm video qua endpoint chính thức `https://api.pexels.com/v1/videos/search`.
8. Chấm điểm theo độ ưu tiên truy vấn, vị trí kết quả, tỷ lệ khung hình, độ phân giải, thời lượng, creator và mức độ lặp clip.
9. Chọn file MP4 gần Full HD để cân bằng chất lượng và dung lượng.
10. Cache truy vấn bằng SQLite, retry lỗi mạng, đọc quota từ response headers.

## Cấu hình quan trọng

Mở `.env` để chỉnh:

```env
MAX_UPLOAD_MB=20
MAX_SEGMENTS=300
CACHE_TTL_HOURS=168
REQUEST_TIMEOUT_SECONDS=30
MAX_API_RETRIES=4
JOB_WORKERS=2
```

Các tham số trên giao diện:

- **Smart**: merge câu ngắn, chia câu dài và giữ mỗi đoạn đủ ý.
- **Landscape / Portrait / Square**: gửi filter tương ứng sang Pexels và dùng khi dựng video.
- **Words per minute**: quyết định thời lượng clip cần lấy.
- **Queries per segment**: tối đa 1–4; tool chỉ gọi fallback khi query đầu có ít candidate.
- **Results per query**: càng cao càng có nhiều lựa chọn nhưng response lớn hơn.

## Production notes

- API key không được ghi vào DOCX, manifest hoặc log.
- Upload có whitelist extension, giới hạn dung lượng và tên file được làm sạch.
- Direct download chỉ chấp nhận HTTPS thuộc miền `pexels.com`.
- Cache SQLite dùng WAL và lock để tránh lỗi khi có nhiều job.
- Job có trạng thái, progress, cảnh báo, retry và file kết quả riêng.
- Video được chống trùng theo ID và giảm điểm nếu lặp creator quá nhiều.
- Rough-cut tự crop/scale về đúng khung hình, loop clip ngắn, trim theo timing rồi concat.

## Giới hạn thực tế

Không có thuật toán nào đảm bảo mọi câu trừu tượng sẽ luôn có một stock clip chính xác tuyệt đối. Pexels chỉ trả metadata video và thứ hạng tìm kiếm, không cung cấp caption chi tiết cho từng clip trong API. Vì vậy tool ưu tiên tạo một rough-cut sử dụng được ngay, nhưng các nội dung nhạy cảm, thương hiệu cụ thể, sự kiện hiếm hoặc câu có nhiều lớp nghĩa vẫn nên được xem lại trước khi xuất bản.

Pexels yêu cầu attribution/link back phù hợp và có quota API mặc định. DOCX đã chèn link Pexels và credit creator khi dữ liệu có sẵn.

## Test

```bat
.venv\Scripts\activate
python -m pytest -q
```

## Cấu trúc project

```text
app/
  main.py                  FastAPI service
  services/
    text_extractor.py      đọc transcript
    segmenter.py           phân đoạn
    query_engine.py        semantic query cục bộ
    pexels_client.py       API, cache, retry, quota
    ranker.py              scoring và chọn MP4
    downloader.py          tải video an toàn
    composer.py            dựng rough-cut
    docx_exporter.py       xuất DOCX
    job_service.py         orchestration và ZIP
cli.py
START_STOCK_MATCHER.bat
```
