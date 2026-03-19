#!/bin/bash

# AI Audio Hub Docker Deployment Script

set -e

echo "🚀 AI Audio Hub - Docker Deployment"
echo "=================================="

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker Desktop first."
    exit 1
fi

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose is not installed."
    exit 1
fi

# Create .env if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env file with your configuration before proceeding."
    echo "   Especially FRONTEND_ORIGIN for CORS."
    read -p "Press Enter after editing .env file..."
fi

# Function to show menu
show_menu() {
    echo ""
    echo "Select deployment option:"
    echo "1) Development (with hot reload)"
    echo "2) Production"
    echo "3) Stop all services"
    echo "4) View logs"
    echo "5) Rebuild and restart"
    echo "6) Cleanup (remove containers and volumes)"
    echo "7) Exit"
    echo ""
}

# Main loop
while true; do
    show_menu
    read -p "Enter your choice (1-7): " choice

    case $choice in
        1)
            echo "🏗️  Starting development environment..."
            docker-compose up --build
            ;;
        2)
            echo "🚀 Starting production environment..."
            docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
            echo "✅ Services started. Check status with: docker-compose ps"
            ;;
        3)
            echo "🛑 Stopping all services..."
            docker-compose down
            ;;
        4)
            echo "📋 Showing logs..."
            docker-compose logs -f
            ;;
        5)
            echo "🔄 Rebuilding and restarting..."
            docker-compose down
            docker-compose up --build -d
            ;;
        6)
            echo "🧹 Cleaning up..."
            docker-compose down -v --remove-orphans
            docker system prune -f
            ;;
        7)
            echo "👋 Goodbye!"
            exit 0
            ;;
        *)
            echo "❌ Invalid option. Please choose 1-7."
            ;;
    esac
done