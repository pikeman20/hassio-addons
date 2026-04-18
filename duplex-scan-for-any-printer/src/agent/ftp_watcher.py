from __future__ import annotations

import os
import time
from typing import Callable
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class NewFileHandler(FileSystemEventHandler):
    def __init__(self, on_new_file: Callable[[str, str], None]):
        super().__init__()
        self.on_new_file = on_new_file

    def on_created(self, event):
        if event.is_directory:
            return
        
        try:
            # Log immediately when file is detected
            print(f"[FTPWatcher] File detected: {event.src_path}")
            # Small delay to ensure file is fully written (reduced from 0.2 to 0.05)
            time.sleep(0.05)
            path = event.src_path
            
            # Verify file exists and is readable
            if not os.path.exists(path):
                print(f"[FTPWatcher] ⚠️  File disappeared: {path}")
                return
            
            # Determine mode by parent folder name
            mode = os.path.basename(os.path.dirname(path))
            print(f"[FTPWatcher] Processing file in mode: {mode}")
            self.on_new_file(mode, path)
        except Exception as e:
            print(f"[FTPWatcher] ❌ Error handling file {event.src_path}: {str(e)}")
            import traceback
            traceback.print_exc()


class FTPWatcher:
    def __init__(self, root: str, subdirs: dict, on_new_file: Callable[[str, str], None]):
        self.root = root
        self.subdirs = subdirs
        self.on_new_file = on_new_file
        self._observer = Observer()

    def start(self):
        for name in self.subdirs.values():
            folder = os.path.join(self.root, name)
            os.makedirs(folder, exist_ok=True)
            self._observer.schedule(NewFileHandler(self.on_new_file), folder, recursive=False)
        self._observer.start()

    def stop(self):
        self._observer.stop()
        self._observer.join()
