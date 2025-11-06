#!/bin/bash

# Start script for Video Translation Web Application

echo "=============================================="
echo "  Video Translation Web Application"
echo "=============================================="
echo ""

# Check if DEEPL_API_KEY is set
if [ -z "$DEEPL_API_KEY" ]; then
    echo "⚠️  Warning: DEEPL_API_KEY environment variable not set!"
    echo ""
    echo "Please set your DeepL API key:"
    echo "export DEEPL_API_KEY=\"your-api-key-here\""
    echo ""
    echo "Press Ctrl+C to exit or Enter to continue anyway..."
    read
fi

# Navigate to webapp directory
cd "$(dirname "$0")"

echo "Starting Flask server..."
echo ""
echo "Access the application at: http://localhost:5000"
echo ""
echo "Press Ctrl+C to stop the server"
echo "=============================================="
echo ""

# Start Flask app
python3 app.py
