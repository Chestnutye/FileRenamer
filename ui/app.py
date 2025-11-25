import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QTreeWidget, QTreeWidgetItem, 
                             QFileDialog, QProgressBar, QFrame, QSplitter, QMessageBox, QHeaderView, 
                             QComboBox, QRadioButton, QButtonGroup)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPalette

from core.scanner import scan_directory
from core.parser import MetadataParser
from core.renamer import rename_file

class WorkerThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(int) # success count
    
    def __init__(self, files_data):
        super().__init__()
        self.files_data = files_data
        self.is_running = True

    def run(self):
        success_count = 0
        total = len(self.files_data)
        for i, item in enumerate(self.files_data):
            if not self.is_running:
                break
                
            old_path = item["filepath"]
            new_name = item["new_name"]
            
            if rename_file(old_path, new_name):
                item["status"] = "Done"
                success_count += 1
            else:
                item["status"] = "Error"
            
            self.progress.emit(int((i + 1) / total * 100))
        
        self.finished.emit(success_count)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("文件重命名工具")
        self.resize(1300, 850)
        
        # Data
        self.files_data = []
        self.root_dir = ""
        self.rename_history = [] # Store rename operations for undo
        
        # Setup UI
        self.setup_ui()
        self.apply_modern_theme()

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Sidebar ---
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(320) # Widen sidebar for tiled options
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(20, 30, 20, 20)
        sidebar_layout.setSpacing(20)

        # Title
        title_label = QLabel("重命名设置")
        title_label.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #ffffff;")
        sidebar_layout.addWidget(title_label)

        # ID Length
        id_group = QVBoxLayout()
        id_group.setSpacing(5)
        id_group.addWidget(QLabel("学号长度（自动检测）："))
        self.id_len_input = QLineEdit("8-12")
        self.id_len_input.setToolTip("选择文件夹后自动检测")
        id_group.addWidget(self.id_len_input)
        sidebar_layout.addLayout(id_group)

        # Standard Project Name
        proj_group = QVBoxLayout()
        proj_group.setSpacing(5)
        label_proj = QLabel("标准项目名（必填）：")
        label_proj.setStyleSheet("color: #ff6b6b; font-weight: bold;")
        proj_group.addWidget(label_proj)
        self.proj_name_input = QLineEdit()
        self.proj_name_input.setPlaceholderText("例如：会计作业")
        self.proj_name_input.textChanged.connect(self.check_runnable)
        proj_group.addWidget(self.proj_name_input)
        sidebar_layout.addLayout(proj_group)

        # Ignored Words (Interference)
        ignore_group = QVBoxLayout()
        ignore_group.setSpacing(5)
        ignore_group.addWidget(QLabel("忽略词（空格分隔）："))
        self.ignore_input = QLineEdit()
        self.ignore_input.setPlaceholderText("例如：副本 样本 练习")
        self.ignore_input.setToolTip("在检测项目名和学生姓名时忽略这些词")
        # DO NOT auto-trigger on text change - this causes infinite loops and clears user input!
        ignore_group.addWidget(self.ignore_input)
        
        # Recommended Ignored Words
        rec_words_label = QLabel("推荐：")
        rec_words_label.setStyleSheet("color: #95a5a6; font-size: 11px;")
        ignore_group.addWidget(rec_words_label)
        
        # Container for recommended word buttons
        self.rec_words_layout = QHBoxLayout()
        self.rec_words_layout.setSpacing(5)
        ignore_group.addLayout(self.rec_words_layout)
        
        sidebar_layout.addLayout(ignore_group)

        # Custom Text
        class_group = QVBoxLayout()
        class_group.setSpacing(5)
        class_group.addWidget(QLabel("自定义文本（可选）："))
        self.class_name_input = QLineEdit()
        self.class_name_input.setPlaceholderText("例如：班级名、课程代码等")
        self.class_name_input.textChanged.connect(self.run_preview)
        class_group.addWidget(self.class_name_input)
        
        # Class Position
        class_pos_layout = QHBoxLayout()
        class_pos_label = QLabel("自定义文本位置：")
        class_pos_layout.addWidget(class_pos_label)
        self.class_pos_combo = QComboBox()
        self.class_pos_combo.addItem("不添加", "none")
        self.class_pos_combo.addItem("开头", "start")
        self.class_pos_combo.addItem("学号后", "after_id")
        self.class_pos_combo.addItem("结尾", "end")
        self.class_pos_combo.currentIndexChanged.connect(self.run_preview)
        class_pos_layout.addWidget(self.class_pos_combo)
        class_group.addLayout(class_pos_layout)
        
        sidebar_layout.addLayout(class_group)

        # Separator Selection
        sep_group = QVBoxLayout()
        sep_group.setSpacing(5)
        # Separator
        sep_label = QLabel("分隔符：")
        sep_group.addWidget(sep_label)
        self.sep_combo = QComboBox()
        self.sep_combo.addItem("横杆 (-)", "-")
        self.sep_combo.addItem("下划线 (_)", "_")
        self.sep_combo.addItem("空格", " ")
        self.sep_combo.addItem("无", "")
        self.sep_combo.currentIndexChanged.connect(self.update_pattern_labels) # Update labels then preview
        sep_group.addWidget(self.sep_combo)
        sidebar_layout.addLayout(sep_group)

        # Format Selection (Tiled Radio Buttons)
        fmt_group = QVBoxLayout()
        fmt_group.setSpacing(10)
        fmt_group.addWidget(QLabel("Naming Pattern:"))
        
        self.fmt_group_btn = QButtonGroup(self)
        self.pattern_buttons = [] # Store to update text later
        
        # Templates for display and logic
        # We use a custom placeholder {sep} for display updates
        formats = [
            ("ID {sep} Name {sep} Project", "{student_id}{sep}{name}{sep}{project}"),
            ("Name {sep} ID {sep} Project", "{name}{sep}{student_id}{sep}{project}"),
            ("Project {sep} ID {sep} Name", "{project}{sep}{student_id}{sep}{name}"),
            ("Original {sep} ID", "{original_name}{sep}{student_id}")
        ]
        
        for i, (label_tmpl, fmt) in enumerate(formats):
            rb = QRadioButton(label_tmpl.replace("{sep}", "-")) # Default to dash
            rb.setProperty("label_tmpl", label_tmpl)
            rb.setProperty("fmt", fmt)
            if i == 0: rb.setChecked(True)
            rb.toggled.connect(self.run_preview)
            self.fmt_group_btn.addButton(rb)
            fmt_group.addWidget(rb)
            self.pattern_buttons.append(rb)
            
        sidebar_layout.addLayout(fmt_group)
        
        sidebar_layout.addStretch()
        
        # --- Main Content ---
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(15)

        # Top Bar
        top_bar = QHBoxLayout()
        self.load_btn = QPushButton("选择文件夹")
        self.load_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.load_btn.clicked.connect(self.select_folder)
        self.load_btn.setFixedWidth(140)
        
        self.path_label = QLabel("未选择文件夹")
        self.path_label.setStyleSheet("color: #888888; font-style: italic;")
        
        top_bar.addWidget(self.load_btn)
        top_bar.addWidget(self.path_label)
        top_bar.addStretch()
        content_layout.addLayout(top_bar)

        # Tree Widget (Table)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["原始文件名", "学号（可编辑）", "姓名", "项目名", "新文件名", "状态"])
        
        # Column Widths
        header = self.tree.header()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive) 
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive) # Allow manual resize for full view
        
        self.tree.setColumnWidth(0, 200)
        self.tree.setColumnWidth(1, 120)
        self.tree.setColumnWidth(2, 100)
        self.tree.setColumnWidth(3, 120)
        self.tree.setColumnWidth(4, 300) # Give more space to New Filename
        self.tree.setColumnWidth(5, 60)
        
        self.tree.setAlternatingRowColors(True)
        self.tree.itemChanged.connect(self.on_item_changed) # Handle edits
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked) # Handle double-click
        content_layout.addWidget(self.tree)

        # Bottom Bar
        bottom_bar = QHBoxLayout()
        
        self.preview_btn = QPushButton("刷新预览")
        self.preview_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.preview_btn.clicked.connect(self.run_preview)
        self.preview_btn.setEnabled(False)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        
        self.rename_btn = QPushButton("执行重命名")
        self.rename_btn.setObjectName("RenameBtn")
        self.rename_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rename_btn.clicked.connect(self.run_rename)
        self.rename_btn.setEnabled(False)
        
        self.undo_btn = QPushButton("撤回重命名")
        self.undo_btn.setObjectName("UndoBtn")
        self.undo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.undo_btn.clicked.connect(self.run_undo)
        self.undo_btn.setEnabled(False)
        self.undo_btn.setStyleSheet("""
            QPushButton#UndoBtn {
                background-color: #e67e22;
                color: white;
                font-weight: bold;
            }
            QPushButton#UndoBtn:hover {
                background-color: #d35400;
            }
            QPushButton#UndoBtn:disabled {
                background-color: #95a5a6;
                color: #7f8c8d;
            }
        """)
        
        bottom_bar.addWidget(self.preview_btn)
        bottom_bar.addWidget(self.progress_bar)
        bottom_bar.addWidget(self.rename_btn)
        bottom_bar.addWidget(self.undo_btn)
        content_layout.addLayout(bottom_bar)

        # Add to main layout
        main_layout.addWidget(sidebar)
        main_layout.addWidget(content)

    def apply_modern_theme(self):
        # Dark Theme Palette
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.ColorRole.Window, QColor(40, 44, 52))
        dark_palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Base, QColor(33, 37, 43))
        dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(40, 44, 52))
        dark_palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        dark_palette.setColor(QPalette.ColorRole.Link, QColor(97, 175, 239))
        dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(97, 175, 239))
        dark_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
        QApplication.setPalette(dark_palette)

        # Stylesheet
        self.setStyleSheet("""
            QMainWindow {
                background-color: #282c34;
            }
            QFrame#Sidebar {
                background-color: #21252b;
                border-right: 1px solid #181a1f;
            }
            QLabel {
                color: #abb2bf;
                font-size: 14px;
            }
            QLineEdit {
                background-color: #3b4048;
                border: 1px solid #181a1f;
                border-radius: 4px;
                color: #dcdfe4;
                padding: 8px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #61afef;
            }
            QComboBox {
                background-color: #3b4048;
                border: 1px solid #181a1f;
                border-radius: 4px;
                color: #dcdfe4;
                padding: 8px;
                font-size: 13px;
            }
            QComboBox::drop-down {
                border:none;
            }
            QRadioButton {
                color: #abb2bf;
                spacing: 8px;
                font-size: 13px;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                border-radius: 8px;
                border: 2px solid #5c6370;
            }
            QRadioButton::indicator:checked {
                background-color: #61afef;
                border: 2px solid #61afef;
            }
            QPushButton {
                background-color: #61afef;
                color: #282c34;
                border: none;
                border-radius: 4px;
                padding: 10px 20px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #528bff;
            }
            QPushButton:disabled {
                background-color: #3b4048;
                color: #5c6370;
            }
            QPushButton#RenameBtn {
                background-color: #98c379;
                color: #282c34;
            }
            QPushButton#RenameBtn:hover {
                background-color: #7db35b;
            }
            QPushButton#RenameBtn:disabled {
                background-color: #3b4048;
                color: #5c6370;
            }
            QTreeWidget {
                background-color: #21252b;
                border: 1px solid #181a1f;
                border-radius: 4px;
                color: #dcdfe4;
                font-size: 13px;
            }
            QHeaderView::section {
                background-color: #282c34;
                color: #abb2bf;
                padding: 8px;
                border: none;
                border-right: 1px solid #181a1f;
                font-weight: bold;
            }
            QProgressBar {
                border: 1px solid #181a1f;
                border-radius: 4px;
                text-align: center;
                background-color: #21252b;
            }
            QProgressBar::chunk {
                background-color: #61afef;
                border-radius: 3px;
            }
        """)

    def check_runnable(self):
        has_proj = bool(self.proj_name_input.text().strip())
        self.preview_btn.setEnabled(has_proj)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            self.root_dir = folder
            self.path_label.setText(folder)
            self.detect_id_length()
            self.detect_common_tokens()
            # If we auto-filled project name, trigger preview
            if self.proj_name_input.text().strip():
                self.run_preview()

    def detect_id_length(self):
        import re
        from collections import Counter
        files = list(scan_directory(self.root_dir))
        lengths = []
        for fpath in files[:50]:
            name = os.path.basename(fpath)
            matches = re.findall(r'\d+', name)
            for m in matches:
                l = len(m)
                if 4 <= l <= 15: lengths.append(l)
        if lengths:
            common = Counter(lengths).most_common(1)[0][0]
            self.id_len_input.setText(f"{common}")
        else:
            self.id_len_input.setText("8-12")

    def detect_common_tokens(self):
        """
        扫描文件名，自动填充 Project Name 和生成推荐忽略词
        
        逻辑：
        1. 从原始文件名（去除扩展名）中提取所有词组
        2. 排除用户手动输入的 Ignored Words
        3. 统计词频
        4. 最常见的词 -> 自动填充到 Standard Project Name
        5. 第2-15名的中文词（≤5字） -> 生成4个推荐按钮
        """
        import re
        from collections import Counter
        
        if not self.root_dir:
            return
        
        files = list(scan_directory(self.root_dir))
        if not files:
            return
        
        print(f"[INFO] Scanning {len(files)} files...")
        
        # ============ 步骤1: 获取用户手动输入的 Ignored Words ============
        ignored_text = self.ignore_input.text().strip()
        ignored_text = ignored_text.replace(',', ' ')  # 支持逗号分隔
        ignored_words = [w.strip() for w in ignored_text.split() if w.strip()]
        
        # 分类：中文词（精确匹配）和英文词（不区分大小写）
        ignored_chinese = [w for w in ignored_words if re.match(r'[\u4e00-\u9fa5]+', w)]
        ignored_english = [w.lower() for w in ignored_words if re.match(r'[a-zA-Z]+', w)]
        
        print(f"[IGNORED] Chinese: {ignored_chinese}, English: {ignored_english}")
        
        # ============ 步骤2: 从所有文件名中提取词组 ============
        token_counts = Counter()
        token_original_case = {}  # 保存原始大小写
        
        for fpath in files:
            filename = os.path.basename(fpath)
            name_no_ext, _ = os.path.splitext(filename)  # 去除扩展名
            
            # 提取词组：中文词组 或 英文单词
            tokens = re.findall(r'[\u4e00-\u9fa5]+|[a-zA-Z]+', name_no_ext)
            
            for token in tokens:
                # 过滤长度
                if re.match(r'[\u4e00-\u9fa5]+', token):
                    # 中文：≥2字符
                    if len(token) < 2:
                        continue
                else:
                    # 英文：>2字符
                    if len(token) <= 2:
                        continue
                
                # ============ 步骤3: 检查是否在 Ignored Words 中 ============
                is_ignored = False
                
                if re.match(r'[\u4e00-\u9fa5]+', token):
                    # 中文：精确匹配
                    if token in ignored_chinese:
                        is_ignored = True
                else:
                    # 英文：不区分大小写
                    if token.lower() in ignored_english:
                        is_ignored = True
                
                if is_ignored:
                    continue
                
                # ============ 步骤4: 统计词频 ============
                token_lower = token.lower()
                token_counts[token_lower] += 1
                
                # 保存原始大小写（第一次出现的）
                if token_lower not in token_original_case:
                    token_original_case[token_lower] = token
        
        if not token_counts:
            print("[WARNING] No tokens found after filtering!")
            self.update_recommended_words([])
            return
        
        # ============ 步骤5: 自动填充 Standard Project Name ============
        most_common_lower, count = token_counts.most_common(1)[0]
        most_common = token_original_case[most_common_lower]
        
        self.proj_name_input.setText(most_common)
        print(f"[AUTO-FILL] Project Name: '{most_common}' ({count}/{len(files)} files)")
        
        # ============ 步骤6: 生成推荐忽略词（4个中文词，≤5字） ============
        top_tokens = token_counts.most_common(20)  # 取前20名
        recommended = []
        
        for token_lower, count in top_tokens[1:]:  # 跳过第1名（已用作项目名）
            token = token_original_case[token_lower]
            
            # 只要中文词
            if not re.match(r'[\u4e00-\u9fa5]+', token):
                continue
            
            # 长度限制：≤5字
            if len(token) > 5:
                continue
            
            recommended.append(token)
            
            if len(recommended) >= 4:
                break
        
        print(f"[RECOMMENDED] Ignored Words: {recommended}")
        self.update_recommended_words(recommended)
        
        # ============ 步骤7: 保存 common_tokens 供 parser 使用 ============
        # 出现在 >80% 文件中的词，传给 parser 作为 excluded_tokens
        total_files = len(files)
        self.common_tokens = []
        for token_lower, count in token_counts.items():
            if count > total_files * 0.8:
                self.common_tokens.append(token_lower)
        
        print(f"[COMMON] Tokens (>80%): {self.common_tokens}")
        
        # Don't auto-trigger preview here - let the caller decide
        # This prevents infinite loops and preserves user's ignored words input
    
    def update_recommended_words(self, words):
        """Update the recommended ignored words buttons"""
        # Clear existing buttons
        while self.rec_words_layout.count():
            item = self.rec_words_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Add new buttons
        for word in words:
            btn = QPushButton(word)
            btn.setFixedHeight(24)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #3b4048;
                    color: #abb2bf;
                    border: 1px solid #5c6370;
                    border-radius: 3px;
                    padding: 2px 8px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #4b5058;
                    border: 1px solid #61afef;
                }
            """)
            btn.clicked.connect(lambda checked, w=word: self.add_ignored_word(w))
            self.rec_words_layout.addWidget(btn)
        
        # Add stretch to push buttons to the left
        self.rec_words_layout.addStretch()
    
    def add_ignored_word(self, word):
        """Add a word to the ignored words input"""
        current = self.ignore_input.text().strip()
        if current:
            # Check if word already exists (case insensitive)
            existing = current.replace(',', ' ').split()
            existing_lower = [w.lower() for w in existing]
            if word.lower() not in existing_lower:
                self.ignore_input.setText(current + ' ' + word)
                print(f"[ADDED] Ignored word: '{word}'")
                # Trigger preview to apply the new ignored word
                if self.proj_name_input.text().strip():
                    self.run_preview()
        else:
            self.ignore_input.setText(word)
            print(f"[ADDED] Ignored word: '{word}'")
            # Trigger preview to apply the new ignored word
            if self.proj_name_input.text().strip():
                self.run_preview()

    def update_pattern_labels(self):
        sep_char = self.sep_combo.currentData()
        # Visual separator for labels (use space for None to make it readable, or just empty)
        visual_sep = sep_char if sep_char else " " 
        if sep_char == " ": visual_sep = " "
        
        for btn in self.pattern_buttons:
            tmpl = btn.property("label_tmpl")
            if tmpl:
                btn.setText(tmpl.replace("{sep}", visual_sep))
        
        self.run_preview()

    def run_preview(self):
        if not self.root_dir: return
        
        # Check if user has manually entered ignored words
        # If so, re-scan to update Project Name with those words excluded
        ignored_text = self.ignore_input.text().strip()
        if ignored_text:
            print(f"[PREVIEW] User has ignored words, re-scanning to update Project Name...")
            self.detect_common_tokens()
        
        proj_name = self.proj_name_input.text().strip()
        if not proj_name: return # Don't warn on every toggle, just return
            
        self.tree.blockSignals(True) # Prevent itemChanged triggering during populate
        self.tree.clear()
        
        # Get settings
        id_range = self.id_len_input.text().split('-')
        try:
            min_len = int(id_range[0])
            max_len = int(id_range[1]) if len(id_range) > 1 else min_len
        except:
            min_len, max_len = 8, 12
            
        class_name = self.class_name_input.text().strip()
        class_pos = self.class_pos_combo.currentData()
        
        # Construct format string
        sep = self.sep_combo.currentData()
        base_fmt = self.fmt_group_btn.checkedButton().property("fmt")
        
        # Inject Class Name based on position
        if class_pos != "none":
            if class_pos == "start":
                base_fmt = "{class_name}{sep}" + base_fmt
            elif class_pos == "end":
                base_fmt = base_fmt + "{sep}{class_name}"
            elif class_pos == "after_id":
                # Replace {student_id} with {student_id}{sep}{class_name}
                base_fmt = base_fmt.replace("{student_id}", "{student_id}{sep}{class_name}")
        
        fmt_str = base_fmt.replace("{sep}", sep)
        
        # Get user's manually entered Ignored Words
        import re
        ignored_text = self.ignore_input.text().strip()
        ignored_text = ignored_text.replace(',', ' ')
        ignored_words = [w.strip().lower() for w in ignored_text.split() if w.strip()]
        
        print(f"[PREVIEW] User ignored words: {ignored_words}")
        
        # Combine with common tokens (>80% frequency)
        common_tokens = getattr(self, 'common_tokens', [])
        all_excluded = list(set(ignored_words + common_tokens))
        
        print(f"[PREVIEW] All excluded tokens: {all_excluded}")
        
        parser = MetadataParser(
            id_min_len=min_len, 
            id_max_len=max_len, 
            standard_project_name=proj_name,
            standard_class_name=class_name,
            excluded_tokens=all_excluded
        )
        
        self.files_data = []
        files = list(scan_directory(self.root_dir))
        
        for fpath in files:
            meta = parser.extract_metadata(fpath)
            new_name = parser.generate_new_name(meta, fmt_str)
            
            # Calculate new path
            dir_path = os.path.dirname(fpath)
            new_path = os.path.join(dir_path, new_name)
            
            item_data = {
                "filepath": fpath,
                "old_path": fpath,  # For undo functionality
                "new_path": new_path,  # For undo functionality
                "meta": meta,
                "new_name": new_name,
                "status": "Ready",
                "fmt_str": fmt_str # Store for re-generation
            }
            self.files_data.append(item_data)
            
            item = QTreeWidgetItem([
                meta["original_name"],
                meta["student_id"],
                meta["name"],
                meta["project"],
                new_name,
                "Ready"
            ])
            # Make ID editable
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            # Add tooltip for full filename visibility
            item.setToolTip(4, new_name)
            self.tree.addTopLevelItem(item)
            
        self.tree.blockSignals(False)
        self.rename_btn.setEnabled(True)

    def on_item_changed(self, item, column):
        # If user edits ID (col 1), regenerate new name
        if column == 1:
            index = self.tree.indexOfTopLevelItem(item)
            if index >= 0 and index < len(self.files_data):
                new_id = item.text(1)
                item_data = self.files_data[index]
                item_data["meta"]["student_id"] = new_id
                
                # Regenerate name
                parser = MetadataParser() # Helper just for generation
                new_name = parser.generate_new_name(item_data["meta"], item_data["fmt_str"])
                
                item_data["new_name"] = new_name
                item.setText(4, new_name) # Update New Filename column
    
    def on_item_double_clicked(self, item, column):
        """Handle double-click on tree items - add Name to Ignored Words if column 2"""
        if column == 2:  # Name column
            name = item.text(2).strip()
            if name and name != "NoID":
                # Add to ignored words
                current = self.ignore_input.text().strip()
                if current:
                    # Check if already exists
                    existing = current.replace(',', ' ').split()
                    existing_lower = [w.lower() for w in existing]
                    if name.lower() not in existing_lower:
                        self.ignore_input.setText(current + ' ' + name)
                        print(f"[DOUBLE-CLICK] Added '{name}' to Ignored Words")
                        # Trigger preview to apply
                        if self.proj_name_input.text().strip():
                            self.run_preview()
                else:
                    self.ignore_input.setText(name)
                    print(f"[DOUBLE-CLICK] Added '{name}' to Ignored Words")
                    # Trigger preview to apply
                    if self.proj_name_input.text().strip():
                        self.run_preview()

    def run_rename(self):
        if not self.files_data: return
        self.rename_btn.setEnabled(False)
        
        # Save current rename operation to history
        current_operation = []
        for item_data in self.files_data:
            current_operation.append({
                'old_path': item_data['old_path'],
                'new_path': item_data['new_path']
            })
        
        self.worker = WorkerThread(self.files_data)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.finished.connect(lambda success_count: self.on_rename_finished(success_count, current_operation))
        self.worker.start()

    def on_rename_finished(self, success_count, operation_history):
        self.rename_btn.setEnabled(True)
        self.progress_bar.setValue(100)
        
        # Save to rename history for undo
        if success_count > 0:
            self.rename_history.append(operation_history)
            self.undo_btn.setEnabled(True)
            print(f"[RENAME] Saved {len(operation_history)} operations to history")
        
        self.tree.blockSignals(True)
        self.tree.clear()
        for item_data in self.files_data:
            meta = item_data["meta"]
            item = QTreeWidgetItem([
                meta["original_name"],
                meta["student_id"],
                meta["name"],
                meta["project"],
                item_data["new_name"],
                item_data["status"]
            ])
            self.tree.addTopLevelItem(item)
        self.tree.blockSignals(False)
        QMessageBox.information(self, "完成", f"已重命名 {success_count}/{len(self.files_data)} 个文件。")
    
    def run_undo(self):
        """Undo the last rename operation"""
        if not self.rename_history:
            QMessageBox.warning(self, "无历史记录", "没有可以撤回的重命名操作。")
            return
        
        # Get the last operation
        last_operation = self.rename_history.pop()
        
        # Ask for confirmation
        reply = QMessageBox.question(
            self,
            "确认撤回",
            f"是否撤回上一次的重命名操作（{len(last_operation)} 个文件）？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            # Put it back if user cancels
            self.rename_history.append(last_operation)
            return
        
        # Perform undo
        success_count = 0
        failed_files = []
        
        for op in last_operation:
            try:
                if os.path.exists(op['new_path']):
                    os.rename(op['new_path'], op['old_path'])
                    success_count += 1
                    print(f"[UNDO] Restored: {os.path.basename(op['new_path'])} -> {os.path.basename(op['old_path'])}")
                else:
                    failed_files.append(os.path.basename(op['new_path']))
            except Exception as e:
                failed_files.append(f"{os.path.basename(op['new_path'])}: {str(e)}")
        
        # Update undo button state
        if not self.rename_history:
            self.undo_btn.setEnabled(False)
        
        # Show result
        if failed_files:
            QMessageBox.warning(
                self,
                "撤回完成（有错误）",
                f"已恢复 {success_count}/{len(last_operation)} 个文件。\n\n失败的文件：\n" + "\n".join(failed_files[:5])
            )
        else:
            QMessageBox.information(
                self,
                "撤回完成",
                f"成功恢复了 {success_count} 个文件到原始文件名。"
            )
        
        # Refresh the view
        if self.root_dir:
            self.run_preview()

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
