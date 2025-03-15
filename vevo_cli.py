import errno
import mimetypes
import os
import sys
import traceback
from pydub import AudioSegment
import torch
sys.path.append('./Amphion') # For importing modules relative to the Amphion directory
import Amphion.models.vc.vevo.vevo_utils as vevo_utils
from huggingface_hub import snapshot_download

# Do vevo inference based on the provided mode string
def run_inference(pipeline : vevo_utils.VevoInferencePipeline,
                  mode : str,
                  content : str,
                  ref_style : str,
                  ref_timbre : str,
                  steps : int):
    if mode == 'voice':
        return pipeline.inference_ar_and_fm(
            src_wav_path=content,
            src_text=None,
            style_ref_wav_path=ref_style,
            timbre_ref_wav_path=ref_timbre,
            flow_matching_steps=steps
        )
    elif mode == 'timbre':
        return pipeline.inference_fm(
            src_wav_path=content,
            timbre_ref_wav_path=ref_timbre,
            flow_matching_steps=steps
        )
    else:
        raise RuntimeError("Unrecognized inference mode '{}'".format(mode))

def load_model():
    device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
    
    # Content Tokenizer
    local_dir = snapshot_download(
        repo_id="amphion/Vevo",
        repo_type="model",
        cache_dir="./models/Vevo",
        allow_patterns=["tokenizer/vq32/*"],
    )
    content_tokenizer_ckpt_path = os.path.join(
        local_dir, "tokenizer/vq32/hubert_large_l18_c32.pkl"
    )

    # Content-Style Tokenizer
    local_dir = snapshot_download(
        repo_id="amphion/Vevo",
        repo_type="model",
        cache_dir="./models/Vevo",
        allow_patterns=["tokenizer/vq8192/*"],
    )
    content_style_tokenizer_ckpt_path = os.path.join(local_dir, "tokenizer/vq8192")

    # Autoregressive Transformer
    local_dir = snapshot_download(
        repo_id="amphion/Vevo",
        repo_type="model",
        cache_dir="./models/Vevo",
        allow_patterns=["contentstyle_modeling/Vq32ToVq8192/*"],
    )
    ar_cfg_path = "./config/Vq32ToVq8192.json"
    ar_ckpt_path = os.path.join(local_dir, "contentstyle_modeling/Vq32ToVq8192")

    # Flow Matching Transformer
    local_dir = snapshot_download(
        repo_id="amphion/Vevo",
        repo_type="model",
        cache_dir="./models/Vevo",
        allow_patterns=["acoustic_modeling/Vq8192ToMels/*"],
    )
    fmt_cfg_path = "./config/Vq8192ToMels.json"
    fmt_ckpt_path = os.path.join(local_dir, "acoustic_modeling/Vq8192ToMels")

    # Vocoder
    local_dir = snapshot_download(
        repo_id="amphion/Vevo",
        repo_type="model",
        cache_dir="./models/Vevo",
        allow_patterns=["acoustic_modeling/Vocoder/*"],
    )
    vocoder_cfg_path = "./Amphion/models/vc/vevo/config/Vocoder.json"
    vocoder_ckpt_path = os.path.join(local_dir, "acoustic_modeling/Vocoder")

    # Inference
    pipeline = vevo_utils.VevoInferencePipeline(
        content_tokenizer_ckpt_path=content_tokenizer_ckpt_path,
        content_style_tokenizer_ckpt_path=content_style_tokenizer_ckpt_path,
        ar_cfg_path=ar_cfg_path,
        ar_ckpt_path=ar_ckpt_path,
        fmt_cfg_path=fmt_cfg_path,
        fmt_ckpt_path=fmt_ckpt_path,
        vocoder_cfg_path=vocoder_cfg_path,
        vocoder_ckpt_path=vocoder_ckpt_path,
        device=device
    )
    return pipeline

def vevo_infer(voice_segments : list, reference_voice : str):
    print('Running vevo inference...')
    outputs = []
    pipeline = load_model()
    for segment in voice_segments:
        output_filename = '{}_({}).wav'.format(os.path.splitext(os.path.basename(segment))[0], os.path.splitext(os.path.basename(reference_voice))[0])
        print(output_filename)
        gen_audio = run_inference(pipeline, 'timbre', segment, reference_voice, reference_voice, 32)
        vevo_utils.save_audio(gen_audio, target_sample_rate=48000, output_path=output_filename)
        outputs.append(output_filename)
    return outputs