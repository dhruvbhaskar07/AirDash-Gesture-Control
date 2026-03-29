#!/bin/bash

# Move to the root directory
cd "$(dirname "$0")/.."

# ANSI color codes
CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

show_menu() {
    clear
    echo -e "${CYAN}=======================================================${NC}"
    echo -e "${CYAN}                AirDash Gesture Control                ${NC}"
    echo -e "${CYAN}=======================================================${NC}"
    echo ""
    echo "  [1] Setup Environment (Install dependencies)"
    echo "  [2] Run AirDash"
    echo "  [3] Exit"
    echo ""
    echo -e "${CYAN}=======================================================${NC}"
    echo -n "Enter your choice (1-3): "
}

setup() {
    clear
    echo -e "${CYAN}=======================================================${NC}"
    echo -e "${CYAN}                Setting up AirDash...                  ${NC}"
    echo -e "${CYAN}=======================================================${NC}"
    echo ""
    
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}[ERROR] Python 3 not found. Please install Python 3.10+.${NC}"
        read -p "Press enter to continue..."
        return
    fi

    if [ ! -d "venv" ]; then
        echo "[INFO] Creating virtual environment 'venv'..."
        python3 -m venv venv
    else
        echo "[INFO] Virtual environment 'venv' already exists."
    fi

    echo "[INFO] Activating virtual environment and installing dependencies..."
    source venv/bin/activate
    python3 -m pip install --upgrade pip
    pip install -r requirements.txt
    
    echo ""
    echo -e "${GREEN}[SUCCESS] Setup complete! You can now run AirDash.${NC}"
    read -p "Press enter to continue..."
}

run_app() {
    clear
    echo -e "${CYAN}=======================================================${NC}"
    echo -e "${CYAN}                  Starting AirDash...                  ${NC}"
    echo -e "${CYAN}=======================================================${NC}"
    echo ""
    
    if [ ! -f "venv/bin/activate" ]; then
        echo -e "${RED}[ERROR] Virtual environment not found. Please run Setup [1] first.${NC}"
        read -p "Press enter to continue..."
        return
    fi
    
    source venv/bin/activate
    python3 main.py
    
    echo ""
    echo -e "${GREEN}[INFO] Application closed.${NC}"
    read -p "Press enter to continue..."
}

while true; do
    show_menu
    read choice
    case $choice in
        1) setup ;;
        2) run_app ;;
        3) exit 0 ;;
        *) echo -e "${RED}Invalid choice. Please try again.${NC}"; sleep 1 ;;
    esac
done
