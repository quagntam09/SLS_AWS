FROM python:3.10-slim

# Ngăn Python tạo file .pyc và ép log đẩy thẳng ra console
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # CHỈNH SỬA TẠI ĐÂY: Thêm đường dẫn chứa module nsga2_improved vào PATH
    PYTHONPATH=/app/NSGA2IS-SLS

WORKDIR /app

# Cache requirements để build nhanh hơn
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy mã nguồn vào container
COPY NSGA2IS-SLS /app/NSGA2IS-SLS

# Thiết lập thư mục làm việc chính
WORKDIR /app/NSGA2IS-SLS

# Chạy worker dưới dạng module
CMD ["python", "-m", "server.app.worker"]