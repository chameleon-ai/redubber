import argparse
import mimetypes
import os
import signal
import subprocess
import traceback
from pydub import AudioSegment
from pydub.silence import split_on_silence
from uvr_cli import uvr_separate
from vevo_cli import vevo_infer

files_to_clean = [] # List of temp files to be cleaned up at the end
do_cleanup = True
def cleanup():
    if do_cleanup:
        for filename in files_to_clean:
            if os.path.isfile(filename):
                os.remove(filename)
def signal_handler(sig, frame):
    cleanup()

# Finds a new filename that doesn't clash with something else
def get_unique_filename(basename : str, extension : str):
    filename = '{}.{}'.format(basename,extension)
    x = 0
    while os.path.isfile(filename):
        x += 1
        filename = '{}-{}.{}'.format(basename,x,extension)
    return filename

# Converts an audio file to wav if needed
def get_wav(filename, out_dir='./'):
    # Possible mime types: https://www.iana.org/assignments/media-types/media-types.xhtml
    mime, encoding = mimetypes.guess_type(filename)
    if mime == 'audio/wav' or mime == 'audio/x-wav':
        return filename
    elif mime == 'audio/mpeg':
        seg = AudioSegment.from_mp3(filename)
        # Create a new file in the output directory named after the input
        wav_filename = get_unique_filename(os.path.join(out_dir, os.path.splitext(os.path.basename(filename))[0]), 'wav')
        seg.export(wav_filename, format="wav")
        files_to_clean.append(wav_filename)
        return wav_filename
    else:
        raise RuntimeError("Unsupported file type {} for file '{}'".format(mime, filename))

def separate_audio_from_video(video_input, out_dir='./'):
    # Create a temp file that has no sound
    video_no_audio = get_unique_filename(os.path.join(out_dir, os.path.splitext(os.path.basename(video_input))[0]), os.path.splitext(video_input)[-1].replace('.',''))
    files_to_clean.append(video_no_audio)
    ffmpeg_cmd1 = ["ffmpeg", '-hide_banner', '-i', video_input, '-c:v', 'copy', '-an', video_no_audio]
    result = subprocess.run(ffmpeg_cmd1, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0 or not os.path.isfile(video_no_audio):
        print(' '.join(ffmpeg_cmd1))
        print(result.stderr)
        raise RuntimeError('Error rendering temp video. ffmpeg return code: {}'.format(result.returncode))
    audio_no_video = get_unique_filename(os.path.join(out_dir, os.path.splitext(os.path.basename(video_input))[0]), 'mp3')
    ffmpeg_cmd2 = ["ffmpeg", '-hide_banner', '-i', video_input, '-vn', '-acodec', 'mp3', '-b:a', '128k', audio_no_video]
    result = subprocess.run(ffmpeg_cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0 or not os.path.isfile(video_no_audio):
        print(' '.join(ffmpeg_cmd2))
        print(result.stderr)
        raise RuntimeError('Error rendering audio. ffmpeg return code: {}'.format(result.returncode))
    return video_no_audio, audio_no_video

def combine_audio_and_video(video_input, audio_input, out_dir = './'):
    category, mimetype = mimetypes.guess_type(video_input)[0].split('/')
    ffmpeg_cmd = ["ffmpeg", '-hide_banner', '-i', video_input, '-i', audio_input, '-c:v', 'copy', '-c:a']
    # Determine which type of audio to use for recombine
    if mimetype == 'mp4':
        print('Using mp4/aac')
        ffmpeg_cmd.append('aac')
    elif mimetype == 'webm':
        print('Using webm/opus')
        ffmpeg_cmd.append('libopus')
    else:
        raise RuntimeError('Unsupported mime type {}/{}'.format(category, mimetype))
    output_filename = get_unique_filename(os.path.join(out_dir, os.path.splitext(os.path.basename(video_input))[0]), os.path.splitext(video_input)[-1].replace('.',''))
    ffmpeg_cmd.append(output_filename)
    result = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0 or not os.path.isfile(output_filename):
        print(' '.join(ffmpeg_cmd))
        print(result.stderr)
        raise RuntimeError('Error rendering video. ffmpeg return code: {}'.format(result.returncode))
    return output_filename

# Split vocals into segments separated by silence if necessary
def prepare_vocal_segments(input_vocal_stem : str, max_duration : float, min_silence_len : int, silence_thresh : int):
    print('Preparing vocal segments')
    vocal_segment = AudioSegment.from_file(input_vocal_stem)
    total_duration = vocal_segment.duration_seconds
    segment_base_name = os.path.splitext(os.path.basename(input_vocal_stem))[0] + '_segment_'
    segments = []
    if total_duration > max_duration:
        print('Audio length of {:.3f} exceeds max duration of {} seconds. Attempting to split on silence.'.format(total_duration, max_duration))
        split_segments = split_on_silence(vocal_segment, min_silence_len=min_silence_len, silence_thresh=silence_thresh, keep_silence=True)
        for idx, seg in enumerate(split_segments):
            if seg.duration_seconds > max_duration:
                print('Warning: Segment {} is {:.3f} seconds.'.format(idx, seg.duration_seconds))
            segment_name = '{}{}.wav'.format(segment_base_name, idx)
            segments.append(segment_name)
            seg.export(segment_name, format="wav")
    else: # Only one segment, still have to convert to wav
        segments.append(segment_base_name + '0.wav')
        vocal_segment.export(segments[0], format="wav")
    return segments

# Concatenate all vocal segments back into one segment
def recombine_segments(original_input : str, vocal_segments : list):
    print('Combining vocal segments.')
    recombined = AudioSegment.empty()
    for seg in vocal_segments:
        next_segment = AudioSegment.from_file(seg)
        recombined = recombined + next_segment
    output_filename = os.path.splitext(os.path.basename(original_input))[0] + '_(Recombined).mp3'
    recombined.export(output_filename, format="mp3", bitrate="128k")
    return output_filename

# Overlay the vocal and instrumental stems back on top of each other
def recombine_stems(original_input : str, input_vocal_stem : str, input_instrumental_stem : str, instrumental_volume : int, vocal_volume : int):
    print('Overlaying vocal and instrumental stems.')
    vocal_segment = AudioSegment.from_file(input_vocal_stem)
    instrumental_segment = AudioSegment.from_file(input_instrumental_stem)

    # Boost volume if required
    if instrumental_volume != 0:
        instrumental_segment = instrumental_segment + instrumental_volume
    if instrumental_volume != 0:
        vocal_segment = vocal_segment + vocal_volume
    overlaid = instrumental_segment.overlay(vocal_segment)
    output_filename = os.path.splitext(os.path.basename(original_input))[0] + '_(Overlaid).mp3'
    overlaid.export(output_filename, format="mp3", bitrate="128k")
    return output_filename
     

if __name__ == '__main__':
    try:
        signal.signal(signal.SIGINT, signal_handler)
        parser = argparse.ArgumentParser(
            prog='Redubber',
            description='Redubs audio or video using a reference voice.',
            epilog='Specify the inputs on the command-line. Use -i and -v to explicitly specify input type if context specific parsing fails.')
        parser.add_argument('-i', '--input', type=str, help='Input video or audio to process')
        parser.add_argument('-v', '--reference_voice', type=str, help='Voice reference to redub with')
        parser.add_argument('--instrumental_volume', type=int, default=-3, help='Boost (or reduce) volume of the instrumental track, in dB')
        parser.add_argument('--vocal_volume', type=int, default=3, help='Boost (or reduce) volume of the vocal track, in dB')
        parser.add_argument('--max_segment_duration', type=float, default=30.0, help='Maximum vocal segment duration')
        parser.add_argument('--min_silence_len', type=int, default=350, help='minimum length (in ms) of silence when splitting vocals into chunks')
        parser.add_argument('--silence_thresh', type=int, default=-48, help='(in dBFS) anything quieter than this will be considered silence')
        parser.add_argument('-k', '--keep_temp_files', action='store_true', help='Keep intermediate temp files')
        args, unknown_args = parser.parse_known_args()
        input_filename = None
        reference_voice = None
        if args.keep_temp_files:
            do_cleanup = False
        if args.input is not None: # Input was explicitly specified
            input_filename = args.input
        if len(unknown_args) > 0: # Input was specified as an unknown argument, attempt smart context parsing
            for arg in unknown_args:
                if os.path.isfile(arg): 
                    category, mimetype = mimetypes.guess_type(arg)[0].split('/')
                    #print('{}/{}'.format(category,mimetype))
                    if category == 'video' and args.input is None:
                        input_filename = arg
                    # Ambiguous case where audio is specified but can't differentiate between input to process and voice reference
                    elif category == 'audio' and args.input is None and args.reference_voice is None:
                        raise RuntimeError("Can't determine if audio file should be input or reference voice. Please specify -i or -v explicitly.")
                    elif category == 'audio' and args.reference_voice is None:
                        args.reference_voice = arg
                    elif category == 'audio' and args.input is None:
                        input_filename = arg
        if args.reference_voice is None:
            raise RuntimeError('Reference voice sample required.')
        else: # Convert specified reference to wav if necessary
            reference_voice = get_wav(args.reference_voice)
        if help in args:
            parser.print_help()
        input_category, input_mimetype = mimetypes.guess_type(input_filename)[0].split('/')
        uvr_input = input_filename
        video_no_audio = None
        if input_category == 'video':
            print('Separating audio from video')
            video_no_audio, audio_no_video = separate_audio_from_video(input_filename)
            files_to_clean.extend([video_no_audio, audio_no_video])
            uvr_input = audio_no_video
        vocal_stem, intrumental_stem = uvr_separate(uvr_input)
        files_to_clean.extend([vocal_stem, intrumental_stem])
        vocal_segments = prepare_vocal_segments(vocal_stem, args.max_segment_duration, args.min_silence_len, args.silence_thresh)
        files_to_clean.extend(vocal_segments)
        print('Total segments to process: {}'.format(len(vocal_segments)))
        coverted_vocals = vevo_infer(vocal_segments, reference_voice)
        files_to_clean.extend(coverted_vocals)
        reassembled_vocals = recombine_segments(uvr_input, coverted_vocals)
        files_to_clean.append(reassembled_vocals)
        recombined = recombine_stems(uvr_input, reassembled_vocals, intrumental_stem, args.instrumental_volume, args.vocal_volume)
        if video_no_audio is not None:
            files_to_clean.append(recombined)
            final_video = combine_audio_and_video(video_no_audio, recombined)
            print('Output file: {}'.format(final_video))
        else:
            print('Output file: {}'.format(recombined))
    except argparse.ArgumentError as e:
        print(e)
    except ValueError as e:
        print(e)
    except Exception:
        print(traceback.format_exc())
    cleanup()