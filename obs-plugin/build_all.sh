#!/bin/bash

# Build script for OBS Mic Filter - Creates both .so (Linux) and .dll (Windows)
# Run this in WSL or Linux environment

set -e  # Exit on any error

echo "=== OBS Mic Filter Build Script ==="
echo "Building both Linux (.so) and Windows (.dll) versions"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check requirements
print_status "Checking build requirements..."

# Check if we're in the right directory
if [ ! -f "CMakeLists.txt" ]; then
    print_error "CMakeLists.txt not found. Please run this script from the obs-mic-filter directory."
    exit 1
fi

# Check if OBS studio directory exists
if [ ! -d "../obs-studio/plugins/obs-filters/rnnoise" ]; then
    print_error "RNNoise source not found. Make sure obs-studio is in the parent directory."
    exit 1
fi

print_success "Requirements check passed"

# Check for required tools
print_status "Checking for required build tools..."

# Check for native GCC
if ! command -v gcc &> /dev/null; then
    print_error "GCC not found. Please install build-essential."
    exit 1
fi

# Check for MinGW (for Windows cross-compilation)
if ! command -v x86_64-w64-mingw32-gcc &> /dev/null; then
    print_warning "MinGW-w64 not found. Installing..."
    sudo apt-get update
    sudo apt-get install -y mingw-w64
fi

# Check for CMake
if ! command -v cmake &> /dev/null; then
    print_error "CMake not found. Please install cmake."
    exit 1
fi

print_success "All build tools are available"

# Function to build for a specific target
build_target() {
    local target_name=$1
    local build_dir=$2
    local cmake_args=$3
    local make_cmd=${4:-"make"}
    
    print_status "Building $target_name..."
    
    # Clean and create build directory
    if [ -d "$build_dir" ]; then
        print_status "Cleaning previous $target_name build..."
        rm -rf "$build_dir"
    fi
    
    # Also clean CMake cache files in root directory
    if [ -f "CMakeCache.txt" ]; then
        print_status "Cleaning CMake cache files..."
        rm -f CMakeCache.txt
        rm -rf CMakeFiles/
    fi
    
    mkdir -p "$build_dir"
    
    # Configure with CMake
    print_status "Configuring $target_name with CMake..."
    if ! (cd "$build_dir" && cmake .. $cmake_args); then
        print_error "CMake configuration failed for $target_name"
        return 1
    fi
    
    # Build
    print_status "Compiling $target_name..."
    if ! (cd "$build_dir" && $make_cmd -j$(nproc)); then
        print_error "Build failed for $target_name"
        return 1
    fi
    
    return 0
}

# Build Linux version (.so)
print_status "Starting Linux build..."
if build_target "Linux (.so)" "build-linux" ""; then
    if [ -f "build-linux/libobs-mic-filter.so" ]; then
        file_size=$(du -h "build-linux/libobs-mic-filter.so" | cut -f1)
        print_success "Linux build completed: libobs-mic-filter.so ($file_size)"
    else
        print_error "Linux build completed but .so file not found"
    fi
else
    print_error "Linux build failed"
    exit 1
fi

echo ""

# Build Windows version (.dll)
print_status "Starting Windows cross-compilation build..."
cmake_args_win="-DCMAKE_SYSTEM_NAME=Windows -DCMAKE_C_COMPILER=x86_64-w64-mingw32-gcc -DCMAKE_RC_COMPILER=x86_64-w64-mingw32-windres"

if build_target "Windows (.dll)" "build-win64" "$cmake_args_win"; then
    if [ -f "build-win64/obs-mic-filter.dll" ]; then
        file_size=$(du -h "build-win64/obs-mic-filter.dll" | cut -f1)
        print_success "Windows build completed: obs-mic-filter.dll ($file_size)"
    else
        print_error "Windows build completed but .dll file not found"
    fi
else
    print_error "Windows build failed"
    exit 1
fi

echo ""
echo "=== Build Summary ==="

# Display results
echo ""
print_status "Build artifacts:"

if [ -f "build-linux/libobs-mic-filter.so" ]; then
    linux_size=$(du -h "build-linux/libobs-mic-filter.so" | cut -f1)
    echo "  ✅ Linux:   build-linux/libobs-mic-filter.so ($linux_size)"
else
    echo "  ❌ Linux:   build-linux/libobs-mic-filter.so (missing)"
fi

if [ -f "build-win64/obs-mic-filter.dll" ]; then
    windows_size=$(du -h "build-win64/obs-mic-filter.dll" | cut -f1)
    echo "  ✅ Windows: build-win64/obs-mic-filter.dll ($windows_size)"
else
    echo "  ❌ Windows: build-win64/obs-mic-filter.dll (missing)"
fi

echo ""
print_status "File information:"

# Show file details
if [ -f "build-linux/libobs-mic-filter.so" ]; then
    echo "Linux (.so):"
    file build-linux/libobs-mic-filter.so | sed 's/^/  /'
    ldd build-linux/libobs-mic-filter.so 2>/dev/null | head -5 | sed 's/^/    /'
    echo ""
fi

if [ -f "build-win64/obs-mic-filter.dll" ]; then
    echo "Windows (.dll):"
    file build-win64/obs-mic-filter.dll | sed 's/^/  /'
    echo ""
fi

echo ""
print_success "🎉 All builds completed successfully!"

echo ""
print_status "Usage instructions:"
echo "  Linux:   Use build-linux/libobs-mic-filter.so"
echo "  Windows: Use build-win64/obs-mic-filter.dll"
echo ""
echo "To test:"
echo "  Linux:   python python_realtime_test.py"
echo "  Windows: Copy .dll to Windows and run python script there"
echo ""
echo "Make sure to install Python dependencies:"
echo "  pip install -r requirements.txt"