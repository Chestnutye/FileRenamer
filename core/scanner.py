import os
from typing import List, Generator

def scan_directory(root_path: str, ignore_hidden: bool = True) -> Generator[str, None, None]:
    """
    Recursively scans a directory for files.
    
    Args:
        root_path: The root directory to scan.
        ignore_hidden: Whether to ignore hidden files (starting with .) and system files.
        
    Yields:
        Absolute paths to files found.
    """
    system_files = {'.DS_Store', 'Thumbs.db'}
    
    for dirpath, dirnames, filenames in os.walk(root_path):
        # Modify dirnames in-place to skip hidden directories
        if ignore_hidden:
            dirnames[:] = [d for d in dirnames if not d.startswith('.')]
            
        for filename in filenames:
            if ignore_hidden:
                if filename.startswith('.'):
                    continue
                if filename in system_files:
                    continue
            
            yield os.path.join(dirpath, filename)
