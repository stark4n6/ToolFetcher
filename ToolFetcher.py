import os
import sys
import json
import threading
import zipfile
import hashlib
import shutil
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import yaml
import requests
import customtkinter as ctk
from tkinter import messagebox, filedialog

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")
BG_COLOR = "#222a33"

# Asset regex patterns
ASSET_PATTERNS = {
    "win64": r"(?i)(win64|windows[-_]?64|win[-_]?x64|x64|x86_64|amd64|64[-_]?bit)",
    "win32": r"(?i)(win32|windows[-_]?32|win[-_]?x86|x86|i386|386|32[-_]?bit)",
    "linux64": r"(?i)(linux[-_]?64|linux[-_]?amd64|linux[-_]?x64|linux[-_]?x86_64|linuxx86_64|linux64|x86_64|amd64|x64)",
    "linux32": r"(?i)(linux[-_]?32|linux[-_]?386|linuxx86|linuxi386|x86|i386|386|32[-_]?bit)",
    "macos64": r"(?i)(macos[-_]?64|darwin[-_]?64|osx[-_]?64|macos[-_]?x64|darwin[-_]?x64|osx[-_]?x64|macos[-_]?x86_64|darwin[-_]?x86_64|osx[-_]?x86_64|x64|x86_64|arm64|aarch64)",
    "macos32": r"(?i)(macos[-_]?32|darwin[-_]?32|osx[-_]?32|macos[-_]?x86|darwin[-_]?x86|osx[-_]?x86|x86|i386|386|32[-_]?bit)",
    "arm64": r"(?i)(arm64|aarch64|armv8)",
    "arm32": r"(?i)(arm32|armv7|armv6|armhf)"
}

class ToolFetcherApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("ToolFetcher - Python Edition")
        self.geometry("1150x750")
        self.configure(fg_color=BG_COLOR)

        self.script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        self.tools_config = None
        self.tools_dir = ""
        self.row_widgets = {} 
        self.is_running = False

        self.col_weights = {
            0: {"weight": 3, "text": "Tool Name"},
            1: {"weight": 2, "text": "Group"},
            2: {"weight": 2, "text": "Method"},
            3: {"weight": 2, "text": "Local Version"},
            4: {"weight": 2, "text": "Latest Version"},
            5: {"weight": 2, "text": "Status"},
            6: {"weight": 3, "text": "Download Progress"}
        }

        self.setup_ui()

    def setup_ui(self):
        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.pack(fill="x", padx=10, pady=(10, 5))

        # Replaced the separate label with a placeholder and aligned it to the left edge
        self.pat_entry = ctk.CTkEntry(top_frame, placeholder_text="GitHub PAT...", width=200, show="*")
        self.pat_entry.pack(side="left", padx=(0, 10))

        self.btn_load = ctk.CTkButton(top_frame, text="Load Config", command=self.load_config, width=120)
        self.btn_load.pack(side="left", padx=(0, 10))

        self.btn_check = ctk.CTkButton(top_frame, text="Check Updates", command=self.start_check_thread, state="disabled", width=120)
        self.btn_check.pack(side="left", padx=(0, 10))

        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.pack(fill="x", padx=10, pady=(0, 5))

        # Text search field
        self.search_entry = ctk.CTkEntry(action_frame, placeholder_text="Filter Tool Name...", width=200)
        self.search_entry.bind("<KeyRelease>", self.apply_filter)
        self.search_entry.pack(side="left", padx=(0, 10))

        # Group dropdown menu
        self.group_filter_var = ctk.StringVar(value="All Groups")
        self.group_dropdown = ctk.CTkOptionMenu(action_frame, variable=self.group_filter_var, values=["All Groups"], command=self.apply_filter, width=160)
        self.group_dropdown.pack(side="left", padx=(0, 10))

        self.btn_select_all = ctk.CTkButton(action_frame, text="Select All", command=self.select_all, width=100, fg_color="#3a4756", hover_color="#4a596a")
        self.btn_select_all.pack(side="left", padx=(0, 10))

        self.btn_deselect_all = ctk.CTkButton(action_frame, text="Deselect All", command=self.deselect_all, width=100, fg_color="#3a4756", hover_color="#4a596a")
        self.btn_deselect_all.pack(side="left")

        self.btn_run = ctk.CTkButton(action_frame, text="Run Selected Updates", command=self.start_download_thread, width=160)
        self.btn_run.pack(side="right")

        self.header_frame = ctk.CTkFrame(self, fg_color="#1a2027", corner_radius=5)
        self.header_frame.pack(fill="x", padx=(10, 26), pady=(0, 0))
        
        for col_idx, config in self.col_weights.items():
            self.header_frame.grid_columnconfigure(col_idx, weight=config["weight"], uniform="col_group")
            lbl = ctk.CTkLabel(self.header_frame, text=config["text"], anchor="w", font=ctk.CTkFont(weight="bold"), width=10)
            lbl.grid(row=0, column=col_idx, padx=10, pady=5, sticky="ew")

        self.scroll_frame = ctk.CTkScrollableFrame(self, fg_color="#1e252d", height=350)
        self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=(5, 5))
        
        for col_idx, config in self.col_weights.items():
            self.scroll_frame.grid_columnconfigure(col_idx, weight=config["weight"], uniform="col_group")

        self.console = ctk.CTkTextbox(self, height=150, fg_color="#12161b", text_color="#d1d5db", font=ctk.CTkFont(family="Consolas", size=12))
        self.console.pack(fill="x", padx=10, pady=(5, 10))
        self.console.insert("end", "Ready.\n")
        self.console.configure(state="disabled")

    def log(self, message, color=None):
        self.console.configure(state="normal")
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self.console.insert("end", f"[{timestamp}] {message}\n")
        self.console.see("end")
        self.console.configure(state="disabled")
        self.update_idletasks()

    def select_all(self):
        for data in self.row_widgets.values():
            if data["chk"].winfo_ismapped():
                data["chk"].select()
                data["chk_var"].set(data["t_name"])

    def deselect_all(self):
        for data in self.row_widgets.values():
            data["chk"].deselect()
            data["chk_var"].set("off")

    def apply_filter(self, *args):
        query = self.search_entry.get().lower()
        selected_group = self.group_filter_var.get()
        visible_row = 0
        
        for t_name, data in self.row_widgets.items():
            group_name = data["group_name"]
            
            match_text = query in t_name.lower()
            match_group = (selected_group == "All Groups") or (group_name == selected_group)
            
            if match_text and match_group:
                data["chk"].grid(row=visible_row, column=0, padx=10, pady=5, sticky="ew")
                data["lbl_group"].grid(row=visible_row, column=1, padx=10, pady=5, sticky="ew")
                data["lbl_method"].grid(row=visible_row, column=2, padx=10, pady=5, sticky="ew")
                data["lbl_local"].grid(row=visible_row, column=3, padx=10, pady=5, sticky="ew")
                data["lbl_remote"].grid(row=visible_row, column=4, padx=10, pady=5, sticky="ew")
                data["lbl_status"].grid(row=visible_row, column=5, padx=10, pady=5, sticky="ew")
                data["prog_bar"].grid(row=visible_row, column=6, padx=10, pady=5, sticky="ew")
                visible_row += 1
            else:
                data["chk"].grid_forget()
                data["lbl_group"].grid_forget()
                data["lbl_method"].grid_forget()
                data["lbl_local"].grid_forget()
                data["lbl_remote"].grid_forget()
                data["lbl_status"].grid_forget()
                data["prog_bar"].grid_forget()

    def update_widget(self, widget, **kwargs):
        def _update():
            if "select" in kwargs:
                if kwargs["select"]:
                    widget.select()
                    if "var_name" in kwargs:
                        self.row_widgets[kwargs["var_name"]]["chk_var"].set(kwargs["var_name"])
                else:
                    widget.deselect()
                    if hasattr(widget, "_variable") and widget._variable:
                        widget._variable.set("off")
                del kwargs["select"]
                if "var_name" in kwargs:
                    del kwargs["var_name"]
            
            if "value" in kwargs:
                widget.set(kwargs["value"])
                del kwargs["value"]
            
            if kwargs:
                widget.configure(**kwargs)
                
        self.after(0, _update)

    def load_config(self):
        yaml_path = filedialog.askopenfilename(
            title="Select Configuration File",
            initialdir=self.script_dir,
            filetypes=[("YAML files", "*.yaml *.yml"), ("All files", "*.*")]
        )

        if not yaml_path:
            return

        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self.row_widgets.clear()
        
        self.search_entry.delete(0, "end")
        unique_groups = set()

        self.log(f"Loading config from {yaml_path}")
        try:
            with open(yaml_path, 'r') as file:
                self.tools_config = yaml.safe_load(file)

            self.tools_dir = self.tools_config.get("tooldirectory", "")
            if not self.tools_dir:
                self.tools_dir = os.path.join(self.script_dir, "Tools")

            for tool in self.tools_config.get("tools", []):
                t_name = tool.get("name") or tool.get("Name")
                if not t_name:
                    continue

                method = tool.get("DownloadMethod", "Unknown")
                group_name = tool.get("category") or tool.get("Category") or tool.get("group") or tool.get("Group")
                
                if not group_name and tool.get("OutputFolder"):
                    group_name = tool.get("OutputFolder").strip("\\/")
                    
                if not group_name:
                    group_name = "Uncategorized"
                
                unique_groups.add(group_name)
                
                output_folder = os.path.join(self.tools_dir, t_name)
                if tool.get("OutputFolder"):
                    output_folder = os.path.join(self.tools_dir, tool.get("OutputFolder"), t_name)

                marker_file = os.path.join(output_folder, ".downloaded.json")
                local_ver = "Not Installed"
                meta = None

                if os.path.exists(marker_file):
                    try:
                        with open(marker_file, 'r', encoding='utf-16') as mf:
                            meta = json.load(mf)
                    except UnicodeError:
                        try:
                            with open(marker_file, 'r', encoding='utf-8-sig') as mf:
                                meta = json.load(mf)
                        except:
                            pass
                    except:
                        pass

                    if meta:
                        if method in ["gitClone", "branchZip"]:
                            local_ver = meta.get("CommitHash", "Unknown")
                            if local_ver and len(local_ver) >= 40:
                                local_ver = local_ver[:7]
                        elif method == "specificFile":
                            local_ver = meta.get("LastModified") or meta.get("ETag") or meta.get("Timestamp", "Downloaded")
                            try:
                                dt = parsedate_to_datetime(local_ver)
                                local_ver = dt.strftime("%Y-%m-%d %H:%M:%S")
                            except:
                                pass
                        else:
                            local_ver = meta.get("Version", "Unknown")
                            
                        if not local_ver: 
                            local_ver = meta.get("Timestamp", "Downloaded")
                    else:
                        local_ver = "Marker Error"
                        
                elif os.path.exists(output_folder) and any(os.scandir(output_folder)):
                    local_ver = "Unknown (No Marker)"

                chk_var = ctk.StringVar(value="off")
                chk = ctk.CTkCheckBox(self.scroll_frame, text=t_name, variable=chk_var, onvalue=t_name, offvalue="off", width=10)
                lbl_group = ctk.CTkLabel(self.scroll_frame, text=group_name, anchor="w", width=10)
                lbl_method = ctk.CTkLabel(self.scroll_frame, text=method, anchor="w", width=10)
                lbl_local = ctk.CTkLabel(self.scroll_frame, text=local_ver, anchor="w", width=10)
                lbl_remote = ctk.CTkLabel(self.scroll_frame, text="Click Check", anchor="w", width=10)
                lbl_status = ctk.CTkLabel(self.scroll_frame, text="Pending", anchor="w", width=10)
                prog_bar = ctk.CTkProgressBar(self.scroll_frame)
                prog_bar.set(0)

                self.row_widgets[t_name] = {
                    "t_name": t_name, "group_name": group_name, "chk": chk, "chk_var": chk_var, "method": method, 
                    "local": local_ver, "lbl_group": lbl_group, "lbl_method": lbl_method, "lbl_local": lbl_local, "lbl_remote": lbl_remote, 
                    "lbl_status": lbl_status, "prog_bar": prog_bar, "tool_config": tool, "output_folder": output_folder,
                    "local_etag": meta.get("ETag", "") if meta else "",
                    "local_last_modified": meta.get("LastModified", "") if meta else "",
                    "local_timestamp": meta.get("Timestamp", "") if meta else ""
                }

            groups_list = ["All Groups"] + sorted(list(unique_groups))
            self.group_dropdown.configure(values=groups_list)
            self.group_filter_var.set("All Groups")

            self.apply_filter()

            self.btn_check.configure(state="normal")
            self.log(f"Loaded {len(self.row_widgets)} tools.")
            
        except Exception as e:
            messagebox.showerror("Parse Error", str(e))
            self.log(f"Error parsing YAML: {e}")

    def get_headers(self):
        pat = self.pat_entry.get()
        headers = {"User-Agent": "ToolFetcher-Python"}
        if pat:
            headers["Authorization"] = f"token {pat}"
        return headers

    def start_check_thread(self):
        self.btn_check.configure(state="disabled", text="Checking...")
        threading.Thread(target=self.check_updates, daemon=True).start()

    def check_updates(self):
        self.log("Starting remote update check...")
        headers = self.get_headers()

        for t_name, data in self.row_widgets.items():
            method = data["method"]
            repo_url = data["tool_config"].get("RepoUrl", "")
            local_ver = data["local"]
            remote_ver = "Error"
            status = "Unknown"
            status_color = "white"
            dl_url = ""

            try:
                if method == "latestRelease":
                    api_url = repo_url.replace("https://github.com/", "https://api.github.com/repos/")
                    resp = requests.get(f"{api_url}/releases/latest", headers=headers)
                    resp.raise_for_status()
                    r_json = resp.json()
                    remote_ver = r_json.get("tag_name", "Unknown")
                    
                    asset_type = data["tool_config"].get("AssetType")
                    asset_name = data["tool_config"].get("DownloadName") or data["tool_config"].get("AssetFilename")
                    for asset in r_json.get("assets", []):
                        if asset_name and (asset["name"] == asset_name or re.search(asset_name, asset["name"])):
                            dl_url = asset["browser_download_url"]
                            break
                        if asset_type and asset_type in ASSET_PATTERNS and re.search(ASSET_PATTERNS[asset_type], asset["name"]):
                            dl_url = asset["browser_download_url"]
                            break
                    if not dl_url and r_json.get("assets"):
                        dl_url = r_json["assets"][0]["browser_download_url"]

                elif method in ["gitClone", "branchZip"]:
                    branch = data["tool_config"].get("Branch", "master")
                    parts = repo_url.rstrip(".git").split("/")
                    owner, repo = parts[-2], parts[-1]
                    
                    try:
                        resp = requests.get(f"https://api.github.com/repos/{owner}/{repo}/branches/{branch}", headers=headers)
                        resp.raise_for_status()
                    except:
                        branch = "main"
                        resp = requests.get(f"https://api.github.com/repos/{owner}/{repo}/branches/main", headers=headers)
                        resp.raise_for_status()
                    
                    full_sha = resp.json()["commit"]["sha"]
                    remote_ver = full_sha[:7] if full_sha and len(full_sha) >= 40 else full_sha
                    dl_url = f"https://github.com/{owner}/{repo}/archive/{full_sha}.zip"

                elif method == "specificFile":
                    try:
                        resp = requests.head(repo_url, headers=headers, allow_redirects=True)
                        resp.raise_for_status()
                        remote_etag = resp.headers.get("ETag", "")
                        remote_last_mod = resp.headers.get("Last-Modified", "")
                        
                        remote_mod_formatted = ""
                        remote_dt = None
                        if remote_last_mod:
                            try:
                                remote_dt = parsedate_to_datetime(remote_last_mod)
                                remote_mod_formatted = remote_dt.strftime("%Y-%m-%d %H:%M:%S")
                            except:
                                remote_mod_formatted = remote_last_mod
                                
                        data["remote_etag"] = remote_etag
                        data["remote_last_mod"] = remote_last_mod
                        data["remote_dt"] = remote_dt
                        
                        remote_ver = remote_mod_formatted or remote_etag or "No Header Info"
                    except:
                        remote_ver = "Manual Check Required"
                    dl_url = repo_url

                data["dl_url"] = dl_url
                data["remote_ver"] = remote_ver

                if local_ver == "Not Installed":
                    status, status_color = "Missing", "#ff6b6b"
                    self.update_widget(data["chk"], select=True, var_name=t_name)
                elif local_ver in ["Unknown (No Marker)", "Marker Error"]:
                    status, status_color = "Force Update Needed", "#feca57"
                    self.update_widget(data["chk"], select=True, var_name=t_name)
                elif remote_ver not in ["Error", "Manual Check Required", "No Header Info"]:
                    if method == "specificFile":
                        loc_etag = data.get("local_etag", "")
                        loc_mod = data.get("local_last_modified", "")
                        rem_etag = data.get("remote_etag", "")
                        rem_mod = data.get("remote_last_mod", "")
                        
                        if rem_etag and loc_etag:
                            is_update = (rem_etag != loc_etag)
                        elif rem_mod and loc_mod:
                            is_update = (rem_mod != loc_mod)
                        else:
                            is_update = True
                            rem_dt = data.get("remote_dt")
                            loc_ts_str = data.get("local_timestamp", "")
                            
                            if rem_dt and loc_ts_str:
                                try:
                                    loc_dt = datetime.strptime(loc_ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                                    if rem_dt <= loc_dt:
                                        is_update = False
                                except:
                                    pass
                                    
                        if is_update:
                            status, status_color = "Update Available!", "#ff6b6b"
                            self.update_widget(data["chk"], select=True, var_name=t_name)
                        else:
                            status, status_color = "Up to date", "#1dd1a1"
                            self.update_widget(data["chk"], select=False)
                    else:
                        if local_ver != remote_ver:
                            status, status_color = "Update Available!", "#ff6b6b"
                            self.update_widget(data["chk"], select=True, var_name=t_name)
                        else:
                            status, status_color = "Up to date", "#1dd1a1"
                            self.update_widget(data["chk"], select=False)
                else:
                    status = "Manual Check"
                    self.update_widget(data["chk"], select=False)

            except Exception as e:
                remote_ver = "API Error/Rate Limit"
                status, status_color = "Error", "red"

            self.update_widget(data["lbl_remote"], text=remote_ver)
            self.update_widget(data["lbl_status"], text=status, text_color=status_color)

        self.log("Remote check complete.")
        self.update_widget(self.btn_check, state="normal", text="Check Updates")

    def start_download_thread(self):
        selected_tools = [t for t, d in self.row_widgets.items() if d["chk_var"].get() == t]
        if not selected_tools:
            messagebox.showinfo("Info", "Please select at least one tool to update.")
            return

        self.is_running = True
        self.btn_run.configure(state="disabled", text="Working...")
        threading.Thread(target=self.process_downloads, args=(selected_tools,), daemon=True).start()

    def process_downloads(self, tools):
        headers = self.get_headers()
        tmp_dir = os.path.join(self.script_dir, "tmp")
        os.makedirs(tmp_dir, exist_ok=True)

        for t_name in tools:
            data = self.row_widgets[t_name]
            url = data.get("dl_url")
            if not url:
                self.log(f"[{t_name}] No download URL found. Skipping.")
                continue

            self.log(f"[{t_name}] Starting download: {url}")
            self.update_widget(data["lbl_status"], text="Downloading...", text_color="cyan")
            self.update_widget(data["prog_bar"], mode="determinate")
            data["prog_bar"].set(0)

            out_folder = data["output_folder"]
            file_name = url.split("/")[-1]
            tmp_file = os.path.join(tmp_dir, file_name)

            try:
                with requests.get(url, headers=headers, stream=True) as r:
                    r.raise_for_status()
                    total_length = r.headers.get('content-length')
                    
                    data["etag"] = r.headers.get("ETag", "")
                    data["last_modified"] = r.headers.get("Last-Modified", "")
                    
                    with open(tmp_file, 'wb') as f:
                        if total_length is None:
                            data["prog_bar"].configure(mode="indeterminate")
                            data["prog_bar"].start()
                            f.write(r.content)
                            data["prog_bar"].stop()
                            data["prog_bar"].configure(mode="determinate")
                            data["prog_bar"].set(1)
                        else:
                            dl = 0
                            total_length = int(total_length)
                            for chunk in r.iter_content(chunk_size=8192):
                                if chunk:
                                    dl += len(chunk)
                                    f.write(chunk)
                                    self.update_widget(data["prog_bar"], value=dl / total_length)

                self.log(f"[{t_name}] Download complete.")
                self.update_widget(data["lbl_status"], text="Processing...", text_color="yellow")

                extract = data["tool_config"].get("Extract", True)
                if tmp_file.endswith(".zip") and extract:
                    self.process_zip(t_name, tmp_file, out_folder, data)
                else:
                    self.process_file(t_name, tmp_file, out_folder, data)

                self.update_widget(data["lbl_status"], text="Finished", text_color="#1dd1a1")
                self.update_widget(data["lbl_local"], text=data["remote_ver"])
                self.log(f"[{t_name}] Successfully updated.")

            except Exception as e:
                self.log(f"[{t_name}] Error: {str(e)}")
                self.update_widget(data["lbl_status"], text="Failed", text_color="red")

        self.log("All selected tasks complete.")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        self.update_widget(self.btn_run, state="normal", text="Run Selected Updates")
        self.is_running = False

    def hash_file(self, file_path):
        hasher = hashlib.md5()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except:
            return "FILE_HASH_ERROR"

    def remove_managed_files(self, output_folder):
        marker_file = os.path.join(output_folder, ".downloaded.json")
        if not os.path.exists(marker_file):
            return

        try:
            with open(marker_file, 'r', encoding='utf-8') as mf:
                meta = json.load(mf)
            
            manifest = meta.get("Manifest", {})
            if not manifest:
                return

            managed_hashes = {v: k for k, v in manifest.items()}

            for root, dirs, files in os.walk(output_folder):
                for f in files:
                    if f.startswith(".downloaded") or ".save" in f:
                        continue
                    
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, output_folder).replace("\\", "/")
                    
                    current_hash = self.hash_file(full_path)
                    
                    if current_hash in managed_hashes:
                        os.remove(full_path)
                    elif rel_path in manifest:
                        save_num = 1
                        while os.path.exists(f"{full_path}.save{save_num}"):
                            save_num += 1
                        os.rename(full_path, f"{full_path}.save{save_num}")
                        self.log(f"Backed up user-modified file: {rel_path}.save{save_num}")

            os.remove(marker_file)
        except Exception as e:
            self.log(f"Error managing previous files: {str(e)}")

    def write_marker(self, out_folder, data, manifest):
        marker_file = os.path.join(out_folder, ".downloaded.json")
        meta = {
            "Tool": data["t_name"],
            "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "DownloadMethod": data["method"],
            "DownloadURL": data["dl_url"],
            "Version": data["remote_ver"] if data["method"] == "latestRelease" else "",
            "CommitHash": data["remote_ver"] if data["method"] in ["gitClone", "branchZip"] else "",
            "ETag": data.get("etag", ""),
            "LastModified": data.get("last_modified", ""),
            "Manifest": manifest
        }
        with open(marker_file, 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=4)

    def process_zip(self, t_name, zip_path, out_folder, data):
        self.log(f"[{t_name}] Extracting archive...")
        tmp_extract = zip_path + "_ext"
        os.makedirs(tmp_extract, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(tmp_extract)

        contents = os.listdir(tmp_extract)
        if len(contents) == 1 and os.path.isdir(os.path.join(tmp_extract, contents[0])):
            src_dir = os.path.join(tmp_extract, contents[0])
        else:
            src_dir = tmp_extract

        self.remove_managed_files(out_folder)
        os.makedirs(out_folder, exist_ok=True)

        manifest = {}
        for root, dirs, files in os.walk(src_dir):
            for file in files:
                src_file = os.path.join(root, file)
                rel_path = os.path.relpath(src_file, src_dir).replace("\\", "/")
                dst_file = os.path.join(out_folder, rel_path)
                
                os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                shutil.copy2(src_file, dst_file)
                manifest[rel_path] = self.hash_file(dst_file)

        self.write_marker(out_folder, data, manifest)
        shutil.rmtree(tmp_extract, ignore_errors=True)

    def process_file(self, t_name, file_path, out_folder, data):
        self.remove_managed_files(out_folder)
        os.makedirs(out_folder, exist_ok=True)

        file_name = os.path.basename(file_path)
        dst_file = os.path.join(out_folder, file_name)
        shutil.copy2(file_path, dst_file)

        manifest = {file_name: self.hash_file(dst_file)}
        self.write_marker(out_folder, data, manifest)

if __name__ == "__main__":
    app = ToolFetcherApp()
    app.mainloop()