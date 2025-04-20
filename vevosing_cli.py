import os
import sys
import torch
sys.path.append('./Amphion') # For importing modules relative to the Amphion directory
import Amphion.models.svc.vevosing.vevosing_utils as vevosing_utils
from huggingface_hub import snapshot_download

# Do vevo inference based on the provided mode string
def run_inference(pipeline : vevosing_utils.VevosingInferencePipeline,
                  mode : str,
                  content : str,
                  ref_timbre : str,
                  steps : int,
                  content_transcript : str = None,
                  content_language = 'en',
                  ref_transcript : str = None,
                  ref_language = 'en'):
    if mode == 'voice':
        return pipeline.inference_ar_and_fm(
            task="recognition-synthesis",
            src_wav_path=content,
            src_text=content_transcript,
            style_ref_wav_path=content,
            style_ref_wav_text=content_transcript,
            src_text_language=content_language,
            style_ref_wav_text_language=ref_language,
            timbre_ref_wav_path=ref_timbre,
            use_style_tokens_as_ar_input=True,
            flow_matching_steps=steps
        )
    elif mode == 'style':
        return pipeline.inference_ar_and_fm(
            task="recognition-synthesis",
            src_wav_path=content,
            src_text=content_transcript,
            style_ref_wav_path=ref_timbre,
            style_ref_wav_text=ref_transcript,
            src_text_language=content_language,
            style_ref_wav_text_language=ref_language,
            timbre_ref_wav_path=ref_timbre,
            use_style_tokens_as_ar_input=True,
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
        repo_id="amphion/Vevo1.5",
        repo_type="model",
        cache_dir="./models/Vevo1.5",
        allow_patterns=["tokenizer/prosody_fvq512_6.25hz/*"],
    )
    prosody_tokenizer_ckpt_path = os.path.join(
        local_dir, "tokenizer/prosody_fvq512_6.25hz"
    )

    # Content-Style Tokenizer
    local_dir = snapshot_download(
        repo_id="amphion/Vevo1.5",
        repo_type="model",
        cache_dir="./models/Vevo1.5",
        allow_patterns=["tokenizer/contentstyle_fvq16384_12.5hz/*"],
    )
    content_style_tokenizer_ckpt_path = os.path.join( local_dir, "tokenizer/contentstyle_fvq16384_12.5hz")

    # Autoregressive Transformer
    ar_model_name = "ar_emilia101k_singnet7k"
    local_dir = snapshot_download(
        repo_id="amphion/Vevo1.5",
        repo_type="model",
        cache_dir="./models/Vevo1.5",
        allow_patterns=[f"contentstyle_modeling/{ar_model_name}/*"],
    )
    ar_cfg_path = f"./config/{ar_model_name}.json"
    ar_ckpt_path = os.path.join(local_dir, "contentstyle_modeling/ar_emilia101k_singnet7k")

    # Flow Matching Transformer
    fm_model_name = "fm_emilia101k_singnet7k"
    local_dir = snapshot_download(
        repo_id="amphion/Vevo1.5",
        repo_type="model",
        cache_dir="./models/Vevo1.5",
        allow_patterns=[f"acoustic_modeling/{fm_model_name}/*"],
    )
    fmt_cfg_path = f"./config/{fm_model_name}.json"
    fmt_ckpt_path = os.path.join(local_dir, "acoustic_modeling/fm_emilia101k_singnet7k")

    # Vocoder
    local_dir = snapshot_download(
        repo_id="amphion/Vevo1.5",
        repo_type="model",
        cache_dir="./models/Vevo1.5",
        allow_patterns=["acoustic_modeling/Vocoder/*"],
    )
    vocoder_cfg_path = "./Amphion/models/svc/vevosing/config/vocoder.json"
    vocoder_ckpt_path = os.path.join(local_dir, "acoustic_modeling/Vocoder")

    # Inference
    pipeline = vevosing_utils.VevosingInferencePipeline(
        prosody_tokenizer_ckpt_path=prosody_tokenizer_ckpt_path,
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

def vevosing_infer(voice_segments : list, reference_voice : str, inference_mode = 'timbre', flow_matching_steps = 32, src_language = 'en', ref_language = 'en'):
    print('Running vevo inference...')
    outputs = []
    pipeline = load_model()
    ref_transcript = None
    content_transcript = None
    if inference_mode != 'timbre':
        print('Loading whisper...')
        import whisper
        whisper_model = whisper.load_model("large-v3-turbo", device="cuda", download_root="./models/whisper")
        print('Transcribing reference...')
        ref_result = whisper_model.transcribe(reference_voice, language=ref_language)
        ref_transcript = ref_result['text']
        print(ref_transcript)
    for segment in voice_segments:
        output_filename = '{}_({}).wav'.format(os.path.splitext(os.path.basename(segment))[0], os.path.splitext(os.path.basename(reference_voice))[0])
        print(output_filename)
        if inference_mode != 'timbre':
            content_result = whisper_model.transcribe(segment, language=ref_language)
            content_transcript = content_result['text']
            print(content_transcript)
        gen_audio = run_inference(pipeline,
                                  inference_mode,
                                  segment,
                                  reference_voice,
                                  flow_matching_steps,
                                  content_transcript=content_transcript,
                                  content_language=src_language,
                                  ref_transcript=ref_transcript,
                                  ref_language = ref_language)
        vevosing_utils.save_audio(gen_audio, target_sample_rate=48000, output_path=output_filename)
        outputs.append(output_filename)
    return outputs