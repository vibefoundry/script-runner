#!/usr/bin/env python3
"""
VibeFoundry Script Runner
A GUI helper for running scripts and managing metadata.
Styled to match VibeFoundry Assistant (light theme)
"""

import os
import sys
import subprocess
import threading
import time
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font
from datetime import datetime
from pathlib import Path

# Check for pandas
try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


class ScriptRunner:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Script Runner")

        # Get screen dimensions
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        # Position: 1/4 of screen on the left
        window_width = screen_width // 4
        window_height = screen_height - 50

        self.root.geometry(f"{window_width}x{window_height}+0+0")
        self.root.resizable(True, True)
        self.root.configure(bg='#ffffff')

        # Store paths
        self.project_folder = None
        self.scripts_folder = None
        self.input_folder = None
        self.output_folder = None
        self.app_folder = None
        self.meta_folder = None

        # Script tracking
        self.script_vars = {}
        self.script_mtimes = {}

        # Auto-run state
        self.auto_run_var = tk.BooleanVar(value=False)

        # File watching state
        self.watching = False
        self.last_input_scan = {}
        self.last_output_scan = {}
        self.last_refresh_time = 0  # Debounce refreshes

        # Configure ttk styles
        self._configure_styles()

        # Build UI
        self._build_ui()

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_styles(self):
        """Configure ttk styles to match VibeFoundry Assistant"""
        style = ttk.Style()
        style.theme_use('clam')

        # Colors matching VibeFoundry Assistant CSS
        bg = '#ffffff'
        bg_alt = '#f0f7ff'
        border = '#b8d4f0'
        accent = '#4a9eda'
        text = '#1a1a1a'
        text_muted = '#4a5568'

        # Frame styles
        style.configure('TFrame', background=bg)
        style.configure('Alt.TFrame', background=bg_alt)

        # Label styles
        style.configure('TLabel', background=bg, foreground=text, font=('Inter', 13))
        style.configure('Title.TLabel', background=bg, foreground=text, font=('Inter', 18, 'bold'))
        style.configure('Header.TLabel', background=bg_alt, foreground=text, font=('Inter', 13, 'bold'))
        style.configure('Muted.TLabel', background=bg, foreground=text_muted, font=('Inter', 11))
        style.configure('Script.TLabel', background=bg, foreground=text, font=('Inter', 14))

        # Button styles
        style.configure('TButton',
            background='#e8e8e8',
            foreground=text,
            font=('Inter', 12, 'bold'),
            padding=(12, 8),
            borderwidth=1,
            relief='flat'
        )
        style.map('TButton',
            background=[('active', '#d8d8d8'), ('pressed', '#c8c8c8')],
            relief=[('pressed', 'flat')]
        )

        style.configure('Accent.TButton',
            background=accent,
            foreground='white',
            font=('Inter', 12, 'bold'),
            padding=(12, 8)
        )
        style.map('Accent.TButton',
            background=[('active', '#3a8eca'), ('pressed', '#2a7eba')]
        )

        # Checkbutton style
        style.configure('TCheckbutton',
            background=bg,
            foreground=text,
            font=('Inter', 14)
        )
        style.map('TCheckbutton',
            background=[('active', bg)]
        )

        # Scrollbar
        style.configure('TScrollbar', background=bg_alt, troughcolor=bg)

    def _build_ui(self):
        """Build the user interface"""
        # Top bar (like VibeFoundry's top-bar)
        top_bar = ttk.Frame(self.root, style='Alt.TFrame')
        top_bar.pack(fill=tk.X)

        # Top bar inner padding
        top_inner = ttk.Frame(top_bar, style='Alt.TFrame')
        top_inner.pack(fill=tk.X, padx=16, pady=10)

        # Title
        title = ttk.Label(top_inner, text="Script Runner", style='Header.TLabel')
        title.pack(side=tk.LEFT)

        # Folder name (right side)
        self.folder_label = ttk.Label(top_inner, text="No folder selected", style='Muted.TLabel')
        self.folder_label.pack(side=tk.RIGHT)

        # Separator
        sep = tk.Frame(self.root, height=1, bg='#b8d4f0')
        sep.pack(fill=tk.X)

        # Button bar
        btn_bar = ttk.Frame(self.root)
        btn_bar.pack(fill=tk.X, padx=16, pady=12)

        # Buttons
        ttk.Button(btn_bar, text="Select Folder", style='Accent.TButton',
                   command=self._select_folder).pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(btn_bar, text="▶ Run", command=self._run_selected_script).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_bar, text="↻ Refresh", command=self._refresh_scripts).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_bar, text="📋 Metadata", command=self._generate_metadata).pack(side=tk.LEFT)

        # Auto-run checkbox
        auto_frame = ttk.Frame(self.root)
        auto_frame.pack(fill=tk.X, padx=16, pady=(0, 8))

        self.auto_run_check = ttk.Checkbutton(
            auto_frame, text="Auto Run on script changes",
            variable=self.auto_run_var, style='TCheckbutton'
        )
        self.auto_run_check.pack(side=tk.LEFT)

        # Separator
        sep2 = tk.Frame(self.root, height=1, bg='#b8d4f0')
        sep2.pack(fill=tk.X)

        # Scripts section
        scripts_header = ttk.Frame(self.root, style='Alt.TFrame')
        scripts_header.pack(fill=tk.X)

        scripts_inner = ttk.Frame(scripts_header, style='Alt.TFrame')
        scripts_inner.pack(fill=tk.X, padx=16, pady=8)

        ttk.Label(scripts_inner, text="Scripts", style='Header.TLabel').pack(side=tk.LEFT)
        self.script_count_label = ttk.Label(scripts_inner, text="", style='Muted.TLabel')
        self.script_count_label.pack(side=tk.RIGHT)

        # Separator
        sep3 = tk.Frame(self.root, height=1, bg='#b8d4f0')
        sep3.pack(fill=tk.X)

        # Scripts list (simple scrollable frame)
        scripts_container = ttk.Frame(self.root)
        scripts_container.pack(fill=tk.BOTH, expand=True)

        # Use a simple listbox-style approach
        self.scripts_frame = ttk.Frame(scripts_container)
        self.scripts_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=8)

        # Separator
        sep4 = tk.Frame(self.root, height=1, bg='#b8d4f0')
        sep4.pack(fill=tk.X)

        # Output section header
        output_header = ttk.Frame(self.root, style='Alt.TFrame')
        output_header.pack(fill=tk.X)

        output_inner = ttk.Frame(output_header, style='Alt.TFrame')
        output_inner.pack(fill=tk.X, padx=16, pady=8)

        ttk.Label(output_inner, text="Output", style='Header.TLabel').pack(side=tk.LEFT)

        # Separator
        sep5 = tk.Frame(self.root, height=1, bg='#b8d4f0')
        sep5.pack(fill=tk.X)

        # Output text area
        output_frame = ttk.Frame(self.root)
        output_frame.pack(fill=tk.BOTH, expand=True)

        self.output_text = tk.Text(
            output_frame, height=8, font=('Monaco', 11),
            bg='#f8fafc', fg='#1a1a1a',
            relief=tk.FLAT, padx=16, pady=12,
            wrap=tk.WORD, borderwidth=0
        )
        output_scroll = ttk.Scrollbar(output_frame, orient="vertical", command=self.output_text.yview)
        self.output_text.configure(yscrollcommand=output_scroll.set)

        self.output_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        output_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Status bar
        status_bar = ttk.Frame(self.root, style='Alt.TFrame')
        status_bar.pack(fill=tk.X)

        status_inner = ttk.Frame(status_bar, style='Alt.TFrame')
        status_inner.pack(fill=tk.X, padx=16, pady=8)

        self.status_label = ttk.Label(status_inner, text="Select a project folder to begin", style='Muted.TLabel')
        self.status_label.pack(side=tk.LEFT)

    def _log(self, message):
        """Add message to output area"""
        self.output_text.insert(tk.END, f"{message}\n")
        self.output_text.see(tk.END)

    def _set_status(self, message):
        """Update status bar"""
        self.status_label.config(text=message)

    def _select_folder(self):
        """Open folder picker dialog"""
        folder = filedialog.askdirectory(title="Select Project Folder")
        if folder:
            self.project_folder = Path(folder)
            self._setup_folder_structure()

    def _setup_folder_structure(self):
        """Set up expected folder paths and create if needed"""
        self.input_folder = self.project_folder / "input_folder"
        self.output_folder = self.project_folder / "output_folder"
        self.app_folder = self.project_folder / "app_folder"
        self.scripts_folder = self.app_folder / "scripts"
        self.meta_folder = self.app_folder / "meta_data"

        # Create folders if they don't exist
        for folder in [self.input_folder, self.output_folder, self.scripts_folder, self.meta_folder]:
            folder.mkdir(parents=True, exist_ok=True)

        # Update UI
        self.folder_label.config(text=self.project_folder.name)

        self._log(f"📁 Opened: {self.project_folder.name}")
        self._refresh_scripts()

        # Generate initial metadata
        self._generate_metadata()

        # Start file watching
        self._start_watching()

        # Launch VibeFoundry Assistant
        self._launch_vibefoundry()

        self._set_status("Ready • Watching for changes")

    def _refresh_scripts(self):
        """Scan scripts folder and update display"""
        # Clear existing
        for widget in self.scripts_frame.winfo_children():
            widget.destroy()
        self.script_vars.clear()

        if not self.scripts_folder or not self.scripts_folder.exists():
            return

        scripts = sorted(self.scripts_folder.glob("**/*.py"))

        for script in scripts:
            rel_path = script.relative_to(self.scripts_folder)
            script_key = str(script)

            # Create variable for this script
            var = tk.BooleanVar(value=False)
            self.script_vars[script_key] = var

            # Track modification time
            self.script_mtimes[script_key] = script.stat().st_mtime

            # Create checkbutton directly in scripts_frame
            cb = ttk.Checkbutton(
                self.scripts_frame,
                text=f"  {rel_path}",
                variable=var,
                style='TCheckbutton'
            )
            cb.pack(fill=tk.X, padx=16, pady=6, anchor='w')

        count = len(scripts)
        self.script_count_label.config(text=f"{count} script{'s' if count != 1 else ''}")

        if not scripts:
            no_scripts = ttk.Label(self.scripts_frame, text="No scripts in app_folder/scripts/", style='Muted.TLabel')
            no_scripts.pack(pady=20)

    def _run_selected_script(self):
        """Run all selected scripts"""
        selected = [path for path, var in self.script_vars.items() if var.get()]

        if not selected:
            messagebox.showinfo("No Selection", "Please select at least one script to run")
            return

        for script_path in selected:
            self._run_script(script_path)

    def _run_script(self, script_path):
        """Run a single script"""
        script = Path(script_path)

        if not script.exists():
            self._log(f"❌ Script not found: {script}")
            return

        self._log(f"\n{'─'*40}")
        self._log(f"▶ Running: {script.name}")
        self._log('─'*40)

        self._set_status(f"Running {script.name}...")

        def run():
            try:
                result = subprocess.run(
                    [sys.executable, str(script)],
                    cwd=str(self.project_folder),
                    capture_output=True,
                    text=True,
                    timeout=300
                )

                if result.stdout:
                    self.root.after(0, lambda: self._log(result.stdout.strip()))
                if result.stderr:
                    self.root.after(0, lambda: self._log(f"⚠️ {result.stderr.strip()}"))

                status = "✓ Completed" if result.returncode == 0 else f"✗ Failed (code {result.returncode})"
                self.root.after(0, lambda: self._log(f"\n{status}"))
                self.root.after(0, lambda: self._set_status(status))

                # Regenerate metadata after script runs
                self.root.after(100, self._generate_metadata)

            except subprocess.TimeoutExpired:
                self.root.after(0, lambda: self._log("⏱ Script timed out (5 min limit)"))
                self.root.after(0, lambda: self._set_status("Timed out"))
            except Exception as e:
                self.root.after(0, lambda: self._log(f"❌ Error: {e}"))
                self.root.after(0, lambda: self._set_status("Error"))

        threading.Thread(target=run, daemon=True).start()

    def _generate_metadata(self):
        """Generate metadata files for input and output folders"""
        if not HAS_PANDAS:
            self._log("⚠️ pandas not installed - metadata skipped")
            return

        if not self.project_folder:
            return

        def generate():
            try:
                # Generate input metadata
                input_meta = self._scan_folder_metadata(self.input_folder, "Input Folder")
                input_path = self.meta_folder / "input_metadata.txt"
                input_path.write_text(input_meta)

                # Generate output metadata
                output_meta = self._scan_folder_metadata(self.output_folder, "Output Folder")
                output_path = self.meta_folder / "output_metadata.txt"
                output_path.write_text(output_meta)

                self.root.after(0, lambda: self._log("✓ Metadata updated"))
                self.root.after(0, lambda: self._set_status("Metadata updated"))

            except Exception as e:
                self.root.after(0, lambda: self._log(f"❌ Metadata error: {e}"))

        threading.Thread(target=generate, daemon=True).start()

    def _scan_folder_metadata(self, folder, title):
        """Scan a folder and generate metadata text"""
        lines = [
            f"{title} Metadata",
            f"Folder: {folder}",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 50,
            ""
        ]

        data_extensions = ['.csv', '.xlsx', '.xls', '.parquet']
        data_files = []
        for ext in data_extensions:
            data_files.extend(folder.glob(f"**/*{ext}"))

        if not data_files:
            lines.append("No data files found.")
            return "\n".join(lines)

        for filepath in sorted(data_files):
            try:
                size_mb = filepath.stat().st_size / (1024 * 1024)

                if filepath.suffix == '.csv':
                    df = pd.read_csv(filepath, nrows=0)
                    df_full = pd.read_csv(filepath)
                    row_count = len(df_full)
                elif filepath.suffix in ['.xlsx', '.xls']:
                    df = pd.read_excel(filepath, nrows=0)
                    df_full = pd.read_excel(filepath)
                    row_count = len(df_full)
                elif filepath.suffix == '.parquet':
                    df = pd.read_parquet(filepath)
                    row_count = len(df)
                else:
                    continue

                rel_path = filepath.relative_to(folder)
                lines.append(f"File: {rel_path}")
                lines.append(f"  Absolute Path: {filepath}")
                lines.append(f"  Size: {size_mb:.2f} MB")
                lines.append(f"  Rows: {row_count}")
                lines.append(f"  Columns ({len(df.columns)}):")

                for col in df.columns:
                    dtype = str(df[col].dtype) if col in df.columns else "unknown"
                    lines.append(f"    - {col} ({dtype})")

                lines.append("")

            except Exception as e:
                lines.append(f"File: {filepath.name}")
                lines.append(f"  Error reading: {e}")
                lines.append("")

        return "\n".join(lines)

    def _start_watching(self):
        """Start watching for file changes"""
        if self.watching:
            return
        self.watching = True

        self._scan_data_folders()

        def watch_loop():
            while self.watching:
                try:
                    self._check_for_changes()
                except Exception as e:
                    print(f"Watch error: {e}")
                time.sleep(1)

        threading.Thread(target=watch_loop, daemon=True).start()

    def _scan_data_folders(self):
        """Scan input/output folders and record file times"""
        if self.input_folder and self.input_folder.exists():
            for f in self.input_folder.glob("**/*"):
                if f.is_file():
                    self.last_input_scan[str(f)] = f.stat().st_mtime

        if self.output_folder and self.output_folder.exists():
            for f in self.output_folder.glob("**/*"):
                if f.is_file():
                    self.last_output_scan[str(f)] = f.stat().st_mtime

    def _check_for_changes(self):
        """Check for new/modified files"""
        data_changed = False
        scripts_changed = []

        # Check input folder
        if self.input_folder and self.input_folder.exists():
            for f in self.input_folder.glob("**/*"):
                if f.is_file():
                    mtime = f.stat().st_mtime
                    key = str(f)
                    if key not in self.last_input_scan or self.last_input_scan[key] != mtime:
                        self.last_input_scan[key] = mtime
                        data_changed = True

        # Check output folder
        if self.output_folder and self.output_folder.exists():
            for f in self.output_folder.glob("**/*"):
                if f.is_file():
                    mtime = f.stat().st_mtime
                    key = str(f)
                    if key not in self.last_output_scan or self.last_output_scan[key] != mtime:
                        self.last_output_scan[key] = mtime
                        data_changed = True

        # Check scripts folder for auto-run (only when auto-run is enabled)
        if self.auto_run_var.get() and self.scripts_folder and self.scripts_folder.exists():
            for f in self.scripts_folder.glob("**/*.py"):
                mtime = f.stat().st_mtime
                key = str(f)
                if key in self.script_mtimes:
                    if self.script_mtimes[key] != mtime:
                        self.script_mtimes[key] = mtime
                        scripts_changed.append(key)
                else:
                    # New script found - add to tracking but only refresh once
                    self.script_mtimes[key] = mtime
                    current_time = time.time()
                    if current_time - self.last_refresh_time > 2:  # Debounce 2 seconds
                        self.last_refresh_time = current_time
                        self.root.after(0, self._refresh_scripts)

        # Regenerate metadata if data files changed
        if data_changed:
            self.root.after(0, lambda: self._log("📁 Data changed → updating metadata"))
            self.root.after(0, self._generate_metadata)

        # Auto-run modified scripts
        for script_path in scripts_changed:
            script_name = Path(script_path).name
            self.root.after(0, lambda n=script_name: self._log(f"📝 {n} modified → running"))
            self.root.after(0, lambda p=script_path: self._run_script(p))

    def _launch_vibefoundry(self):
        """Open VibeFoundry Assistant in app mode (no URL bar)"""
        self._log("🚀 Opening VibeFoundry Assistant...")
        url = "https://vibefoundry.ai/file-preview/"

        # Try to open in app mode (no URL bar)
        if sys.platform == "darwin":  # macOS
            chrome_paths = [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            ]
            for chrome in chrome_paths:
                if os.path.exists(chrome):
                    subprocess.Popen([chrome, f"--app={url}"])
                    self._log("✓ Opened in app mode")
                    return
        elif sys.platform == "win32":  # Windows
            import shutil
            chrome = shutil.which("chrome") or shutil.which("google-chrome")
            edge = shutil.which("msedge")
            if chrome:
                subprocess.Popen([chrome, f"--app={url}"])
                self._log("✓ Opened in app mode")
                return
            elif edge:
                subprocess.Popen([edge, f"--app={url}"])
                self._log("✓ Opened in app mode")
                return

        # Fallback to regular browser
        webbrowser.open(url)
        self._log("✓ Browser opened")

    def _on_close(self):
        """Clean up on window close"""
        self.watching = False
        self.root.destroy()

    def run(self):
        """Start the application"""
        self.root.mainloop()


def check_and_install_deps():
    """Check for optional dependencies and offer to install them"""
    if not HAS_PANDAS and sys.stdout.isatty():
        print("pandas is recommended for metadata generation.")
        response = input("Install it now? [y/N]: ").strip().lower()
        if response == 'y':
            subprocess.check_call([sys.executable, "-m", "pip", "install", "pandas"])
            print("Installed! Please restart.")
            sys.exit(0)


if __name__ == "__main__":
    check_and_install_deps()
    app = ScriptRunner()
    app.run()
