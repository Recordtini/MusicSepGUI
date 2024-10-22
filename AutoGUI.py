import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import os
import yaml
import base64
import torch
from torch.hub import download_url_to_file
import subprocess
import sys
import json
import webbrowser

class MusicSeparationGUI:
    def __init__(self, master):
        self.master = master
        master.title("Music Source Separation")

        self.config_file = 'config.json'
        self.models_file = 'models.json'
        self.load_config()
        self.load_models()

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
        
        # Input/Output folders
        self.create_io_section()

        # Model selection
        self.create_model_section()

        # Processing options
        self.create_options_section()
        
    def create_io_section(self):
        io_frame = ttk.LabelFrame(self.main_frame, text="Input/Output", padding="10")
        io_frame.grid(column=0, row=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        io_frame.columnconfigure(1, weight=1)

        # Input folder
        ttk.Label(io_frame, text="Input Folder:").grid(column=0, row=0, sticky=tk.W)
        self.input_folder = tk.StringVar(value=self.config.get('input_folder', ''))
        ttk.Entry(io_frame, width=50, textvariable=self.input_folder).grid(column=1, row=0, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(io_frame, text="Browse", command=self.browse_input).grid(column=2, row=0)

        # Output folder
        ttk.Label(io_frame, text="Output Folder:").grid(column=0, row=1, sticky=tk.W)
        self.output_folder = tk.StringVar(value=self.config.get('output_folder', ''))
        ttk.Entry(io_frame, width=50, textvariable=self.output_folder).grid(column=1, row=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(io_frame, text="Browse", command=self.browse_output).grid(column=2, row=1)
        
    def create_model_section(self):
        model_frame = ttk.LabelFrame(self.main_frame, text="Model Selection", padding="10")
        model_frame.grid(column=0, row=1, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        model_frame.columnconfigure(1, weight=1)
        model_frame.rowconfigure(1, weight=1)

        # Model Type Selection
        ttk.Label(model_frame, text="Model Type:").grid(column=0, row=0, sticky=tk.W)
        self.model_type = tk.StringVar(value=self.config.get('model_type', 'VOCALS'))

        # Get unique SORT categories from model_info
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

        # Update Models button
        ttk.Button(model_frame, text="Update Models", command=self.update_models_from_github).grid(column=1, row=2, pady=(5, 0))

        self.update_model_list()
        
    def update_model_list(self, event=None):
        selected_type = self.model_type.get()
        self.model_list.delete(0, tk.END)  # Clear the current list

        # Filter and sort models by name
        filtered_models = [
            model_name for model_name, model_data in self.model_info.items()
            if model_data.get('SORT') == selected_type
        ]
        filtered_models.sort()  # Sort alphabetically

        # Insert models into the Listbox
        for model_name in filtered_models:
            self.model_list.insert(tk.END, model_name)

        # Select the first model by default, if available
        if self.model_list.size() > 0:
            self.model_list.selection_set(0)
            self.model_list.see(0)

                
    def create_options_section(self):
        options_frame = ttk.LabelFrame(self.main_frame, text="Processing Options", padding="10")
        options_frame.grid(column=0, row=2, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        options_frame.columnconfigure(1, weight=1)

        # Extract instrumental
        self.extract_instrumental = tk.BooleanVar(value=self.config.get('extract_instrumental', True))
        ttk.Checkbutton(options_frame, text="Extract Instrumental", variable=self.extract_instrumental).grid(column=0, row=0, sticky=tk.W, columnspan=2)

        # Export format
        ttk.Label(options_frame, text="Export Format:").grid(column=0, row=1, sticky=tk.W)
        self.export_format = tk.StringVar(value=self.config.get('export_format', 'wav FLOAT'))
        ttk.Combobox(options_frame, textvariable=self.export_format, values=['wav FLOAT', 'flac PCM_16', 'flac PCM_24']).grid(column=1, row=1, sticky=(tk.W, tk.E))

        # Use TTA
        self.use_tta = tk.BooleanVar(value=self.config.get('use_tta', False))
        ttk.Checkbutton(options_frame, text="Use TTA", variable=self.use_tta).grid(column=0, row=2, sticky=tk.W, columnspan=2)

        # Overlap
        ttk.Label(options_frame, text="Overlap:").grid(column=0, row=3, sticky=tk.W)
        self.overlap = tk.IntVar(value=self.config.get('overlap', 2))
        ttk.Scale(options_frame, from_=1, to=40, variable=self.overlap, orient=tk.HORIZONTAL).grid(column=1, row=3, sticky=(tk.W, tk.E))

        # Chunk size
        ttk.Label(options_frame, text="Chunk Size:").grid(column=0, row=4, sticky=tk.W)
        self.chunk_size = tk.IntVar(value=self.config.get('chunk_size', 352800))
        ttk.Combobox(options_frame, textvariable=self.chunk_size, values=[352800, 485100]).grid(column=1, row=4, sticky=(tk.W, tk.E))
        
    def create_action_section(self):
        action_frame = ttk.Frame(self.main_frame, padding="10")
        action_frame.grid(column=0, row=3, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        action_frame.columnconfigure(0, weight=1)

        # Separate button
        ttk.Button(action_frame, text="Separate", command=self.separate).grid(column=0, row=0, pady=(0, 5))

        # Status (moved below the button)
        self.status = tk.StringVar(value="Ready")
        ttk.Label(action_frame, textvariable=self.status).grid(column=0, row=1)

        # Import font module from tkinter
        import tkinter.font as tkFont 

        # Create smaller hyperlink font
        hyperlink_font = tkFont.Font(underline=True, size=8) # Set size to 8 

        # Credit label with hyperlink (added below status)
        credit_label = ttk.Label(action_frame, text="GUI made by Sifted Sand Records", 
                                  cursor="hand2", font=hyperlink_font, foreground="blue")
        credit_label.grid(column=0, row=2, pady=(5, 0))
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
        self.config['input_folder'] = self.input_folder.get()
        self.config['output_folder'] = self.output_folder.get()
        self.config['model_type'] = self.model_type.get()
        self.config['model'] = self.model.get()
        
        self.config['extract_instrumental'] = self.extract_instrumental.get()
        self.config['export_format'] = self.export_format.get()
        self.config['use_tta'] = self.use_tta.get()
        self.config['overlap'] = self.overlap.get()
        self.config['chunk_size'] = self.chunk_size.get()

        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=4)

    def update_model_list(self, event=None):
        selected_type = self.model_type.get()
        self.model_list.delete(0, tk.END)  # Clear the current list

        # Filter models by the selected type
        filtered_models = [
            model_name for model_name, model_data in self.model_info.items()
            if model_data.get('SORT') == selected_type
        ]

        # Case-insensitive alphabetical sort
        filtered_models.sort(key=lambda x: x.lower())

        # Insert models into the Listbox
        for model_name in filtered_models:
            self.model_list.insert(tk.END, model_name)

        # Select the first model by default, if available
        if self.model_list.size() > 0:
            self.model_list.selection_set(0)
            self.model_list.see(0)

    def browse_input(self):
        folder = filedialog.askdirectory()
        if folder:
            self.input_folder.set(folder)
            self.save_config()  

    def browse_output(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output_folder.set(folder)
            self.save_config()  

    def download_file(self, url, filename):
        path = 'ckpts'
        os.makedirs(path, exist_ok=True)
        file_path = os.path.join(path, filename)

        if os.path.exists(file_path):
            self.status.set(f"File '{filename}' already exists.")
            self.master.update()
            return file_path # If the file exists, just return the path 

        # --- Only try to download if the file does NOT exist ---
        try:
            self.status.set(f"Downloading '{filename}'...")
            self.master.update()
            download_url_to_file(url, file_path)
            self.status.set(f"File '{filename}' downloaded successfully.")
            self.master.update()
            return file_path
        except Exception as e:
            self.status.set(f"Error downloading file '{filename}': {e}")
            self.master.update()
            return None

    def modify_yaml(self, yaml_path):
        if not yaml_path.endswith(('.yaml', '.yml')):
            print(f"Skipping non-YAML file: {yaml_path}")
            return 

        with open(yaml_path, 'r') as f:
            data = yaml.load(f, Loader=yaml.FullLoader)

        if 'training' in data and 'use_amp' not in data['training']:
            data['training']['use_amp'] = True

            with open(yaml_path, 'w') as f:
                yaml.dump(data, f, indent=4)

    def separate(self):
        selected_model = self.model_list.get(tk.ANCHOR)
        if not selected_model or selected_model not in self.model_info:
            messagebox.showerror("Error", "Please select a valid model.")
            return

        info = self.model_info[selected_model]

        config_path = self.download_file(info['config_url'], info['config_name'])
        checkpoint_path = self.download_file(info['checkpoint_url'], info['checkpoint_name'])

        if not config_path or not checkpoint_path:
            messagebox.showerror("Error", "Failed to download necessary files.")
            return

        self.modify_yaml(config_path)

        cmd = [
            sys.executable,
            "inference.py",
            "--model_type", info['model_type'],
            "--config_path", config_path,
            "--start_check_point", checkpoint_path,
            "--input_folder", self.input_folder.get(),
            "--store_dir", self.output_folder.get()
        ]

        if self.extract_instrumental.get():
            cmd.append("--extract_instrumental")

        if self.export_format.get().startswith('flac'):
            cmd.append("--flac_file")
            cmd.extend(["--pcm_type", self.export_format.get().split()[1]])

        if self.use_tta.get():
            cmd.append("--use_tta")

        self.status.set("Separating... (This might take a while)")
        self.master.update()
        try:
            subprocess.run(cmd, check=True)
            self.status.set("Separation completed successfully!")
        except subprocess.CalledProcessError:
            self.status.set("An error occurred during separation.")
            messagebox.showerror("Error", "An error occurred during separation.")

        self.save_config() 

    def update_models_from_github(self):
        models_url = "https://raw.githubusercontent.com/SiftedSand/MusicSepGUI/refs/heads/main/models.json"
        try:
            self.status.set("Updating models...")
            self.master.update()
            download_url_to_file(models_url, self.models_file)
            self.load_models()  # Reload model info from updated file
            self.update_model_list()  # Refresh the model listbox
            self.status.set("Models updated successfully!")
        except Exception as e:
            self.status.set(f"Error updating models: {e}")

root = tk.Tk()
gui = MusicSeparationGUI(root)
root.mainloop() 
