# MusicSepGUI: A User-Friendly Interface for Music Source Separation

MusicSepGUI is a graphical user interface (GUI) designed to simplify the process of music source separation using [Music-Source-Separation-Training](https://github.com/ZFTurbo/Music-Source-Separation-Training)  by ZFTurbo. It builds upon the Colab notebook by jarredou, found [here](https://github.com/jarredou/Music-Source-Separation-Training-Colab-Inference/tree/main).

**Key Features:**

*   **Multi-Model Processing:**
    *   **Sequential Mode:** Process multiple models in sequence, where the output of one model becomes the input for the next.
    *   **Independent Mode:** Run multiple models independently on the same input audio.
*   **Ensemble Mode:** Combine the outputs of multiple models using various averaging techniques (powered by `ensemble.py` - see [details here]([link_to_ensemble_md](https://github.com/ZFTurbo/Music-Source-Separation-Training/blob/main/docs/ensemble.md))).
*   **Model Management:** Download models directly from the GUI with no external downloading needed, constantly updated!
*   **Advanced Options:** Fine-tune parameters like chunk size, overlap, and export format.

**Prerequisites:**

1. **Python 3.9 or higher:** Ensure you have Python 3.9 or a later version installed on your system.
2. **Music-Source-Separation-Training:** This repository needs to be installed prior, follow [their readme](https://github.com/ZFTurbo/Music-Source-Separation-Training/blob/main/README.md) to get started.

**Installation:**

1. **Download [AutoGUI.py](https://github.com/SiftedSand/MusicSepGUI/blob/main/AutoGUI.py)**
2. **Place `AutoGUI.py` in your main `Music-Source-Separation-Training` folder.**
3. **Download requirements.txt, open a terminal in the folder where you've placed it, and run ``pip install -r requirements.txt``.**

**Usage:**

1. **Launch the GUI:**
2. **Configure Input/Output:**
    *   Select your input audio folder.
    *   Choose an output directory.
    *   Optionally, enable "Organize Output Per Model" to create subfolders for each model's output.
3. **Select a Model:**
    *   Choose a "Model Type" (e.g., VOCALS, DRUMS, BASS).
    *   Select a specific model from the list.
    *   Click "Update Models" to refresh the list from the GitHub repository.
4. **Multi-Model Processing (Optional):**
    *   Click "Multi-Model" to open the Multi-Model window.
    *   Add models to the "Model Order" list.
    *   Choose between "Sequential" and "Independent" processing modes.
5. **Ensemble Mode (Optional):**
    *   Click "Ensemble" to open the Ensemble window.
    *   Select the "other" stem output files from different models.
    *   Adjust weights for each input.
    *   Choose an ensemble type (see [Ensemble Documentation](link_to_ensemble_md)).
6. **Advanced Options (Optional):**
    *   Enable/disable Test Time Augmentation (TTA).
    *   Adjust the "Overlap" and "Chunk Size" parameters.
7. **Separate:**
    *   Click the "Separate" button to start the separation process.

**Troubleshooting:**

*   **"Could not find inference.py":** Make sure `AutoGUI.py` is placed in your main `Music-Source-Separation-Training` folder, where `inference.py` is located.
*   **"Could not find ensemble.py":** If using Ensemble mode, ensure that `ensemble.py` is also present in the same directory.

**Contributing:**

Contributions to MusicSepGUI are welcome! If you have suggestions, bug reports, or want to contribute code, please open an issue or submit a pull request on GitHub.

**Contact:**

For questions or support, please open an issue on this GitHub repository.
