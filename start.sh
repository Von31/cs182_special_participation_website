#!/bin/bash
# Start script for Render.com - runs both backend and Ed integration

echo "Starting CS182A/282A Participation Portal..."

# Start Ed integration in background
echo "Starting Ed integration..."
python ed_integration.py &
ED_PID=$!

# Give Ed integration time to initialize
sleep 2

# Start the backend API (foreground - this keeps the container running)
echo "Starting backend API..."
uvicorn backend_api:app --host 0.0.0.0 --port ${PORT:-8320}

# If uvicorn exits, also kill Ed integration
kill $ED_PID 2>/dev/null

