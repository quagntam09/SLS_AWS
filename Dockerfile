FROM python:3.10-slim

# Cho phép đổi thư mục source mà không phải sửa lệnh copy / PYTHONPATH trong nhiều chỗ.
ARG SOURCE_DIR=NSGA2IS-SLS

# Ngăn Python tạo file .pyc và ép log đẩy thẳng ra console
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/${SOURCE_DIR}:/app

WORKDIR /app

# Cache requirements để build nhanh hơn
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy mã nguồn vào container
COPY ${SOURCE_DIR} /app/${SOURCE_DIR}

# Thiết lập thư mục làm việc chính
WORKDIR /app/${SOURCE_DIR}

# Chạy worker dưới dạng module
CMD ["python", "-m", "server.app.worker"]