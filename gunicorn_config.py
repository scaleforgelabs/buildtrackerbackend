import multiprocessing

# Bind to all interfaces for production; use 127.0.0.1 only behind a reverse proxy
bind = "127.0.0.1:8000"

# Scale workers to CPU count. Rule of thumb: (2 × CPU cores) + 1
workers = multiprocessing.cpu_count() * 2 + 1

# Use Uvicorn workers for ASGI async support
worker_class = "uvicorn.workers.UvicornWorker"

# Max simultaneous connections per worker (default 100 is too low for high traffic)
worker_connections = 1000

# Timeouts
timeout = 60          # Kill worker if it doesn't respond in 60s (was 120 — too generous)
graceful_timeout = 30  # Allow 30s for in-flight requests during shutdown
keepalive = 30        # Keep connections alive for 30s (was 5 — too low for high traffic)

# Worker recycling — prevents memory leaks from accumulating over time
max_requests = 1000           # Recycle worker after 1000 requests
max_requests_jitter = 50      # Add randomness so all workers don't restart simultaneously

# Logging
accesslog = "/var/log/gunicorn/access.log"
errorlog = "/var/log/gunicorn/error.log"
loglevel = "info"

# Preload app for faster worker spawning and shared memory
preload_app = True
