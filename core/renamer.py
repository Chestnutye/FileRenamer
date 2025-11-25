import os
import shutil

def rename_file(old_path: str, new_name: str) -> bool:
    """
    Renames a file.
    
    Args:
        old_path: The absolute path to the existing file.
        new_name: The new filename (including extension).
        
    Returns:
        True if successful, False otherwise.
    """
    try:
        directory = os.path.dirname(old_path)
        new_path = os.path.join(directory, new_name)
        
        if os.path.exists(new_path):
            # Simple conflict resolution: don't overwrite, just fail or skip for now
            # Or maybe append a counter?
            # For this MVP, let's just skip to avoid data loss
            print(f"Target file already exists: {new_path}")
            return False
            
        os.rename(old_path, new_path)
        return True
    except Exception as e:
        print(f"Error renaming {old_path} to {new_name}: {e}")
        return False
