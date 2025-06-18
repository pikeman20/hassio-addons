#!/usr/bin/env python3
"""
Version bumping script for Home Assistant Addon
Usage: python scripts/bump_version.py [major|minor|patch]
"""

import re
import sys
import os
import subprocess
from datetime import datetime
from pathlib import Path

def get_current_version(config_file):
    """Get current version from config.yaml"""
    with open(config_file, 'r') as f:
        content = f.read()
    
    match = re.search(r'version:\s*([0-9]+\.[0-9]+\.[0-9]+)', content)
    if match:
        return match.group(1)
    return None

def bump_version(version, bump_type):
    """Bump version based on semantic versioning"""
    major, minor, patch = map(int, version.split('.'))
    
    if bump_type == 'major':
        major += 1
        minor = 0
        patch = 0
    elif bump_type == 'minor':
        minor += 1
        patch = 0
    elif bump_type == 'patch':
        patch += 1
    
    return f"{major}.{minor}.{patch}"

def update_config_yaml(file_path, new_version):
    """Update version in config.yaml"""
    with open(file_path, 'r') as f:
        content = f.read()
    
    content = re.sub(r'version:\s*[0-9]+\.[0-9]+\.[0-9]+', f'version: {new_version}', content)
    
    with open(file_path, 'w') as f:
        f.write(content)

def update_dockerfile(file_path, new_version):
    """Update version in Dockerfile"""
    with open(file_path, 'r') as f:
        content = f.read()
    
    content = re.sub(r'io\.hass\.version="[0-9]+\.[0-9]+\.[0-9]+"', 
                     f'io.hass.version="{new_version}"', content)
    
    with open(file_path, 'w') as f:
        f.write(content)

def update_build_yaml(file_path, new_version):
    """Update version in build.yaml if exists"""
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            content = f.read()
        
        content = re.sub(r'version:\s*[0-9]+\.[0-9]+\.[0-9]+', f'version: {new_version}', content)
        
        with open(file_path, 'w') as f:
            f.write(content)

def update_changelog(file_path, new_version, bump_type):
    """Update CHANGELOG.md"""
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    # Create changelog if doesn't exist
    if not os.path.exists(file_path):
        with open(file_path, 'w') as f:
            f.write("# Changelog\n\n")
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    new_entry = f"""## [{new_version}] - {current_date}

### Changes
- {bump_type.capitalize()} version bump

"""
    
    # Insert after "# Changelog" line
    content = content.replace("# Changelog\n", f"# Changelog\n\n{new_entry}")
    
    with open(file_path, 'w') as f:
        f.write(content)

def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/bump_version.py [major|minor|patch]")
        sys.exit(1)
    
    bump_type = sys.argv[1].lower()
    if bump_type not in ['major', 'minor', 'patch']:
        print("Invalid bump type. Use: major, minor, or patch")
        sys.exit(1)
    
    # Set working directory to ha-mic-filter
    script_dir = Path(__file__).parent
    addon_dir = script_dir.parent
    os.chdir(addon_dir)
    
    # Get current version
    config_file = "config.yaml"
    current_version = get_current_version(config_file)
    if not current_version:
        print("Could not find current version in config.yaml")
        sys.exit(1)
    
    print(f"Current version: {current_version}")
    
    # Calculate new version
    new_version = bump_version(current_version, bump_type)
    print(f"New version: {new_version}")
    
    # Update files
    print("Updating files...")
    update_config_yaml(config_file, new_version)
    update_dockerfile("Dockerfile", new_version)
    update_build_yaml("build.yaml", new_version)
    update_changelog("CHANGELOG.md", new_version, bump_type)
    
    print(f"Version bumped from {current_version} to {new_version}")
    print(f"Files updated: config.yaml, Dockerfile, build.yaml (if exists), CHANGELOG.md")
    print(f"\nTo commit changes, run:")
    print(f"git add .")
    print(f"git commit -m '🔖 Bump version to {new_version}'")
    print(f"git tag v{new_version}")
    print(f"git push && git push --tags")

if __name__ == "__main__":
    main()