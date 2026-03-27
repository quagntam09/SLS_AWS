# NSGA2IS-SLS Worker systemd

Mẫu service cho worker long-polling SQS được đặt tại [deploy/systemd/nsga2-worker.service](deploy/systemd/nsga2-worker.service).

## File service chuẩn

```ini
[Unit]
Description=NSGA2IS-SLS background worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/nsga2is-sls/NSGA2IS-SLS
Environment=PYTHONPATH=/opt/nsga2is-sls/NSGA2IS-SLS
EnvironmentFile=-/etc/nsga2is-sls-worker.env
ExecStart=/opt/nsga2is-sls/NSGA2IS-SLS/venv/bin/python -m server.app.worker
Restart=always
RestartSec=5
KillSignal=SIGTERM
TimeoutStopSec=60
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

## Ý nghĩa các cấu hình chính

- `WorkingDirectory`: chạy từ root project để Python resolve đúng package `server.app.*`.
- `Environment=PYTHONPATH=...`: đảm bảo import module theo package root `NSGA2IS-SLS`.
- `ExecStart`: dùng venv riêng để tránh phụ thuộc Python hệ thống.
- `Restart=always` và `RestartSec=5`: tự khởi động lại nếu process crash hoặc bị kill, chờ 5 giây trước khi restart.
- `StandardOutput=journal` và `StandardError=journal`: đẩy log vào `journald` để xem bằng `journalctl`.
- `EnvironmentFile=-/etc/nsga2is-sls-worker.env`: file env do script EC2 tạo ra, chứa `QUEUE_URL`, `TABLE_NAME`, `BUCKET_NAME` và các biến runtime liên quan.

## Lưu ý vận hành

- SQS visibility timeout phải đủ dài cho thời gian xử lý thực tế; code hiện dùng 1800 giây để phù hợp workload nặng.
- Nếu cần debug nhanh, `journalctl -u nsga2-worker.service -n 50 -o cat` thường đủ để xem lỗi gần nhất.

## Các lệnh triển khai trên EC2

### 1. Tạo file service

```bash
sudo tee /etc/systemd/system/nsga2-worker.service >/dev/null <<'EOF'
[Unit]
Description=NSGA2IS-SLS background worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/nsga2is-sls/NSGA2IS-SLS
Environment=PYTHONPATH=/opt/nsga2is-sls/NSGA2IS-SLS
EnvironmentFile=-/etc/nsga2is-sls-worker.env
ExecStart=/opt/nsga2is-sls/NSGA2IS-SLS/venv/bin/python -m server.app.worker
Restart=always
RestartSec=5
KillSignal=SIGTERM
TimeoutStopSec=60
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
```

### 2. Reload systemd

```bash
sudo systemctl daemon-reload
```

### 3. Enable và start service

```bash
sudo systemctl enable --now nsga2-worker.service
```

### 4. Kiểm tra trạng thái

```bash
sudo systemctl status nsga2-worker.service --no-pager
```

### 5. Xem log realtime

```bash
sudo journalctl -u nsga2-worker.service -f -o cat
```

## Lưu ý về path thực tế

Nếu EC2 của bạn dùng thư mục khác, chỉ cần sửa đồng bộ 3 chỗ trong unit: `WorkingDirectory`, `Environment=PYTHONPATH=...`, và `ExecStart`.