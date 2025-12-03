import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import os
import yaml
import torch
from torch.hub import download_url_to_file
import subprocess
import sys
import json
import webbrowser
import logging
import re
import tempfile
import time
import shutil

#logging.basicConfig(filename='music_separation.log', level=logging.DEBUG,
#                    format='%(asctime)s - %(levelname)s - %(message)s')

class MusicSeparationGUI:
    def __init__(self, master):
        self.master = master
        master.title("Music Source Separation")

        self.config_file = 'config.json'
        self.models_file = 'models.json'
        # Load config (creates an empty one if it doesn't exist)
        self.load_config()
        self.load_models()

        # Modify inference.py if needed
        self.check_and_modify_inference_py()

        # Create the main frame
        self.main_frame = ttk.Frame(master, padding="10")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        # Create sections
        self.create_io_section()
        self.create_model_section()
        self.create_options_section()
        self.create_action_section()

        # Multi-model window (initialized as None)
        self.multi_model_window = None

    def check_and_modify_inference_py(self):
        inference_py_path = "inference.py"
        if not os.path.exists(inference_py_path):
            logging.error("inference.py not found.")
            return

        with open(inference_py_path, "r", encoding='utf-8') as f:
            code = f.read()

        modified = False

        # --- PATCH 1: Intercept --input_path before the parser crashes ---
        # The standard parser doesn't know --input_path, so we steal it from sys.argv 
        # before the parser sees it.
        if "custom_input_path = None" not in code:
            print("Patching inference.py: Injecting argument interceptor...")
            
            # We look for the start of the proc_folder function
            target_str = "def proc_folder(dict_args):"
            inject_str = """def proc_folder(dict_args):
    # --- GUI PATCH START: Intercept input_path ---
    custom_input_path = None
    if "--input_path" in sys.argv:
        try:
            idx = sys.argv.index("--input_path")
            if idx + 1 < len(sys.argv):
                custom_input_path = sys.argv[idx + 1]
                del sys.argv[idx:idx + 2]
        except: pass
    # --- GUI PATCH END ---
"""
            code = code.replace(target_str, inject_str)

            # Re-inject the path after parsing
            target_str_2 = "args = parse_args_inference(dict_args)"
            inject_str_2 = """args = parse_args_inference(dict_args)
    # --- GUI PATCH START: Restore input_path ---
    if custom_input_path:
        args.input_path = custom_input_path
        if not args.input_folder:
            args.input_folder = os.path.dirname(custom_input_path)
    # --- GUI PATCH END ---"""
            code = code.replace(target_str_2, inject_str_2)
            modified = True

        # --- PATCH 2: Handle Single File Logic in run_folder ---
        # Standard code only globs a folder. We add a check for the specific file.
        if "if getattr(args, 'input_path', None)" not in code:
            print("Patching inference.py: Injecting single file logic...")
            target_str = "mixture_paths = sorted(glob.glob(os.path.join(args.input_folder, '*.*')))"
            inject_str = """if getattr(args, 'input_path', None) and os.path.isfile(args.input_path):
        mixture_paths = [args.input_path]
    else:
        mixture_paths = sorted(glob.glob(os.path.join(args.input_folder, '*.*')))"""
            code = code.replace(target_str, inject_str)
            modified = True

        # --- PATCH 3: Flat Output Directory Structure ---
        # Standard code creates subfolders (output/TrackName/vocals.wav).
        # We want output/TrackName_vocals.wav
        if "output_dir = os.path.join(args.store_dir, file_name)" in code:
            print("Patching inference.py: Flattening output directory structure...")
            # Remove the subfolder creation
            code = code.replace("output_dir = os.path.join(args.store_dir, file_name)", 
                                "# output_dir = os.path.join(args.store_dir, file_name) # GUI PATCH")
            
            # Fix the output path construction
            # Original looks like: output_path = os.path.join(output_dir, f"{instr}.{codec}")
            # We change regex broadly to catch variants
            code = code.replace('output_path = os.path.join(output_dir, f"{instr}.{codec}")', 
                                'output_path = os.path.join(args.store_dir, f"{file_name}_{instr}.{codec}")')
            
            # Also fix the spectrogram output path if it exists
            code = code.replace('output_img_path = os.path.join(output_dir, f"{instr}.jpg")',
                                'output_img_path = os.path.join(args.store_dir, f"{file_name}_{instr}.jpg")')
            
            modified = True

        # --- SAVE CHANGES ---
        if modified:
            try:
                with open(inference_py_path, "w", encoding='utf-8') as f:
                    f.write(code)
                print("inference.py successfully patched.")
                # Update timestamp to prevent re-patching loops if you use that logic
                self.config['last_inference_py_edit'] = os.path.getmtime(inference_py_path)
                self.save_config()
            except Exception as e:
                logging.error(f"Failed to write patched inference.py: {e}")
                messagebox.showerror("Error", f"Failed to patch inference.py:\n{e}")

    def modify_inference_py(self, inference_py_path, inference_code):
        # Replace with the "old" code pattern
        inference_code = inference_code.replace(
            "output_dir = os.path.join(args.store_dir, file_name)\n        os.makedirs(output_dir, exist_ok=True)",
            ""  # Remove the lines that create subfolders
        )
        inference_code = inference_code.replace(
            "output_path = os.path.join(output_dir, f\"{instr}.{codec}\")",
            "output_path = os.path.join(args.store_dir, f\"{file_name}_{instr}.{codec}\")"  # Modify output path
        )
        with open(inference_py_path, "w") as f:
            f.write(inference_code)

        # Record the modification time in config.json (only timestamp update)
        self.update_last_inference_py_edit()
        print("Modified inference.py to use the old output path structure.")

    def update_last_inference_py_edit(self):
        # Update only the timestamp part of the config
        self.config['last_inference_py_edit'] = os.path.getmtime("inference.py")
        self.save_timestamp()

    def save_timestamp(self):
        # Save only the timestamp without GUI data
        temp_config = {'last_inference_py_edit': self.config.get('last_inference_py_edit', None)}
        with open(self.config_file, 'w') as f:
            json.dump(temp_config, f, indent=4)

    def create_io_section(self):
        io_frame = ttk.LabelFrame(self.main_frame, text="Input/Output", padding="10")
        io_frame.grid(column=0, row=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        io_frame.columnconfigure(1, weight=1)

        # Input path (now can be file or folder)
        ttk.Label(io_frame, text="Input Path:").grid(column=0, row=0, sticky=tk.W)
        self.input_path = tk.StringVar(value=self.config.get('input_path', '')) # Changed variable name
        ttk.Entry(io_frame, width=50, textvariable=self.input_path).grid(column=1, row=0, sticky=(tk.W, tk.E), padx=5) # Changed variable name
        ttk.Button(io_frame, text="Browse", command=self.browse_input_path).grid(column=2, row=0) # Changed browse function

        # Output folder
        ttk.Label(io_frame, text="Output Folder:").grid(column=0, row=1, sticky=tk.W)
        self.output_folder = tk.StringVar(value=self.config.get('output_folder', ''))
        ttk.Entry(io_frame, width=50, textvariable=self.output_folder).grid(column=1, row=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(io_frame, text="Browse", command=self.browse_output).grid(column=2, row=1)

        # Model Folder Sort checkbox
        self.model_folder_sort = tk.BooleanVar(value=self.config.get('model_folder_sort', False))
        ttk.Checkbutton(io_frame, text="Organize Output Per Model", variable=self.model_folder_sort).grid(column=0, row=2, sticky=tk.W, columnspan=2)

    def create_model_section(self):
        model_frame = ttk.LabelFrame(self.main_frame, text="Model Selection", padding="10")
        model_frame.grid(column=0, row=1, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        model_frame.columnconfigure(1, weight=1)  # Allow column 1 to expand
        model_frame.rowconfigure(1, weight=1)

        # Model Type Selection
        ttk.Label(model_frame, text="Model Type:").grid(column=0, row=0, sticky=tk.W)
        self.model_type = tk.StringVar(value=self.config.get('model_type', 'VOCALS'))

        self.model_type_options = sorted(set(model['SORT'] for model in self.model_info.values()))
        self.model_type_combo = ttk.Combobox(model_frame, textvariable=self.model_type,
                                             values=self.model_type_options, width=30)
        self.model_type_combo.grid(column=1, row=0, sticky=(tk.W, tk.E), padx=5)
        self.model_type_combo.bind("<<ComboboxSelected>>", self.update_model_list)

        # Specific Model Selection
        ttk.Label(model_frame, text="Specific Model:").grid(column=0, row=1, sticky=tk.NW)
        self.model = tk.StringVar(value=self.config.get('model', ''))
        self.model_list = tk.Listbox(model_frame, selectmode=tk.SINGLE, height=5)
        self.model_list.grid(column=1, row=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5)
        model_scrollbar = ttk.Scrollbar(model_frame, orient="vertical", command=self.model_list.yview)
        model_scrollbar.grid(column=2, row=1, sticky=(tk.N, tk.S))
        self.model_list.configure(yscrollcommand=model_scrollbar.set)

        # Create a frame for the buttons to prevent them from expanding
        buttons_frame = ttk.Frame(model_frame)
        buttons_frame.grid(column=1, row=2, pady=(5, 0))

        # Center the buttons within the buttons_frame
        buttons_frame.columnconfigure(0, weight=1)
        buttons_frame.columnconfigure(1, weight=1)

        # Multi-Model Selection Button
        ttk.Button(buttons_frame, text="Multi-Model", command=self.open_multi_model_window).grid(column=0, row=0, padx=(0, 5))

        # Ensemble Mode Button
        ttk.Button(buttons_frame, text="Ensemble", command=self.open_ensemble_window).grid(column=1, row=0)

        # Update Models button
        ttk.Button(model_frame, text="Update Models", command=self.update_models_from_github).grid(column=1, row=3, pady=(5, 0))

        self.update_model_list()

    def create_options_section(self):
        options_frame = ttk.LabelFrame(self.main_frame, text="Processing Options", padding="10")
        options_frame.grid(column=0, row=2, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        options_frame.columnconfigure(1, weight=1)

        # Extract instrumental
        self.extract_instrumental = tk.BooleanVar(value=self.config.get('extract_instrumental', True))
        ttk.Checkbutton(options_frame, text="Extract other stem", variable=self.extract_instrumental).grid(column=0, row=0, sticky=tk.W, columnspan=2)

        # Export format
        ttk.Label(options_frame, text="Export Format:").grid(column=0, row=1, sticky=tk.W)
        self.export_format = tk.StringVar(value=self.config.get('export_format', 'wav FLOAT'))
        ttk.Combobox(options_frame, textvariable=self.export_format, values=['wav FLOAT', 'flac PCM_16', 'flac PCM_24']).grid(column=1, row=1, sticky=(tk.W, tk.E))

        # Advanced Options Frame
        advanced_frame = ttk.LabelFrame(options_frame, text="Advanced Options", padding="10")
        advanced_frame.grid(column=0, row=2, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=(10, 0)) # Add padding at the top

        # Use default parameters checkbox
        self.use_default_params = tk.BooleanVar(value=True)  # Initially checked
        ttk.Checkbutton(advanced_frame, text="Use Default Parameters", variable=self.use_default_params, command=self.toggle_advanced_options).grid(column=0, row=0, sticky=tk.W, columnspan=3)

        # Use TTA
        self.use_tta = tk.BooleanVar(value=self.config.get('use_tta', False))
        self.tta_checkbutton = ttk.Checkbutton(advanced_frame, text="Use TTA", variable=self.use_tta, state=tk.DISABLED)  # Initially disabled
        self.tta_checkbutton.grid(column=0, row=1, sticky=tk.W, columnspan=3)

        # Overlap
        ttk.Label(advanced_frame, text="Overlap:").grid(column=0, row=2, sticky=tk.W)
        self.overlap = tk.IntVar(value=self.config.get('overlap', 2))

        # Use a Frame to hold the Entry and Scale
        overlap_frame = ttk.Frame(advanced_frame)
        overlap_frame.grid(column=1, row=2, sticky=(tk.W, tk.E))

        self.overlap_entry = ttk.Entry(overlap_frame, width=5, textvariable=self.overlap, state=tk.DISABLED)
        self.overlap_entry.pack(side=tk.LEFT, padx=(0, 5))

        self.overlap_scale = ttk.Scale(overlap_frame, from_=1, to=40, variable=self.overlap, orient=tk.HORIZONTAL, state=tk.DISABLED, command=self.update_overlap_entry)
        self.overlap_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Bind <Return> on Entry to update the Scale
        self.overlap_entry.bind("<Return>", self.update_overlap_scale)

        # Chunk size
        ttk.Label(advanced_frame, text="Chunk Size:").grid(column=0, row=3, sticky=tk.W)
        self.chunk_size = tk.IntVar(value=self.config.get('chunk_size', 352800))
        values = [352800, 485100]
        self.chunk_size_combo = ttk.Combobox(advanced_frame, textvariable=self.chunk_size, values=values, state=tk.DISABLED)
        self.chunk_size_combo.grid(column=1, row=3, sticky=(tk.W, tk.E))
        self.chunk_size_combo.current(values.index(self.chunk_size.get()) if self.chunk_size.get() in values else 0) # Set current value based on self.chunk_size

    def update_overlap_entry(self, *args):
        """Updates the overlap entry when the slider is moved."""
        try:
            value = int(self.overlap_scale.get())
            self.overlap.set(value)
        except ValueError:
            pass

    def update_overlap_scale(self, event=None):
        """Updates the slider when the overlap entry is changed."""
        try:
            value = self.overlap.get()
            if 1 <= value <= 40:
                self.overlap_scale.set(value)
        except (ValueError, tk.TclError):
            pass

    def toggle_advanced_options(self):
        state = tk.NORMAL if not self.use_default_params.get() else tk.DISABLED
        self.tta_checkbutton.config(state=state)
        self.overlap_entry.config(state=state)
        self.overlap_scale.config(state=state)  # Enable/disable the slider too
        self.chunk_size_combo.config(state=state)

    def create_action_section(self):
        action_frame = ttk.Frame(self.main_frame, padding="10")
        action_frame.grid(column=0, row=3, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        action_frame.columnconfigure(0, weight=1)

        # Separate button
        ttk.Button(action_frame, text="Separate", command=self.separate).grid(column=0, row=0, pady=(0, 5))

        # Status label
        self.status = tk.StringVar(value="Ready")
        ttk.Label(action_frame, textvariable=self.status).grid(column=0, row=1)

        # Progress bar
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(action_frame, orient="horizontal", mode="determinate", variable=self.progress_var, maximum=100)
        self.progress_bar.grid(column=0, row=2, pady=(5, 0))

        # Credit label with hyperlink
        credit_label = ttk.Label(action_frame, text="GUI made by Sifted Sand Records",
                                  cursor="hand2", font=("TkDefaultFont", 8, "underline"), foreground="blue")
        credit_label.grid(column=0, row=3, pady=(5, 0))
        credit_label.bind("<Button-1>", lambda e: webbrowser.open_new("https://lnk.bio/siftedsand"))

    def load_config(self):
        try:
            with open(self.config_file, 'r') as f:
                self.config = json.load(f)
        except FileNotFoundError:
            self.config = {}

    def load_models(self):
        try:
            with open(self.models_file, 'r') as f:
                self.model_info = json.load(f)
        except FileNotFoundError:
            self.model_info = {}

    def save_config(self):
        self.config['input_path'] = self.input_path.get() # Changed to input_path
        self.config['output_folder'] = self.output_folder.get()
        self.config['model_type'] = self.model_type.get()
        self.config['model'] = self.model.get()
        self.config['model_folder_sort'] = self.model_folder_sort.get()
        self.config['extract_instrumental'] = self.extract_instrumental.get()
        self.config['export_format'] = self.export_format.get()
        self.config['use_tta'] = self.use_tta.get()
        self.config['overlap'] = self.overlap.get()
        self.config['chunk_size'] = self.chunk_size.get()
        self.config['last_inference_py_edit'] = self.config.get('last_inference_py_edit') # Save the timestamp

        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=4)


    def update_model_list(self, event=None):
        selected_type = self.model_type.get()
        self.model_list.delete(0, tk.END)

        filtered_models = [
            model_name for model_name, model_data in self.model_info.items()
            if model_data.get('SORT') == selected_type
        ]
        filtered_models.sort(key=lambda x: x.lower())

        for model_name in filtered_models:
            self.model_list.insert(tk.END, model_name)

        # Select the first model by default if available
        if self.model_list.size() > 0:
            self.model_list.selection_set(0)
            self.model_list.see(0)

    def browse_input_path(self): # Changed function name
        file_or_folder = filedialog.askopenfilename(filetypes=[("Audio files", "*.wav;*.flac;*.mp3;*.aiff;*.aif"), ("Folders", "*")]) # Allow file or folder selection
        if file_or_folder:
            if os.path.isfile(file_or_folder) or os.path.isdir(file_or_folder): # Check if selected path is valid
                self.input_path.set(file_or_folder) # Changed to input_path
                self.save_config()
            else:
                messagebox.showerror("Error", "Invalid input path selected.")
                return

    def browse_output(self):
        folder = filedialog.askdirectory()
        if folder:
            if not os.path.isdir(folder):
                messagebox.showerror("Error", "Invalid output folder selected.")
                return
            self.output_folder.set(folder)
            self.save_config()

    def download_file(self, url, filename):
        path = 'ckpts'
        os.makedirs(path, exist_ok=True)
        file_path = os.path.join(path, filename)

        if os.path.exists(file_path):
            self.status.set(f"File '{filename}' already exists.")
            self.master.update()
            return file_path

        try:
            self.status.set(f"Downloading '{filename}'...")
            self.master.update()
            download_url_to_file(url, file_path)
            self.status.set(f"File '{filename}' downloaded successfully")
            self.master.update()
            return file_path
        except Exception as e:
            self.status.set(f"Error downloading file '{filename}': {e}")
            self.master.update()
            return None

    def modify_yaml(self, original_config_path):
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as temp_yaml:
                self.temp_config_path = temp_yaml.name

                with open(original_config_path, 'r') as f:
                    data = yaml.safe_load(f)

                # Ensure necessary sections exist
                if 'training' not in data:
                    data['training'] = {}
                if 'audio' not in data:
                    data['audio'] = {}
                if 'inference' not in data:
                    data['inference'] = {}

                if 'use_amp' not in data['training']:
                    data['training']['use_amp'] = True
                data['audio']['chunk_size'] = self.chunk_size.get()
                data['inference']['num_overlap'] = self.overlap.get()

                if data['inference'].get('batch_size') == 1:  # Only update batch size if necessary
                    data['inference']['batch_size'] = 2

                yaml.safe_dump(data, temp_yaml, default_flow_style=False, sort_keys=False, indent=4)
                logging.debug(f"Modified YAML (temp file): {self.temp_config_path}")

        except Exception as e:
            logging.exception(f"Error modifying YAML: {e}")
            messagebox.showerror("Error", f"Error modifying YAML file: {e}")
            return False

        return True

    def separate(self):
        selected_model = self.model_list.get(tk.ANCHOR)
        if not selected_model or selected_model not in self.model_info:
            messagebox.showerror("Error", "Please select a valid model.")
            return

        logging.info(f"Starting separation with model: {selected_model}")
        input_path = self.input_path.get() # Changed to input_path
        output_dir = self._get_output_directory(selected_model)

        try:
            if not self._download_model_files(selected_model):
                return  # _download_model_files handles error messages

            # No need for temp folders in a straight separation
            cmd = self._build_separation_command(selected_model, output_dir, input_path) # Changed to input_path

            logging.info(f"Separation command: {cmd}")  # Log the full command

            # Run separation directly (no threading)
            self._run_separation(cmd, selected_model)

        except Exception as e:
            logging.exception(f"An unexpected error occurred during separation: {e}")  # Log the full traceback
            messagebox.showerror("Error", f"An unexpected error occurred during separation: {e}")

        finally:
            self.save_config()

    def _download_model_files(self, selected_model):
        info = self.model_info[selected_model]
        config_url = info['config_url']
        config_name = info['config_name']
        checkpoint_url = info['checkpoint_url']
        checkpoint_name = info['checkpoint_name']

        config_path = self.download_file(config_url, config_name)
        checkpoint_path = self.download_file(checkpoint_url, checkpoint_name)

        if not config_path or not checkpoint_path:
            messagebox.showerror("Error", "Failed to download necessary files.")
            logging.error("Failed to download config or checkpoint files.")
            return False

        if not self.use_default_params.get():  # Only modify YAML if not using defaults
            if not self.modify_yaml(config_path):
                logging.error("Failed to modify YAML file.")  # Add more specific logging
                return False

        return True

    def _get_output_directory(self, selected_model):
        output_dir = self.output_folder.get()
        if self.model_folder_sort.get():
            output_dir = os.path.join(output_dir, selected_model)
            os.makedirs(output_dir, exist_ok=True)
        return output_dir

    def _build_separation_command(self, selected_model, output_dir, input_path): # Modified function to handle input_path
        info = self.model_info[selected_model]

        if not self.use_default_params.get():
            config_path = self.temp_config_path
        else:
            config_path = os.path.join('ckpts', info['config_name'])

        checkpoint_path = os.path.join('ckpts', info['checkpoint_name'])

        cmd = [
            sys.executable,
            "inference.py",
            "--model_type", info['model_type'],
            "--config_path", config_path,
            "--start_check_point", checkpoint_path,
            "--store_dir", output_dir,
            "--input_path", input_path,  # <--- ALWAYS use --input_path and pass input_path
        ]

        # Remove the old if/elif/else block completely
        # No longer need to check if it's a dir or file here. inference.py handles it.

        # Add other options (rest of the function remains the same)
        if self.extract_instrumental.get():
            cmd.append("--extract_instrumental")

        export_format = self.export_format.get()
        if export_format.startswith('flac'):
            cmd.append("--flac_file")
            cmd.append(f"--pcm_type={export_format.split()[1]}")
        elif export_format == "wav FLOAT":
            cmd.append("--wav_file")

        if self.use_tta.get():
            cmd.append("--use_tta")

        logging.debug(f"Built command: {cmd}")
        return cmd

    def _update_progress_from_output(self, output_line):
        # Windows: "Processing audio chunks:   7%|█████                                     | 134400/1926339 [00:00<00:02, 652215.64it/s]"
        # Linux: "Processing audio chunks:  73%|███████████████████████████████▌           | 1411200/1926339 [00:03<00:01, 416574.69it/s]"
        match = re.search(r"Processing audio chunks:\s+(\d+)%|", output_line)
        if match:
            try:
                progress_percentage = int(match.group(1))
                self.progress_var.set(progress_percentage)
                self.master.update_idletasks()
            except (ValueError, TypeError) as e:
                logging.warning(f"Could not convert progress value to integer: {e}")
                logging.warning(f"Problematic line: {output_line.strip()}")
        elif "%" in output_line:
            logging.warning(f"Percentage character found but regex didn't match: {output_line.strip()}")

    def _prepare_input_files(self, input_folder):
        """
        Prepares input files by creating temporary subfolders for each track.

        Args:
            input_folder: The original input folder containing audio files.

        Returns:
            A list of paths to the temporary subfolders, or None if an error occurs.
        """
        temp_folders = []
        audio_files = [f for f in os.listdir(input_folder) if os.path.isfile(os.path.join(input_folder, f)) and f.lower().endswith(('.wav', '.flac', '.aif', '.aiff', '.mp3'))]

        if not audio_files:
            messagebox.showerror("Error", "No valid audio files found in the input folder.")
            return None

        for i, audio_file in enumerate(audio_files):
            temp_folder_name = f"temp{i+1}"
            temp_folder_path = os.path.join(input_folder, temp_folder_name)
            os.makedirs(temp_folder_path, exist_ok=True)

            source_path = os.path.join(input_folder, audio_file)
            destination_path = os.path.join(temp_folder_path, audio_file)
            shutil.copy2(source_path, destination_path)  # Copy the file to the temp folder

            temp_folders.append(temp_folder_path)

        return temp_folders

    def _cleanup_temp_folders(self, temp_folders, output_dir):
        """
        Cleans up temporary folders by moving output files and deleting the folders.

        Args:
            temp_folders: A list of paths to the temporary subfolders.
            output_dir: The final output directory.
        """
        for temp_folder in temp_folders:
            try:
                # Move output files from temp folder to final output folder
                for item in os.listdir(temp_folder):
                    source_item_path = os.path.join(temp_folder, item)
                    destination_item_path = os.path.join(output_dir, item)
                    if os.path.isfile(source_item_path):  # Only move files
                        shutil.move(source_item_path, destination_item_path)

                # Delete the empty temporary folder
                shutil.rmtree(temp_folder)
            except Exception as e:
                logging.error(f"Error during cleanup of {temp_folder}: {e}")

    def _run_separation(self, cmd, model_name):
        """
        Runs the separation process using the given command.

        Args:
            cmd: The command to execute for separation.
            model_name: The name of the model being used.
        """

        self.status.set(f"Separating ({model_name})...")

        try:
            # Run the process without capturing output
            subprocess.run(cmd, check=True)  # check=True raises an exception if the command fails
            self.status.set(f"Separation of {model_name} completed successfully!")
            logging.info(f"Separation of {model_name} completed successfully.")

        except subprocess.CalledProcessError as e:
            error_message = f"An error occurred during separation of {model_name} (return code {e.returncode}):\n{e.stderr}"
            self.status.set(error_message)
            logging.error(error_message)  # Log the error
            messagebox.showerror("Error", error_message)  # Display error message

        except FileNotFoundError:
            self.status.set("Could not find inference.py script.")
            logging.error("Could not find inference.py script.")
            messagebox.showerror("Error", "Could not find the inference.py script. Ensure it's in the correct location.")
        except Exception as e:
            self.status.set(f"An unexpected error occurred: {e}")
            logging.exception(f"An unexpected error occurred: {e}")
            messagebox.showerror("Error", f"An unexpected error occurred: {e}")
        finally:
            self.master.update_idletasks()  # Update the GUI

    def update_models_from_github(self):
        models_url = "https://raw.githubusercontent.com/SiftedSand/MusicSepGUI/refs/heads/main/models.json"
        try:
            self.status.set("Updating models...")
            self.master.update()
            download_url_to_file(models_url, self.models_file)
            self.load_models()
            self.update_model_list()
            self.status.set("Models updated successfully!")
        except Exception as e:
            self.status.set(f"Error updating models: {e}")

    def open_multi_model_window(self):
        if self.multi_model_window is None or not self.multi_model_window.master.winfo_exists():
            self.multi_model_window = MultiModelWindow(self)
        else:
            self.multi_model_window.master.lift()  # Bring window to the front

        # Update the list of models in the multi-model window
        self.multi_model_window.update_model_list()

    def open_ensemble_window(self):
        EnsembleWindow(self)

class MultiModelWindow:
    def __init__(self, parent):
        self.parent = parent
        self.master = tk.Toplevel(parent.master)
        self.master.title("Multi-Model Selection")

        # Frame
        self.main_frame = ttk.Frame(self.master, padding="10")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)
        self.master.resizable(True, True)  # Allow resizing in both directions

        # Filter Entry
        ttk.Label(self.main_frame, text="Filter:").grid(column=0, row=0, sticky=tk.W)
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", self.update_model_list)
        ttk.Entry(self.main_frame, textvariable=self.filter_var).grid(column=1, row=0, sticky=(tk.W, tk.E), padx=5)

        # Model Listbox
        self.model_list = tk.Listbox(self.main_frame, selectmode=tk.EXTENDED, exportselection=False, height=10)
        self.model_list.grid(column=0, row=1, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5)
        model_scrollbar = ttk.Scrollbar(self.main_frame, orient="vertical", command=self.model_list.yview)
        model_scrollbar.grid(column=3, row=1, sticky=(tk.N, tk.S))
        self.model_list.configure(yscrollcommand=model_scrollbar.set)
        self.main_frame.columnconfigure(0, weight=1)  # Column 0 expands horizontally
        self.main_frame.columnconfigure(1, weight=1)  # Column 1 expands horizontally
        self.main_frame.columnconfigure(2, weight=0) # Column 2 doesn't expand
        self.main_frame.columnconfigure(4, weight=1)  # Column 4 expands horizontally
        self.main_frame.rowconfigure(1, weight=1)    # Row 1 expands vertically
        self.model_list.config(width=0) # Listbox width will now adjust to fit content

        # Model Order Listbox
        ttk.Label(self.main_frame, text="Model Order:").grid(column=4, row=0, sticky=tk.W)
        self.order_list = tk.Listbox(self.main_frame, height=10)
        self.order_list.grid(column=4, row=1, padx=5, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Add Model Button
        ttk.Button(self.main_frame, text="Add ->", command=self.add_to_order).grid(column=1, row=2, pady=5)

        # Remove Model Button
        ttk.Button(self.main_frame, text="<- Remove", command=self.remove_from_order).grid(column=2, row=2, pady=5)

        # Move Up Button
        ttk.Button(self.main_frame, text="Move Up", command=lambda: self.move_in_order(-1)).grid(column=4, row=2, sticky=tk.W, pady=5)

        # Move Down Button
        ttk.Button(self.main_frame, text="Move Down", command=lambda: self.move_in_order(1)).grid(column=4, row=2, sticky=tk.E, pady=5)

        # Processing Mode
        ttk.Label(self.main_frame, text="Mode:").grid(column=0, row=3, sticky=tk.W, pady=(5, 0))
        self.processing_mode = tk.StringVar(value="Sequential")  # Default mode
        tk.Radiobutton(self.main_frame, text="Sequential", variable=self.processing_mode, value="Sequential").grid(column=1, row=3, sticky=tk.W, pady=(5, 0))
        tk.Radiobutton(self.main_frame, text="Independent", variable=self.processing_mode, value="Independent").grid(column=2, row=3, sticky=tk.W, pady=(5, 0))

        # Process Button
        ttk.Button(self.main_frame, text="Process", command=self.process_multi_model).grid(column=4, row=3, pady=5)

        # Close Button
        ttk.Button(self.main_frame, text="Close", command=self.close_window).grid(column=0, row=4, pady=5)

        ttk.Entry(self.main_frame, textvariable=self.filter_var).grid(column=1, row=0, sticky=(tk.W, tk.E), padx=5) # Sticky expands to fill the space in the resizable mainframe

        self.master.geometry("800x400") # Initial size, but user can resize

        self.update_model_list()

    def update_model_list(self, *args):
        self.model_list.delete(0, tk.END)
        filter_text = self.filter_var.get().lower()

        sorted_models = sorted(self.parent.model_info.items(), key=lambda item: (item[1].get('SORT', ''), item[0].lower()))

        current_category = None
        for model_name, model_data in sorted_models:
            model_category = model_data.get('SORT', '')
            display_name = model_name

            if filter_text and filter_text not in model_name.lower() and filter_text not in model_category.lower():
                continue

            if model_category != current_category:
                if model_category:
                    self.model_list.insert(tk.END, f"--- {model_category} ---")
                    self.model_list.itemconfig(tk.END, {'fg': 'blue'})
                current_category = model_category

            self.model_list.insert(tk.END, display_name)

    def add_to_order(self):
        selected_indices = self.model_list.curselection()
        for i in selected_indices:
            model = self.model_list.get(i)
            if not model.startswith("---") and model not in self.order_list.get(0, tk.END):
                self.order_list.insert(tk.END, model)

    def remove_from_order(self):
        selected_indices = self.order_list.curselection()
        for i in reversed(selected_indices):  # Reverse to avoid index issues
            self.order_list.delete(i)

    def move_in_order(self, direction):
        selected_indices = self.order_list.curselection()
        for i in selected_indices:
            if 0 <= i + direction < self.order_list.size():
                model = self.order_list.get(i)
                self.order_list.delete(i)
                self.order_list.insert(i + direction, model)
                self.order_list.selection_set(i + direction)


    def process_multi_model(self):
        ordered_models = self.order_list.get(0, tk.END)
        if not ordered_models:
            messagebox.showerror("Error", "Please add at least one model to the order list.")
            return

        separate_button = self.parent.main_frame.winfo_children()[-1].winfo_children()[0]
        separate_button.config(state=tk.DISABLED)
        multi_model_button = self.parent.main_frame.winfo_children()[1].winfo_children()[2]
        multi_model_button.config(state=tk.DISABLED)

        original_model_folder_sort = self.parent.model_folder_sort.get()
        self.parent.model_folder_sort.set(True)  # Organize output per model

        input_path = self.parent.input_path.get() # Changed to input_path
        output_folder = self.parent.output_folder.get()

        processing_mode = self.processing_mode.get()

        try:
            if processing_mode == "Sequential":
                # Sequential mode: Use temp folders and process sequentially
                temp_folders = self.parent._prepare_input_files(os.path.dirname(input_path) if os.path.isfile(input_path) else input_path) # Modified for single file input
                if not temp_folders:
                    return  # Error already handled in _prepare_input_files

                for i, selected_model in enumerate(ordered_models):
                    if selected_model not in self.parent.model_info:
                        messagebox.showerror("Error", f"Invalid model selected: {selected_model}")
                        return

                    if not self.parent._download_model_files(selected_model):
                        return

                    current_output_folder = os.path.join(output_folder, selected_model)
                    os.makedirs(current_output_folder, exist_ok=True)

                    for temp_folder in temp_folders:
                        track_name = os.path.splitext(os.path.basename(os.path.join(temp_folder, os.listdir(temp_folder)[0])))[0]
                        track_output_folder = os.path.join(current_output_folder, track_name)
                        os.makedirs(track_output_folder, exist_ok=True)

                        if i == 0:  # First model
                            cmd = self.parent._build_separation_command(selected_model, track_output_folder, temp_folder)
                            self.parent._run_separation(cmd, selected_model)
                        else:  # Subsequent models
                            prev_model_output = os.path.join(output_folder, ordered_models[i - 1], track_name)
                            if os.path.exists(prev_model_output):
                                cmd = self.parent._build_separation_command(selected_model, track_output_folder, prev_model_output)
                                self.parent._run_separation(cmd, selected_model)
                            else:
                                logging.warning(f"Output folder from previous model not found: {prev_model_output}")

                self.parent._cleanup_temp_folders(temp_folders, output_folder)

            elif processing_mode == "Independent":
                # Independent mode: Process input folder directly with each model
                for selected_model in ordered_models:
                    if selected_model not in self.parent.model_info:
                        messagebox.showerror("Error", f"Invalid model selected: {selected_model}")
                        return

                    if not self.parent._download_model_files(selected_model):
                        return

                    current_output_folder = os.path.join(output_folder, selected_model)
                    os.makedirs(current_output_folder, exist_ok=True)

                    cmd = self.parent._build_separation_command(selected_model, current_output_folder, input_path) # Changed to input_path
                    self.parent._run_separation(cmd, selected_model)

            else:
                messagebox.showerror("Error", f"Invalid processing mode selected: {processing_mode}")
                return

        except Exception as e:
            error_message = f"An unexpected error occurred during multi-model processing: {e}"
            logging.exception(error_message)
            messagebox.showerror("Error", error_message)
            return
        finally:
            self.parent.model_folder_sort.set(original_model_folder_sort)
            self.parent.input_path.set(input_path) # Changed to input_path
            self.parent.save_config()
            separate_button.config(state=tk.NORMAL)
            multi_model_button.config(state=tk.NORMAL)
            self.close_window()

    def close_window(self):
        self.parent.multi_model_window = None  # Allow the window to be opened again
        self.master.destroy()

class EnsembleWindow:
    def __init__(self, parent):
        self.parent = parent
        self.master = tk.Toplevel(parent.master)
        self.master.title("Ensemble Mode")

        self.ensemble_frame = ttk.Frame(self.master, padding="10")
        self.ensemble_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)

        # Ensemble Type
        ttk.Label(self.ensemble_frame, text="Ensemble Type:").grid(column=0, row=0, sticky=tk.W)
        self.ensemble_type = tk.StringVar(value="avg_wave")
        ensemble_types = ["avg_wave", "median_wave", "min_wave", "max_wave", "avg_fft", "median_fft", "min_fft", "max_fft"]
        self.ensemble_type_combo = ttk.Combobox(self.ensemble_frame, textvariable=self.ensemble_type, values=ensemble_types, width=15)
        self.ensemble_type_combo.grid(column=1, row=0, sticky=(tk.W, tk.E), padx=5)

        # Input Files Frame
        self.input_files_frame = ttk.LabelFrame(self.ensemble_frame, text="Input Files (Select the 'other' stem from each model)", padding="10")
        self.input_files_frame.grid(column=0, row=1, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        self.input_files_frame.columnconfigure(1, weight=1)  # Allow the column with file entries to expand
        for i in range(10):  # Assuming 10 is the maximum number of input files
            self.input_files_frame.rowconfigure(i, weight=0)  # Allow rows to expand if needed
            self.input_files_frame.grid(column=0, row=1, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)

        self.ensemble_frame.columnconfigure(0, weight=1)
        self.ensemble_frame.rowconfigure(1, weight=1)  # Make row 1 (input_files_frame) expand

        self.input_files = []
        self.weights = []
        self.create_input_file_widgets(10)  # Create widgets for up to 10 input files

        # Output File
        ttk.Label(self.ensemble_frame, text="Output File:").grid(column=0, row=2, sticky=tk.W)
        self.output_file = tk.StringVar(value=os.path.join(self.parent.output_folder.get(), "ensemble_output.wav"))
        self.output_entry = ttk.Entry(self.ensemble_frame, width=40, textvariable=self.output_file)
        self.output_entry.grid(column=1, row=2, sticky=(tk.W, tk.E), padx=5)

        # Make the column with the output entry expand
        self.ensemble_frame.columnconfigure(1, weight=1)

        # Button Frame
        button_frame = ttk.Frame(self.ensemble_frame)
        button_frame.grid(column=0, row=4, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        button_frame.columnconfigure(0, weight=1)

        # Process Button
        ttk.Button(button_frame, text="Process", command=self.process_ensemble).grid(column=0, row=0, sticky=tk.W, padx=5)

        # Close Button
        ttk.Button(button_frame, text="Close", command=self.master.destroy).grid(column=1, row=0, sticky=tk.W, padx=5)

        self.master.geometry("700x600")

    def create_input_file_widgets(self, num_files):
        for i in range(num_files):
            ttk.Label(self.input_files_frame, text=f"Input File {i + 1}:").grid(column=0, row=i, sticky=tk.W)
            input_file_var = tk.StringVar()
            ttk.Entry(self.input_files_frame, width=30, textvariable=input_file_var).grid(column=1, row=i, sticky=(tk.W, tk.E), padx=5)
            self.input_files.append(input_file_var)

            ttk.Button(self.input_files_frame, text="Browse", command=lambda i=i: self.browse_input_file(i)).grid(column=2, row=i)

            ttk.Label(self.input_files_frame, text=f"Weight:").grid(column=3, row=i, sticky=tk.W)
            weight_var = tk.IntVar(value=1)
            self.weights.append(weight_var)

            # Add an Entry widget for the weight
            weight_entry = ttk.Entry(self.input_files_frame, width=5, textvariable=weight_var)
            weight_entry.grid(column=4, row=i, sticky=(tk.W, tk.E))

            # Add the Scale widget (optional - you can keep it or remove it)
            ttk.Scale(self.input_files_frame, from_=1, to=10, variable=weight_var, orient=tk.HORIZONTAL).grid(column=5, row=i, sticky=(tk.W, tk.E))

    def browse_input_file(self, index):
        file_path = filedialog.askopenfilename(
            initialdir=self.parent.output_folder.get(),
            title="Select Input File",
            filetypes=(("Audio Files", "*.wav *.flac *.mp3"), ("All Files", "*.*"))
        )
        if file_path:
            self.input_files[index].set(file_path)
            self.master.focus_set()  # Keep focus on the Ensemble window

    def process_ensemble(self):
        ensemble_type = self.ensemble_type.get()
        output_file = self.output_file.get()
        input_files = [f.get() for f in self.input_files if f.get()]
        weights = [w.get() for w in self.weights][:len(input_files)]

        if not all(input_files):
            messagebox.showerror("Error", "Please specify all input files.")
            return

        if not output_file:
            messagebox.showerror("Error", "Please specify an output file.")
            return

        if not os.path.exists("ensemble.py"):
            messagebox.showerror("Error", "Could not find ensemble.py. Ensure it's in the correct location")
            return

        cmd = [
            sys.executable,
            "ensemble.py",
            "--type", ensemble_type,
            "--output", output_file,
            "--files"
        ]
        cmd.extend(input_files)
        cmd.append("--weights")
        cmd.extend(map(str, weights))

        try:
            self.parent.status.set("Running ensemble...")
            self.master.update()
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            self.parent.status.set("Ensemble process completed.")
            messagebox.showinfo("Ensemble", "Ensemble process completed successfully!")
        except subprocess.CalledProcessError as e:
            self.parent.status.set(f"Ensemble process failed: {e.stderr}")
            messagebox.showerror("Error", f"Ensemble process failed:\n{e.stderr}")
        except Exception as e:
            self.parent.status.set(f"An unexpected error occurred: {e}")
            messagebox.showerror("Error", f"An unexpected error occurred:\n{e}")

root = tk.Tk()

def on_closing():
    try:
        if gui.temp_config_path:
            os.remove(gui.temp_config_path)
    except (AttributeError, FileNotFoundError):
        pass  # Handle cases where temp_config_path is not set or file doesn't exist.
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)

gui = MusicSeparationGUI(root)
root.mainloop()
