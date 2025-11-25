import re
import os
from typing import Dict, Optional

class MetadataParser:
    def __init__(self, id_min_len: int = 8, id_max_len: int = 12, standard_project_name: str = "", standard_class_name: str = "", excluded_tokens: list = None):
        self.id_min_len = id_min_len
        self.id_max_len = id_max_len
        self.standard_project_name = standard_project_name
        self.standard_class_name = standard_class_name
        self.excluded_tokens = [t.lower() for t in excluded_tokens] if excluded_tokens else []
        
        # Regex for Student ID (Anchor)
        self.id_pattern = re.compile(rf'\d{{{self.id_min_len},{self.id_max_len}}}')
        
        # Regex for Chinese Name (2-4 chars)
        self.cn_name_pattern = re.compile(r'[\u4e00-\u9fa5]{2,4}')
        
        # Regex for English Name (Letters and spaces)
        self.en_name_pattern = re.compile(r'[a-zA-Z][a-zA-Z\s]*')
        
        # Keywords for Class
        # Enhanced to support Chinese numbers (e.g. 一班, 十二班)
        self.class_keywords = ["班", "级", "Class", "Section"]
        self.cn_num_pattern = r'[一二三四五六七八九十]+'

    def preprocess_filename(self, filename: str) -> str:
        """
        Preprocesses the filename to handle "adhesion" cases where separators are missing.
        """
        # 1. Separate Chinese and English/Numbers
        filename = re.sub(r'([\u4e00-\u9fa5])([a-zA-Z0-9])', r'\1 \2', filename)
        filename = re.sub(r'([a-zA-Z0-9])([\u4e00-\u9fa5])', r'\1 \2', filename)
        
        # 2. Separate Lowercase and Uppercase (CamelCase adhesion)
        filename = re.sub(r'([a-z])([A-Z])', r'\1 \2', filename)
        
        # 3. Separate Letters and Long Numbers (ID adhesion)
        # We only split if the number sequence is long enough to be an ID
        filename = re.sub(rf'([a-zA-Z])(\d{{{self.id_min_len},}})', r'\1 \2', filename)
        
        # 4. Separate Long Numbers and Letters
        filename = re.sub(rf'(\d{{{self.id_min_len},}})([a-zA-Z])', r'\1 \2', filename)

        # 5. Remove "副本" / "Copy" artifacts
        filename = re.sub(r'(?: - )?(?:副本|Copy)(?:\s*\(\d+\))?', '', filename, flags=re.IGNORECASE)

        return filename

    def extract_metadata(self, filepath: str) -> Dict[str, str]:
        filename = os.path.basename(filepath)
        name_only, extension = os.path.splitext(filename)
        
        # Preprocess to handle adhesion
        clean_name = self.preprocess_filename(name_only)
        
        metadata = {
            "original_name": filename,
            "filepath": filepath,
            "extension": extension,
            "student_id": "NoID",
            "name": "",
            "project": "",
            "class_name": ""
        }
        
        # 1. Anchor: Find Student ID
        id_matches = list(self.id_pattern.finditer(clean_name))
        if id_matches:
            best_match = max(id_matches, key=lambda m: len(m.group()))
            metadata["student_id"] = best_match.group()
            # Remove ID from string for further processing
            clean_name = clean_name.replace(metadata["student_id"], " ")
        
        # 2. Extract Class
        if self.standard_class_name:
            # If manually provided, use it and try to remove it from filename if present
            metadata["class_name"] = self.standard_class_name
            clean_name = re.sub(re.escape(self.standard_class_name), " ", clean_name, flags=re.IGNORECASE)
        else:
            # Regex extraction
            keywords_pattern = "|".join(map(re.escape, self.class_keywords))
            # Match "1班", "Class 1", "一班"
            class_pattern = re.compile(
                r'((?:\d+|' + self.cn_num_pattern + r')\s*(?:' + keywords_pattern + r'))|' + 
                r'((?:' + keywords_pattern + r')\s*(?:\d+|' + self.cn_num_pattern + r'))', 
                re.IGNORECASE
            )
            class_match = class_pattern.search(clean_name)
            if class_match:
                metadata["class_name"] = class_match.group(0)
                clean_name = clean_name.replace(metadata["class_name"], " ")

        # 3. Normalize Separators and Remove Standard Project Name
        # We treat standard separators as "breaks" for name clustering, but spaces as "continuations"
        # Replace hard separators with a special char that won't match the name regex
        clean_name = re.sub(r'[_\-\+——]+', ' | ', clean_name)
        
        # If standard project name is set, remove it now to prevent it being picked as Name
        if self.standard_project_name:
            # Case insensitive removal
            clean_name = re.sub(re.escape(self.standard_project_name), " ", clean_name, flags=re.IGNORECASE)

        # 4. Extract Name
        # Strategy: Look for Chinese name first
        cn_match = self.cn_name_pattern.search(clean_name)
        if cn_match:
            candidate_name = cn_match.group()
            
            # Check if this Chinese name contains any excluded tokens
            # Remove excluded tokens from the candidate name
            cleaned_candidate = candidate_name
            for excluded in self.excluded_tokens:
                if excluded in cleaned_candidate.lower():
                    # Remove the excluded token
                    cleaned_candidate = cleaned_candidate.replace(excluded, '')
                    cleaned_candidate = cleaned_candidate.replace(excluded.upper(), '')
                    cleaned_candidate = cleaned_candidate.replace(excluded.capitalize(), '')
                    print(f"[PARSER] Removed '{excluded}' from '{candidate_name}' -> '{cleaned_candidate}'")
            
            # If after removing excluded tokens, we still have a valid name
            if cleaned_candidate.strip():
                metadata["name"] = cleaned_candidate.strip()
            else:
                # The entire candidate was excluded, try to find another Chinese name
                print(f"[PARSER] Entire candidate '{candidate_name}' was excluded")
                all_cn_matches = self.cn_name_pattern.findall(clean_name)
                for cn_name in all_cn_matches:
                    if cn_name == candidate_name:
                        continue  # Skip the one we already tried
                    
                    cleaned_cn = cn_name
                    for excluded in self.excluded_tokens:
                        if excluded in cleaned_cn.lower():
                            cleaned_cn = cleaned_cn.replace(excluded, '')
                            cleaned_cn = cleaned_cn.replace(excluded.upper(), '')
                            cleaned_cn = cleaned_cn.replace(excluded.capitalize(), '')
                    
                    if cleaned_cn.strip():
                        metadata["name"] = cleaned_cn.strip()
                        break
        
        # If no Chinese name found, try English Name Strategy
        if not metadata["name"]:
            # English Name Strategy: Token Clustering
            # We look for consecutive tokens that look like names (letters)
            tokens = clean_name.split()
            name_candidates = []
            current_candidate = []
            
            for token in tokens:
                # Clean token (keep letters only)
                if re.match(r'^[a-zA-Z]+$', token):
                    # Check if this token is in the excluded list (Common Element)
                    if token.lower() in self.excluded_tokens:
                        # It's a common element (likely project), so treat as separator
                        if current_candidate:
                            name_candidates.append(" ".join(current_candidate))
                            current_candidate = []
                        continue
                        
                    current_candidate.append(token)
                else:
                    # End of a sequence (hit a separator or number)
                    if current_candidate:
                        name_candidates.append(" ".join(current_candidate))
                        current_candidate = []
            
            # Append last candidate if exists
            if current_candidate:
                name_candidates.append(" ".join(current_candidate))
            
            if name_candidates:
                # Heuristic: Prefer multi-word names (First Last)
                multi_word = [nc for nc in name_candidates if ' ' in nc]
                if multi_word:
                    metadata["name"] = multi_word[0]
                else:
                    # Fallback to first single word candidate
                    metadata["name"] = name_candidates[0]

        # Remove Name from string to clean up for Project
        if metadata["name"]:
            # Remove ALL occurrences of the name (case insensitive)
            clean_name = re.sub(re.escape(metadata["name"]), " ", clean_name, flags=re.IGNORECASE)

        # 5. Extract Project
        if self.standard_project_name:
            metadata["project"] = self.standard_project_name
            
            # Check if project contains the extracted name
            # If so, the name extraction was wrong - re-extract from remaining tokens
            if metadata["name"] and metadata["name"].lower() in metadata["project"].lower():
                print(f"[WARNING] Project '{metadata['project']}' contains name '{metadata['name']}' - re-extracting name")
                
                # Re-extract name from the original clean_name before we removed the name
                # Get all English name candidates again, excluding the project name
                temp_clean = metadata["original_name"].replace(metadata["extension"], "")
                temp_clean = self.preprocess_filename(temp_clean)
                
                # Extract English words
                english_words = re.findall(r'[A-Z][a-z]+', temp_clean)
                
                # Filter out words that are in the project name
                project_words_lower = [w.lower() for w in re.findall(r'[a-zA-Z]+', metadata["project"])]
                name_candidates = []
                current_candidate = []
                
                for word in english_words:
                    if word.lower() not in project_words_lower and word.lower() not in self.excluded_tokens:
                        current_candidate.append(word)
                    else:
                        if current_candidate:
                            name_candidates.append(" ".join(current_candidate))
                            current_candidate = []
                
                if current_candidate:
                    name_candidates.append(" ".join(current_candidate))
                
                if name_candidates:
                    # Prefer multi-word names
                    multi_word = [nc for nc in name_candidates if ' ' in nc]
                    if multi_word:
                        metadata["name"] = multi_word[0]
                    else:
                        metadata["name"] = name_candidates[0]
                    print(f"[RE-EXTRACTED] New name: '{metadata['name']}'")
                else:
                    metadata["name"] = ""
                    print(f"[WARNING] Could not re-extract name")
        else:
            # Cleanup remainder
            # Remove the special separator chars we added
            clean_name = clean_name.replace('|', ' ')
            clean_name = re.sub(r'\s+', ' ', clean_name).strip()
            metadata["project"] = clean_name

        return metadata

    def generate_new_name(self, metadata: Dict[str, str], format_str: str = "{student_id}-{name}-{project}") -> str:
        """
        Generates the new filename based on metadata and format string.
        """
        # Clean up components
        sid = metadata.get("student_id", "")
        # If ID is "NoID", treat it as empty
        if sid == "NoID":
            sid = ""
        
        name = metadata.get("name", "")
        proj = metadata.get("project", "")
        cls = metadata.get("class_name", "")
        ext = metadata.get("extension", "")
        
        new_name_base = format_str.format(
            student_id=sid,
            name=name,
            project=proj,
            class_name=cls,
            original_name=metadata.get("original_name", "").replace(ext, "")
        )
        
        # Detect the separator used in format_str
        # Check what separator is actually in the format string
        separator = "-"  # default
        if "_" in format_str and "-" not in format_str:
            separator = "_"
        elif " " in format_str and "-" not in format_str and "_" not in format_str:
            separator = " "
        
        # Clean up double separators if some fields are empty
        # Replace any sequence of separators with a single separator
        # This handles cases like "123--Project" or "___Project"
        if separator == " ":
            # For space separator, clean up multiple spaces
            new_name_base = re.sub(r'\s+', ' ', new_name_base)
        else:
            # For - or _, replace multiple occurrences with single
            pattern = re.escape(separator) + r'{2,}'
            new_name_base = re.sub(pattern, separator, new_name_base)
        
        # Remove leading/trailing separators
        new_name_base = new_name_base.strip(separator + ' ')
        
        return new_name_base + ext
