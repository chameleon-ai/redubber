from huggingface_hub import hf_hub_download
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'ultimatevocalremovergui'))
#from ultimatevocalremovergui.UVR import ( 
#    ModelData, MainWindow
#)
#os.chdir('..') # The UVR import above causes an unwanted chdir
from modeldata import ModelData
from ultimatevocalremovergui.separate import (
    SeperateAttributes,
    SeperateDemucs, SeperateMDX, SeperateMDXC, SeperateVR,  # Model-related
    save_format, clear_gpu_cache,  # Utility functions
    cuda_available, mps_available, #directml_available,
)
from ultimatevocalremovergui.gui_data.constants import *

def stub(step, inference_iterations):
    pass

vr_cache_source_mapper = {}
mdx_cache_source_mapper = {}
demucs_cache_source_mapper = {}
def cached_source_callback(process_method, model_name=None):
    
    model, sources = None, None
    
    if process_method == VR_ARCH_TYPE:
        mapper = vr_cache_source_mapper
    if process_method == MDX_ARCH_TYPE:
        mapper = mdx_cache_source_mapper
    if process_method == DEMUCS_ARCH_TYPE:
        mapper = demucs_cache_source_mapper
    
    for key, value in mapper.items():
        if model_name in key:
            model = key
            sources = value
    
    return model, sources

def uvr_separate(filename : str):
    
    model = ModelData(model_name='MDX23C_models/MDX23C-8KFFT-InstVoc_HQ.ckpt')
    file_num = 1
    audio_file_base = f"{file_num}_{os.path.splitext(os.path.basename(filename))[0]}"
    export_path = './'
    set_progress_bar = lambda step, inference_iterations=0 : stub(step,inference_iterations)
    write_to_console = lambda progress_text, base_text='':print('{} {}'.format(base_text,progress_text))

    process_data = {
        'model_data': model, 
        'export_path': export_path,
        'audio_file_base': audio_file_base,
        'audio_file': filename,
        'set_progress_bar': set_progress_bar,
        'write_to_console': write_to_console,
        'process_iteration': None, #self.process_iteration,
        'cached_source_callback': cached_source_callback,
        'cached_model_source_holder': None, #self.cached_model_source_holder,
        'list_all_models': [],
        'is_ensemble_master': False,
        'is_4_stem_ensemble': False}
    
    clear_gpu_cache()
    seperator = SeperateMDXC(model, process_data)
    seperator.seperate()

if __name__ == '__main__':
    # Download models
    hf_hub_download(repo_id="Politrees/UVR_resources", filename="MDX23C_models/MDX23C-8KFFT-InstVoc_HQ.ckpt", local_dir="models")
    uvr_separate('baby-got-back-short.mp3')
    print('hello')