from huggingface_hub import hf_hub_download
from uvr_cli import uvr_separate

if __name__ == '__main__':
    # Download models
    hf_hub_download(repo_id="Politrees/UVR_resources", filename="MDX23C_models/MDX23C-8KFFT-InstVoc_HQ.ckpt", local_dir="models")
    uvr_separate('baby-got-back-short.mp3')
    print('hello')