"""
E2E Test Script for Web UI API
Test all endpoints without frontend
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import requests
import time

API_BASE = "http://localhost:8099"

def test_health():
    """Test health endpoint"""
    print("🔍 Testing health check...")
    response = requests.get(f"{API_BASE}/api/health")
    assert response.status_code == 200
    print("✅ Health check passed")
    return response.json()

def test_list_scans():
    """Test list scans endpoint"""
    print("\n🔍 Testing list scans...")
    response = requests.get(f"{API_BASE}/api/scans")
    assert response.status_code == 200
    data = response.json()
    print(f"✅ Found {len(data['scans'])} scans")
    return data['scans']

def test_scan_info(filename):
    """Test scan info endpoint"""
    print(f"\n🔍 Testing scan info for {filename}...")
    response = requests.get(f"{API_BASE}/api/scan/{filename}/info")
    assert response.status_code == 200
    info = response.json()
    print(f"✅ Scan info: {info['pages']} pages, {info['width']}x{info['height']}px")
    return info

def test_page_image(filename, page=0, size='medium'):
    """Test page image endpoint"""
    print(f"\n🔍 Testing page image {page} (size={size})...")
    response = requests.get(f"{API_BASE}/api/scan/{filename}/page/{page}?size={size}")
    assert response.status_code == 200
    assert response.headers['content-type'] == 'image/png'
    print(f"✅ Page image loaded: {len(response.content)} bytes")
    return response.content

def test_edit_pdf(filename):
    """Test edit/export endpoint"""
    print(f"\n🔍 Testing PDF edit for {filename}...")
    
    # Simple crop edit
    payload = {
        "filename": filename,
        "pages": [
            {
                "page": 0,
                "crop": {
                    "x": 100,
                    "y": 100,
                    "w": 400,
                    "h": 600
                }
            }
        ],
        "preview_width": 800
    }
    
    response = requests.post(f"{API_BASE}/api/edit", json=payload)
    assert response.status_code == 200
    result = response.json()
    print(f"✅ PDF edited: {result['file']} ({result['pages_processed']} pages)")
    return result

def test_download(filename):
    """Test download endpoint"""
    print(f"\n🔍 Testing download {filename}...")
    response = requests.get(f"{API_BASE}/api/download/{filename}")
    assert response.status_code == 200
    assert response.headers['content-type'] == 'application/pdf'
    print(f"✅ Downloaded: {len(response.content)} bytes")
    return response.content

def main():
    print("="*60)
    print("🚀 Web UI API E2E Test")
    print("="*60)
    
    try:
        # Test 1: Health check
        health = test_health()
        
        # Test 2: List scans
        scans = test_list_scans()
        
        if not scans:
            print("\n⚠️  No scans found in scan_out directory")
            print("💡 Create a test PDF first:")
            print("   python tests/test_main_scan_document.py")
            return
        
        # Use first scan for testing
        test_scan = scans[0]['filename']
        print(f"\n📄 Using test scan: {test_scan}")
        
        # Test 3: Get scan info
        info = test_scan_info(test_scan)
        
        # Test 4: Get page images (different sizes)
        for size in ['small', 'medium', 'large']:
            test_page_image(test_scan, 0, size)
        
        # Test 5: Edit PDF
        result = test_edit_pdf(test_scan)
        edited_file = result['file']
        
        # Test 6: Download edited PDF
        test_download(edited_file)
        
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED!")
        print("="*60)
        print("\n📊 Summary:")
        print(f"  - Health check: OK")
        print(f"  - Scans listed: {len(scans)}")
        print(f"  - Scan info: OK")
        print(f"  - Page images: OK (3 sizes)")
        print(f"  - PDF edit: OK")
        print(f"  - Download: OK")
        print("\n🎉 Backend API is ready!")
        print("\n🌐 Next: Test frontend at http://localhost:5173")
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except requests.exceptions.ConnectionError:
        print(f"\n❌ Cannot connect to {API_BASE}")
        print("💡 Start the server first:")
        print("   python src/web_ui_server.py")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
