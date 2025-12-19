#!/bin/bash

echo "╔════════════════════════════════════════════════════════════╗"
echo "║   CS182A/282A Ed Integration Startup Script                ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found!"
    echo "   Please copy .env.example to .env and fill in your credentials"
    exit 1
fi

# Check if edpy is installed
if [ ! -d "edpy" ]; then
    echo "⚠️  edpy directory not found. Cloning..."
    git clone https://github.com/bachtran02/edpy.git
    echo "✓ edpy cloned"
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -q -r requirements.txt
echo "✓ Dependencies installed"

echo ""
echo "════════════════════════════════════════════════════════════"
echo ""
echo "Choose what to run:"
echo ""
echo "  1) Backend API Server only"
echo "  2) Ed Integration only" 
echo "  3) Both (recommended)"
echo "  4) Exit"
echo ""
read -p "Enter your choice (1-4): " choice

case $choice in
    1)
        echo ""
        echo "Starting Backend API Server..."
        python backend_api.py
        ;;
    2)
        echo ""
        echo "Starting Ed Integration..."
        python ed_integration.py
        ;;
    3)
        echo ""
        echo "Starting both services..."
        echo "Opening two terminal tabs..."
        
        # For macOS
        if [[ "$OSTYPE" == "darwin"* ]]; then
            osascript -e 'tell application "Terminal" to do script "cd \"'"$(pwd)"'\" && source venv/bin/activate && python backend_api.py"'
            sleep 2
            osascript -e 'tell application "Terminal" to do script "cd \"'"$(pwd)"'\" && source venv/bin/activate && python ed_integration.py"'
        # For Linux with gnome-terminal
        elif command -v gnome-terminal &> /dev/null; then
            gnome-terminal -- bash -c "cd $(pwd) && source venv/bin/activate && python backend_api.py; exec bash"
            sleep 2
            gnome-terminal -- bash -c "cd $(pwd) && source venv/bin/activate && python ed_integration.py; exec bash"
        else
            echo ""
            echo "Please open two terminal windows and run:"
            echo ""
            echo "Terminal 1: python backend_api.py"
            echo "Terminal 2: python ed_integration.py"

            python backend_api.py &
            python ed_integration.py 
        fi
        ;;
    4)
        echo "Exiting..."
        exit 0
        ;;
    *)
        echo "Invalid choice. Exiting..."
        exit 1
        ;;
esac