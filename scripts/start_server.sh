#!/bin/bash
# GLaDOS Server Start Script
# Comprehensive server startup with dependency checks, tests, and service management

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"
PYTHON_MIN_VERSION="3.10"
CONFIG_FILE="${CONFIG_FILE:-configs/glados_network_config.yaml}"
SKIP_TESTS="${SKIP_TESTS:-false}"
SKIP_RVC="${SKIP_RVC:-false}"

cd "$PROJECT_ROOT"

# Helper functions
print_header() {
    echo ""
    echo -e "${BLUE}============================================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}============================================================${NC}"
}

print_step() {
    echo -e "${GREEN}▶ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Version comparison
version_ge() {
    printf '%s\n%s\n' "$2" "$1" | sort -V -C
}

# Check Python version
check_python() {
    print_step "Checking Python installation..."

    if ! command_exists python3; then
        print_error "Python 3 not found!"
        echo "Please install Python ${PYTHON_MIN_VERSION} or higher"
        echo "  Arch Linux: sudo pacman -S python"
        echo "  Ubuntu/Debian: sudo apt install python3"
        exit 1
    fi

    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    print_success "Found Python ${PYTHON_VERSION}"

    if ! version_ge "$PYTHON_VERSION" "$PYTHON_MIN_VERSION"; then
        print_error "Python ${PYTHON_MIN_VERSION}+ required, found ${PYTHON_VERSION}"
        exit 1
    fi
}

# Check system dependencies
check_system_deps() {
    print_step "Checking system dependencies..."

    local missing_deps=()

    # Check for git
    if ! command_exists git; then
        missing_deps+=("git")
    fi

    # Check for docker (optional, for RVC)
    if ! command_exists docker && [ "$SKIP_RVC" != "true" ]; then
        print_warning "Docker not found - RVC service will be disabled"
        SKIP_RVC="true"
    fi

    # Check for docker-compose (optional, for RVC)
    if ! command_exists docker-compose && ! docker compose version >/dev/null 2>&1; then
        if [ "$SKIP_RVC" != "true" ]; then
            print_warning "Docker Compose not found - RVC service will be disabled"
            SKIP_RVC="true"
        fi
    fi

    if [ ${#missing_deps[@]} -ne 0 ]; then
        print_error "Missing system dependencies: ${missing_deps[*]}"
        echo ""
        echo "Install with:"
        echo "  Arch Linux: sudo pacman -S ${missing_deps[*]}"
        echo "  Ubuntu/Debian: sudo apt install ${missing_deps[*]}"
        exit 1
    fi

    print_success "System dependencies OK"
}

# Check Ollama service
check_ollama() {
    print_step "Checking Ollama service..."

    if ! command_exists ollama; then
        print_warning "Ollama not found in PATH"
        echo "GLaDOS requires Ollama for LLM processing"
        echo "Install from: https://ollama.ai"
        read -p "Continue anyway? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
        return
    fi

    # Check if Ollama is running
    if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
        print_warning "Ollama service not running"
        echo "Starting Ollama service..."
        ollama serve >/dev/null 2>&1 &
        sleep 3

        if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
            print_error "Failed to start Ollama service"
            echo "Please start Ollama manually: ollama serve"
            exit 1
        fi
    fi

    print_success "Ollama service running"
}

# Create or activate virtual environment
setup_venv() {
    print_step "Setting up Python virtual environment..."

    if [ ! -d "$VENV_DIR" ]; then
        print_step "Creating new virtual environment..."
        python3 -m venv "$VENV_DIR"
        print_success "Virtual environment created"
    else
        print_success "Virtual environment found"
    fi

    # Activate virtual environment
    source "$VENV_DIR/bin/activate"
    print_success "Virtual environment activated"
}

# Install Python dependencies
install_dependencies() {
    print_step "Installing Python dependencies..."

    # Upgrade pip first
    pip install --upgrade pip -q

    # Install from pyproject.toml
    if [ -f "pyproject.toml" ]; then
        print_step "Installing from pyproject.toml..."
        pip install -e ".[cuda]" -q
        print_success "Core dependencies installed"

        # Install dev dependencies for testing
        print_step "Installing dev dependencies..."
        pip install pytest pytest-cov pytest-timeout -q
        print_success "Dev dependencies installed"
    elif [ -f "requirements.txt" ]; then
        print_step "Installing from requirements.txt..."
        pip install -r requirements.txt -q
        print_success "Dependencies installed from requirements.txt"
    else
        print_error "No dependency file found (pyproject.toml or requirements.txt)"
        exit 1
    fi

    # Additional dependencies for Phase 1
    print_step "Installing additional dependencies..."
    pip install python-dateutil -q 2>/dev/null || true

    print_success "All dependencies installed"
}

# Start RVC container
start_rvc() {
    if [ "$SKIP_RVC" == "true" ]; then
        print_warning "Skipping RVC service (disabled)"
        return
    fi

    print_step "Starting RVC voice cloning service..."

    if [ ! -d "rvc" ]; then
        print_warning "RVC directory not found - skipping"
        return
    fi

    cd rvc

    # Check if already running
    if docker compose ps | grep -q "Up"; then
        print_success "RVC service already running"
    else
        docker compose up -d
        sleep 2

        if docker compose ps | grep -q "Up"; then
            print_success "RVC service started"
        else
            print_warning "RVC service failed to start (non-critical)"
        fi
    fi

    cd "$PROJECT_ROOT"
}

# Run tests
run_tests() {
    if [ "$SKIP_TESTS" == "true" ]; then
        print_warning "Skipping tests (SKIP_TESTS=true)"
        return
    fi

    print_header "Running Tests"

    # Check if pytest is available
    if ! python -c "import pytest" 2>/dev/null; then
        print_warning "pytest not installed - skipping tests"
        return
    fi

    # Run Phase 1 syntax validation
    print_step "Validating syntax..."
    if python3 << 'EOF'
import sys
import ast

files_to_check = [
    ("Exception Hierarchy", "src/glados/core/exceptions.py"),
    ("Component Base", "src/glados/core/component.py"),
    ("Thread-Safe State", "src/glados/core/state.py"),
    ("Circuit Breaker", "src/glados/core/resilience.py"),
]

all_valid = True
for name, filepath in files_to_check:
    try:
        with open(filepath, 'r') as f:
            ast.parse(f.read())
    except SyntaxError as e:
        print(f"✗ {name}: {e}")
        all_valid = False
    except FileNotFoundError:
        print(f"⚠ {name}: File not found")

sys.exit(0 if all_valid else 1)
EOF
    then
        print_success "Syntax validation passed"
    else
        print_error "Syntax validation failed"
        exit 1
    fi

    # Run unit tests if they exist
    if [ -d "tests/unit" ] && [ "$(ls -A tests/unit/*.py 2>/dev/null)" ]; then
        print_step "Running unit tests..."
        if pytest tests/unit -v --tb=short 2>&1 | tee /tmp/glados_test.log; then
            print_success "Unit tests passed"
        else
            print_warning "Some unit tests failed (see /tmp/glados_test.log)"
            read -p "Continue anyway? (y/N) " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                exit 1
            fi
        fi
    else
        print_warning "No unit tests found"
    fi

    print_success "All tests completed"
}

# Check if GLaDOS is already running
check_running() {
    print_step "Checking for existing GLaDOS process..."

    if pgrep -f "glados.cli start" >/dev/null; then
        print_warning "GLaDOS server appears to be already running"
        echo ""
        echo "PIDs: $(pgrep -f 'glados.cli start')"
        echo ""
        read -p "Kill existing process and restart? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            pkill -f "glados.cli start"
            sleep 2
            print_success "Stopped existing GLaDOS process"
        else
            exit 0
        fi
    fi
}

# Start GLaDOS server
start_server() {
    print_header "Starting GLaDOS Server"

    # Verify config file exists
    if [ ! -f "$CONFIG_FILE" ]; then
        print_error "Config file not found: $CONFIG_FILE"
        echo "Available configs:"
        ls -1 configs/*.yaml 2>/dev/null || echo "  No config files found"
        exit 1
    fi

    print_step "Using config: $CONFIG_FILE"
    print_step "Starting GLaDOS..."

    # Start server in background with logging
    LOG_FILE="/tmp/glados_server.log"
    nohup python -m glados.cli start --config "$CONFIG_FILE" > "$LOG_FILE" 2>&1 &
    SERVER_PID=$!

    print_success "GLaDOS server started (PID: $SERVER_PID)"
    print_step "Waiting for server to initialize..."

    sleep 3

    # Check if process is still running
    if kill -0 $SERVER_PID 2>/dev/null; then
        print_success "Server is running!"
        echo ""
        echo "Server PID: $SERVER_PID"
        echo "Log file: $LOG_FILE"
        echo "Config: $CONFIG_FILE"
        echo ""
        echo "Monitor logs: tail -f $LOG_FILE"
        echo "Stop server: kill $SERVER_PID"
        echo ""

        # Save PID for later
        echo $SERVER_PID > /tmp/glados_server.pid

    else
        print_error "Server failed to start!"
        echo ""
        echo "Last 20 lines of log:"
        tail -20 "$LOG_FILE"
        exit 1
    fi
}

# Show usage
show_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Start the GLaDOS server with dependency checks and testing.

Options:
  --config FILE       Use specific config file (default: $CONFIG_FILE)
  --skip-tests        Skip running tests
  --skip-rvc          Skip starting RVC service
  --help              Show this help message

Environment Variables:
  CONFIG_FILE         Path to config file
  SKIP_TESTS          Set to 'true' to skip tests
  SKIP_RVC            Set to 'true' to skip RVC service

Examples:
  $0                                    # Standard startup
  $0 --skip-tests                       # Skip tests
  $0 --config configs/custom.yaml       # Use custom config
  SKIP_RVC=true $0                      # Skip RVC service

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        --skip-tests)
            SKIP_TESTS="true"
            shift
            ;;
        --skip-rvc)
            SKIP_RVC="true"
            shift
            ;;
        --help)
            show_usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Main execution
main() {
    print_header "GLaDOS Server Startup"
    echo "Project: $PROJECT_ROOT"
    echo "Config: $CONFIG_FILE"
    echo ""

    check_python
    check_system_deps
    check_ollama
    setup_venv
    install_dependencies
    start_rvc
    run_tests
    check_running
    start_server

    print_header "Server Started Successfully!"
    print_success "GLaDOS v2.0 is now running with Phase 1 improvements"
    echo ""
    echo "Next steps:"
    echo "  1. Monitor logs: tail -f /tmp/glados_server.log"
    echo "  2. Start client: ./scripts/start_client.sh"
    echo "  3. Test conversation with Courtney!"
    echo ""
}

# Run main function
main
