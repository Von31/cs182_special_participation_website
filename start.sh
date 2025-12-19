#!/bin/bash
# Start script for Render.com - runs both backend and Ed integration

echo "Starting CS182A/282A Participation Portal..."

# Add local edpy folder to Python path (fallback if pip install fails)
export PYTHONPATH="${PYTHONPATH}:$(pwd)/edpy"

# Set API_BASE_URL for ed_integration to connect to local backend
# Render sets $PORT dynamically, so we use that
export API_BASE_URL="http://localhost:${PORT:-8320}/api"
echo "API_BASE_URL set to: $API_BASE_URL"

# Start the backend API first (in background initially)
echo "Starting backend API on port ${PORT:-8320}..."
uvicorn backend_api:app --host 0.0.0.0 --port ${PORT:-8320} &
API_PID=$!

# Wait for API to be ready
echo "Waiting for API to start..."
sleep 5

# Start Ed integration in background
echo "Starting Ed integration..."
python ed_integration.py &
ED_PID=$!

# Keep the container running by waiting for the API process
echo "All services started. Waiting..."
wait $API_PID

# If API exits, also kill Ed integration
kill $ED_PID 2>/dev/null

