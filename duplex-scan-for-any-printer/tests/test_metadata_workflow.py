"""
Test metadata workflow:
1. Load scan to canvas
2. Add crop box
3. Export with metadata
4. Load edited file → bbox should restore
"""
import requests
import json

API_BASE = "http://localhost:8099"

def test_metadata_workflow():
    print("🧪 Testing Metadata Workflow\n")
    
    # 1. Get scans
    response = requests.get(f"{API_BASE}/api/scans")
    scans = response.json()['scans']
    
    if not scans:
        print("❌ No scans found")
        return
    
    test_file = scans[0]['filename']
    print(f"📄 Using: {test_file}\n")
    
    # 2. Get scan info
    info = requests.get(f"{API_BASE}/api/scan/{test_file}/info").json()
    print(f"📐 Dimensions: {info['width']}x{info['height']}px")
    print(f"📑 Pages: {info['pages']}\n")
    
    # 3. Create edit with crop box
    edit_request = {
        "filename": test_file,
        "preview_width": 800,
        "pages": [
            {
                "page": 0,
                "crop": {
                    "x": 100,
                    "y": 150,
                    "w": 400,
                    "h": 600
                }
            }
        ]
    }
    
    print("✂️ Applying crop box (100, 150, 400x600)...")
    response = requests.post(f"{API_BASE}/api/edit", json=edit_request)
    result = response.json()
    
    edited_file = result['file']
    print(f"✅ Created: {edited_file}")
    print(f"💾 Metadata saved: {result.get('metadata_saved', False)}\n")
    
    # 4. Load metadata
    print("📖 Reading metadata...")
    metadata = requests.get(f"{API_BASE}/api/scan/{edited_file}/metadata").json()
    
    if metadata.get('has_metadata'):
        print("✅ Metadata found:")
        print(f"  Original: {metadata['original_file']}")
        print(f"  Preview width: {metadata['preview_width']}")
        print(f"  Crop box: {json.dumps(metadata['pages'][0]['crop'], indent=4)}")
        print("\n🎉 Metadata workflow successful!")
        print("\n💡 Now load edited file in web UI:")
        print(f"   1. Click 'Load to Canvas' on {edited_file}")
        print(f"   2. Bbox should restore at correct position")
        print(f"   3. Try zoom in/out - bbox should scale correctly")
    else:
        print("❌ No metadata found")

if __name__ == "__main__":
    try:
        test_metadata_workflow()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
