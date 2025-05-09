# Redubber
Redubs audio or video with any voice using zero-shot voice cloning.\
(It runs stuff through a voice changer, basically.)\
The video stream is copied and the audio is split between a vocal and instrumental track before changing the vocals.\
Therefore, the final output has a different voice with preserved background noise.
This project also attempts to work around the limitations of vevo by splitting arbitrarily long audio into segments separated by silence.

This project leverages the following repositories:

https://github.com/Anjok07/ultimatevocalremovergui

https://github.com/open-mmlab/Amphion

Video Rundown:\
[![YouTube Video](https://img.youtube.com/vi/eQjZxfjdS-U/0.jpg)](https://www.youtube.com/watch?v=eQjZxfjdS-U)

## How Does it Work?
The script goes through several steps:
- Separate the audio from the video (the video bitstream is copied, so there is no re-encoding)
- Separate the audio into vocal and instrumental tracks using Ultimate Vocal Remover
- Split the audio into segments separated by silence if the duration is greater than the max
- Run the audio segments through Amphion Vevo speech-to-speech with zero-shot voice cloning using the reference voice
- Combine the new vocal segments into one vocal track
- Overlay the new vocal track onto the original instrumental track
- Combine the new vocal+instrumental track with the original video

## Installation
- Clone this repository and `cd` to the top level.
- Clone the submodules using `git submodule update --init`. This should produce the `Amphion` and `ultimatevocalremovergui` directories. (submodules are pointers to other repositories at a specific commit)
- Create and activate python virtual environment:
  - `python -m venv venv`
  - `source venv/bin/activate` or `venv\Scripts\activate.bat`
- Install pytorch using the recommended command from the website:
  - https://pytorch.org/
- Install the dependencies:
  - `pip install -r requirements.txt`
- Run the utility (current working directory needs to be the top level of the repo):
  - `python redubber.py -i input.mp4 -v reference.wav`
  - See usage section below
- This is developed on python 3.10 Linux+AMD (ROCM 6.2.4). I can't speak for compatibility with other configurations.

## Usage
- Prepare 15-30 seconds of your reference voice as an `.mp3` or `.wav`, we'll call this `reference.wav`, but it can have any name.
- Find the video or audio that you want to redub. We'll call this `input.mp4`. It can be of any length, but anything longer than 30 seconds will be split.
- Activate your vitual environment
- Invoke the script: `python redubber.py -i input.mp4 -v reference.wav`
- Note that the first time can take a while because it needs to download models. These are downloaded to the `models` directory.
- The output will be named after the input, appended with `_(Redub-timbre)`, i.e. `input_(Redub-timbre).mp4`

## Command-Line Flags
- `-i`/`--input` - The input file to redub (i.e. `-i input.mp4`)
- `-v`/`--reference_voice` - The reference voice to redub with (i.e. `-v reference.wav`)
- `--inference_mode` - The vevo inference mode to use, either `timbre`, `voice`, or `style`. The default, `timbre`, uses the reference voiceprint, but the input accent will remain. `style` mode attempts to mimic the reference accent, and keep the input timbre. `voice` mode attempts to mimic the reference timbre and accent. `style` and `voice` are less reliable than `timbre` mode and requires shorter audio segments. Maximum reference voice length in `timbre` mode is 45 seconds, while maximum reference voice length in `style` and `voice` mode is 15 seconds.
- `--steps` - The number of vevo flow matching steps. Default is 48. Typically you don't have to mess with this.
- `--instrumental_volume` - Adjust the volume, in dB, of the instrumental track by this amount (i.e. `--instrumental_volume -3` will reduce the volume by 3dB)
- `--vocal_volume` - Adjust the volume, in dB, of the vocal track by this amount (i.e. `--vocal_volume 4` will boost the volume by 4dB). You may want to do this if the output voice is too quiet.
- `--max_segment_duration` - Override the default maximum segment duration, in seconds, of the input vocal segments. (i.e. `--max_segment_duration 41.2` will split the input into clips up to 41.2 seconds long. Changing this value is not recommended and may break vevo.)
- `--min_silence_len` - minimum length (in ms) of silence when splitting vocals into chunks. Default is 350.
- `--silence_thresh` - Silence threshold (in dBFS) used when splitting vocals. Anything quieter than this will be considered silence. Default is -48.
- `--audio_bitrate` - Bitrate, in kbps, of the final output audio. Default is 128.
- `--skip_uvr` - Skips Ultimate Vocal Remover inference. Only do this if your input vocals are already clean.
- `--skip_trim` - Sometimes the output audio length doesn't match the input. In this case, the output is trimmed (or silence is added) to make the segment fit the input duration. This flag skips that step. Only do this if you don't care about the output being out of sync with the input.
- `-k`/`--keep_temp_files` - Keep intermediate temp files. Warning: This can result in a lot of clutter in your current working directory, so only use this flag if you want to debug something like the segment silence threshold or inspect the original vocal track or something.
- `--vevo_model` - The vevo model to use, either `1` or `1.5`. Default is `1`.
- `-d`/`--in_dir` - An input directory to batch process. If no `--out_dir` is specified, an output directory named after the in_dir will be made appended with `.out`
- `-o`/`--out_dir` - Files will get placed into this output directory if specified.
- `--ref_language` - Reference language (used by whisper transcription for vevo 1.5 style and voice). Default is `en`.
- `--input_language` - Source language (used by whisper transcription for vevo 1.5 style and voice). Default is `en`.

## Context Specific Command-Line Arguments
It's recommended to use the command-line flags above, but if a file is specified without command-line flags (i.e. `python redubber.py input.mp4 reference.wav`), the script will attempt to figure out which is the input and which is the reference depending on metadata and context:
- If a video file is provided, it's assumed to be the input
- Note that you need to specify the video before the audio, or you'll get an error. The script can only figure out if an audio is the reference if it already has an input.
- If two audio files are provided, you'll get an error because it doesn't know which is the input and which is the reference. Specify `-i` on one of them and the other will be deduced as the reference, and vice versa.
