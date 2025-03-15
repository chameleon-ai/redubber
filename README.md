# Redubber
Redubs audio or video with any voice using zero-shot voice cloning.\
This project leverages the following repositories:

https://github.com/Anjok07/ultimatevocalremovergui

https://github.com/open-mmlab/Amphion

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
- Clone the submodules using `git submodule init`. This should produce the `Amphion` and `ultimatevocalremovergui` directories.
- Create and activate python virtual environment:
  - `python -m venv venv`
  - `source venv/bin/activate` or `venv\Scripts\activate.bat`
- Install pytorch using the recommended command from the website:
  - https://pytorch.org/
- Install the dependencies:
  - `pip install -r requirements.txt`
- Run the app (current working directory needs to be the top level of the repo):
  - `python app.py`
- This is developed on python 3.10 Linux+AMD (ROCM 6.2). I can't speak for compatibility with other configurations.

## Usage
- Prepare about 30 seconds of your reference voice as an `.mp3` or `.wav`, we'll call this `reference.wav`, but it can have any name.
- Find the video or audio that you want to redub. We'll call this `input.mp4`. It can be of any length, but anything longer than 30 seconds will be split.
- Activate your vitual environment
- Invoke the script: `python app.py -i input.mp4 -v reference.wav`
- Note that the first time can take a while because it needs to download models. These are downloaded to the `models` directory.
- The output will be named after the input, appended with `_(Redub)`, i.e. `input_(Redub).mp4`

## Command-Line Flags
- `-i`/`--input` - The input file to redub (i.e. `-i input.mp4`)
- `-v`/`--reference_voice` - The reference voice to redub with (i.e. `-v reference.wav`)
- `--instrumental_volume` - Adjust the volume, in dB, of the instrumental track by this amount (i.e. `--instrumental_volume -3` will reduce the volume by 3dB)
- `--vocal_volume` - Adjust the volume, in dB, of the vocal track by this amount (i.e. `--vocal_volume 4` will boost the volume by 4dB)
- `--max_segment_duration` - Change the maximum segment duration, in seconds, allowed before attempting to split the vocal track into segments. (i.e. `--max_segment_duration 41.2` will allow the clip to be 41.2 seconds long)
- `--min_silence_len` - minimum length (in ms) of silence when splitting vocals into chunks. Default is 350.
- `--silence_thresh` - Silence threchold (in dBFS) used when splitting vocals. Anything quieter than this will be considered silence. Default is -48.
- `--audio_bitrate` - Bitrate, in kbps, of the final output audio. Default is 128.
- `-k`/`--keep_temp_files` - Keep intermediate temp files. Warning: This can result in a lot of clutter in your current working directory, so only use this flag if you want to debug something like the segment silence threshold or inspect the original vocal track or something.

## Context Specific Command-Line Arguments
It's recommended to use the command-line flags above, but if a file is specified without command-line flags (i.e. `python app.py input.mp4 reference.wav`), the script will attempt to figure out which is the input and which is the reference depending on metadata and context:
- If a video file is provided, it's assumed to be the input
- Note that you need to specify the video before the audio, or you'll get an error. The script can only figure out if an audio is the reference if it already has an input.
- If two audio files are provided, you'll get an error because it doesn't know which is the input and which is the reference. Specify `-i` on one of them and the other will be deduced as the reference, and vice versa.
