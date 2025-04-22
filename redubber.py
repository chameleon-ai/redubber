import argparse
import mimetypes
import os
import shutil
import signal
import subprocess
import traceback
from pydub import AudioSegment
from pydub.silence import split_on_silence
from uvr_cli import uvr_separate

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
def get_wav(filename : str, out_dir='./'):
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

def get_audio_duration(filename : str):
    segment = AudioSegment.from_file(filename)
    return segment.duration_seconds

def separate_audio_from_video(video_input : str, out_dir='./'):
    # Create a temp file that has no sound
    video_no_audio = get_unique_filename(os.path.join(out_dir, os.path.splitext(os.path.basename(video_input))[0]), os.path.splitext(video_input)[-1].replace('.',''))
    ffmpeg_cmd1 = ["ffmpeg", '-hide_banner', '-i', video_input, '-c:v', 'copy', '-an', video_no_audio]
    result = subprocess.run(ffmpeg_cmd1, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0 or not os.path.isfile(video_no_audio):
        print(' '.join(ffmpeg_cmd1))
        print(result.stderr)
        raise RuntimeError('Error rendering temp video. ffmpeg return code: {}'.format(result.returncode))
    audio_no_video = get_unique_filename(os.path.join(out_dir, os.path.splitext(os.path.basename(video_input))[0]), 'mp3')
    ffmpeg_cmd2 = ["ffmpeg", '-hide_banner', '-i', video_input, '-vn', '-acodec', 'mp3', '-b:a', '192k', audio_no_video]
    result = subprocess.run(ffmpeg_cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0 or not os.path.isfile(video_no_audio):
        print(' '.join(ffmpeg_cmd2))
        print(result.stderr)
        raise RuntimeError('Error rendering audio. ffmpeg return code: {}'.format(result.returncode))
    return video_no_audio, audio_no_video

def combine_audio_and_video(video_input :str, audio_input : str, audio_bitrate : int, out_dir = './'):
    category, mimetype = mimetypes.guess_type(video_input)[0].split('/')
    ffmpeg_cmd = ["ffmpeg", '-hide_banner', '-i', video_input, '-i', audio_input, '-c:v', 'copy', '-c:a']
    # Determine which type of audio to use for recombine
    if mimetype == 'mp4':
        print('Using mp4/aac')
        ffmpeg_cmd.append('aac')
    elif mimetype == 'webm':
        print('Using webm/opus')
        ffmpeg_cmd.append('libopus')
    elif mimetype == 'x-matroska':
        print('Using mkv/opus')
        ffmpeg_cmd.append('libopus')
    else:
        raise RuntimeError('Unsupported mime type {}/{}'.format(category, mimetype))
    ffmpeg_cmd.extend(['-b:a', '{}k'.format(audio_bitrate)])
    output_filename = get_unique_filename(os.path.join(out_dir, os.path.splitext(os.path.basename(video_input))[0]), os.path.splitext(video_input)[-1].replace('.',''))
    ffmpeg_cmd.append(output_filename)
    result = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0 or not os.path.isfile(output_filename):
        print(' '.join(ffmpeg_cmd))
        print(result.stderr)
        raise RuntimeError('Error rendering video. ffmpeg return code: {}'.format(result.returncode))
    return output_filename

# For when the initial split attempt isn't enough. Returns the segment split into smaller segments, recursively if needed.
def extra_split(segment : AudioSegment, max_duration : float, min_silence_len : int, silence_thresh : int, print_padding = '  '):
    extra_segments = []
    # Split again, raising the silence threshold and lowering the min silence length
    segments = split_on_silence(segment, min_silence_len=min_silence_len - 10, silence_thresh=silence_thresh + 5, keep_silence=True)
    for seg in segments:
        if seg.duration_seconds <= max_duration: # Good segment
            extra_segments.append(seg)
        else: # Recursive split with higher thresholds
            #print('{}Segment is {:.3f} seconds. Resorting to recursive split.'.format(print_padding,seg.duration_seconds))
            extra_segments.extend(extra_split(seg, max_duration, min_silence_len - 10, silence_thresh + 5, print_padding+'  '))
    
    current_segment = AudioSegment.empty()
    rejoined_segments = []
    # Splitting might cause more fragments than necessary, so rejoin short ones if possible
    for idx, seg in enumerate(extra_segments):
        if current_segment.duration_seconds + seg.duration_seconds < max_duration: # Current segment can be added
            new_segment = current_segment + seg
            current_segment = new_segment
        else: # Segment length exceeds max, add segment and start over with new segment
            rejoined_segments.append(current_segment) # Append segment
            current_segment = seg # Replace segment with current one not added
        # Don't forget the  last segment         
        if idx == len(extra_segments) - 1 and current_segment.duration_seconds > 0.0: 
            rejoined_segments.append(current_segment)
    #print('{}Segment was split into {} smaller segments.'.format(print_padding, len(rejoined_segments)))
    return rejoined_segments

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
        # We don't know how long each segment is, so combine them back into segments up to the max length
        current_segment = AudioSegment.empty()
        rejoined_segments = []
        for idx, seg in enumerate(split_segments):
            #print(current_segment.duration_seconds)
            if seg.duration_seconds > max_duration: # Segment already exceeds max
                rejoined_segments.append(current_segment)
                print('  Warning: Segment is {:.3f} seconds. Attempting to split further...'.format(seg.duration_seconds))
                extra_segments = extra_split(seg, max_duration, min_silence_len, silence_thresh)
                print('  Segment was split into {} smaller segments.'.format(len(extra_segments)))
                rejoined_segments.extend(extra_segments)
                current_segment = AudioSegment.empty() # Clear out past segment
            elif current_segment.duration_seconds + seg.duration_seconds < max_duration: # Current segment can be added
                new_segment = current_segment + seg
                current_segment = new_segment
            else: # Segment length exceeds max, add segment and start over with new segment
                rejoined_segments.append(current_segment) # Append segment
                current_segment = seg # Replace segment with current one not added
            # Don't forget the  last segment         
            if idx == len(split_segments) - 1 and current_segment.duration_seconds > 0.0: 
                rejoined_segments.append(current_segment)
        # Export rejoined segments and add their names to the list
        rejoined_duration = 0.0
        for idx, seg in enumerate(rejoined_segments):
            rejoined_duration += seg.duration_seconds
            segment_name = '{}{}.wav'.format(segment_base_name, idx)
            seg.export(segment_name, format="wav", bitrate="192k")
            segments.append(segment_name)
        if abs(rejoined_duration - total_duration) > 0.01:
            print('Warning: split segments total {:.3f} seconds, but input audio was {:.3f} seconds.'.format(rejoined_duration, total_duration))
    else: # Only one segment, still have to convert to wav
        segments.append(segment_base_name + '0.wav')
        vocal_segment.export(segments[0], format="wav", bitrate="192k")
    return segments

# Concatenate all vocal segments back into one segment
def recombine_segments(original_input : str, converted_segments : list, original_segments : list, sync_segments : bool):
    print('Combining vocal segments.')
    recombined = AudioSegment.empty()
    if len(converted_segments) != len(original_segments):
        raise RuntimeError("Converted segment count {} doesn't match original segment count of {}. Something went wrong during vocal conversion.".format(len(converted_segments), len(original_segments)))
    for idx,seg in enumerate(converted_segments):
        next_segment = AudioSegment.from_file(seg)
        # Sometimes, segment length doesn't match the original. We have to trim or extend to keep in sync.
        original_seg_duration = get_audio_duration(original_segments[idx])
        if sync_segments and (abs(original_seg_duration - next_segment.duration_seconds) > 0.01):
            #print('Converted segment duration: {:.3f}, original segment duration: {:.3f}'.format(next_segment.duration_seconds, original_seg_duration))
            if original_seg_duration > next_segment.duration_seconds:
                diff_ms = int((original_seg_duration - next_segment.duration_seconds) * 1000)
                print('Extending segment {} by {} ms'.format(idx, diff_ms))
                filler = AudioSegment.silent(duration=diff_ms)
                next_segment = next_segment + filler
            elif original_seg_duration < next_segment.duration_seconds:
                diff_ms = int((next_segment.duration_seconds - original_seg_duration) * 1000)
                print('Trimming segment {} by {} ms'.format(idx, diff_ms))
                next_segment = next_segment[:-diff_ms]
        recombined = recombined + next_segment
    output_filename = os.path.splitext(os.path.basename(original_input))[0] + '_(Recombined).mp3'
    recombined.export(output_filename, format="mp3", bitrate="192k")
    return output_filename

# Overlay the vocal and instrumental stems back on top of each other
def overlay_stems(original_input : str, input_vocal_stem : str, input_instrumental_stem : str, instrumental_volume : int, vocal_volume : int, audio_bitrate : int):
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
    overlaid.export(output_filename, format="mp3", bitrate="{}k".format(audio_bitrate))
    return output_filename

def change_file_directory(filename, new_output_path):
    """
    Moves a file to a new directory.

    Parameters:
    filename (str): The full path to the file to be moved.
    new_output_path (str): The new directory where the file should be moved.

    Raises:
    FileNotFoundError: If the specified file does not exist.
    
    Returns:
    str: The new full path of the file.
    """
    # Ensure the new output path exists
    os.makedirs(new_output_path, exist_ok=True)

    # Get the base name of the file (i.e., the file name without the directory)
    file_name = os.path.basename(filename)

    # Create the new full path for the file
    new_file_path = os.path.join(new_output_path, file_name)

    return new_file_path

if __name__ == '__main__':
    try:
        signal.signal(signal.SIGINT, signal_handler)
        parser = argparse.ArgumentParser(
            prog='Redubber',
            description='Redubs audio or video using a reference voice.',
            epilog='Specify the inputs on the command-line. Use -i and -v to explicitly specify input type if context specific parsing fails.')
        parser.add_argument('-i', '--input', type=str, help='Input video or audio to process')
        parser.add_argument('-d', '--in_dir', type=str, help='Input directory. All found video and audio will be processed.')
        parser.add_argument('-o', '--out_dir', type=str, help='Output directory to use when batch processing from --in_dir.')
        parser.add_argument('-k', '--keep_temp_files', action='store_true', help='Keep intermediate temp files')
        parser.add_argument('-v', '--reference_voice', type=str, help='Voice reference to redub with')
        parser.add_argument('--audio_bitrate', type=int, default=128, help='Bitrate, in kbps, of the final output audio. Default is 128.')
        parser.add_argument('--inference_mode', type=str, default='timbre', choices=['timbre','style','voice'], help='Vevo inference type. "style" and "voice" are less reliable but attempt more accurate accents.')
        parser.add_argument('--instrumental_volume', type=int, default=0, help='Boost (or reduce) volume of the instrumental track, in dB')
        parser.add_argument('--ref_language', type=str, default='en', choices=['en', 'zh'], help='Reference language (used by whisper transcription for vevo 1.5 style)')
        parser.add_argument('--input_language', type=str, default='en', choices=['en', 'zh'], help='Source language (used by whisper transcription for vevo 1.5 style)')
        parser.add_argument('--silence_thresh', type=int, default=-48, help='(in dBFS) anything quieter than this will be considered silence')
        parser.add_argument('--skip_uvr', action='store_true', help='Skip Ultimate Vocal Remover inference')
        parser.add_argument('--skip_trim', action='store_true', help='Skip trimming and extending when reassembling output segments. This may cause a desync in the output video.')
        parser.add_argument('--steps', type=int, default=48, help='Vevo flow matching steps.')
        parser.add_argument('--max_segment_duration', type=float, help='Maximum vocal segment duration, in seconds.')
        parser.add_argument('--min_silence_len', type=int, default=350, help='minimum length (in ms) of silence when splitting vocals into chunks')
        parser.add_argument('--vevo_model', type=str, default='1', choices=['1', '1.5'], help='Vevo model version, either 1 or 1.5 (a.k.a vevosing)')
        parser.add_argument('--vocal_volume', type=int, default=0, help='Boost (or reduce) volume of the vocal track, in dB')
        
        args, unknown_args = parser.parse_known_args()
        if help in args:
            parser.print_help()
        input_filenames = []
        reference_voice = None
        if args.keep_temp_files:
            do_cleanup = False
        if args.input is not None: # Input was explicitly specified
            input_filenames.append(args.input)
        if len(unknown_args) > 0: # Input was specified as an unknown argument, attempt smart context parsing
            for arg in unknown_args:
                if os.path.isfile(arg): 
                    category, mimetype = mimetypes.guess_type(arg)[0].split('/')
                    #print('{}/{}'.format(category,mimetype))
                    if category == 'video' and args.input is None:
                        args.input = arg
                        input_filenames.append(arg)
                    # Ambiguous case where audio is specified but can't differentiate between input to process and voice reference
                    elif category == 'audio' and args.input is None and args.reference_voice is None:
                        raise RuntimeError("Can't determine if audio file should be input or reference voice. Please specify -i or -v explicitly.")
                    elif category == 'audio' and args.reference_voice is None:
                        args.reference_voice = arg
                    elif category == 'audio' and args.input is None:
                        input_filenames.append(arg)
        if args.reference_voice is None:
            raise RuntimeError('Reference voice sample required.')
        else: # Convert specified reference to wav if necessary
            reference_voice = get_wav(args.reference_voice)
        
        # Assert appropriate reference audio duration depending on inference mode
        reference_duration = get_audio_duration(reference_voice)
        # 45 seconds for vevo 1 timbre, 15 seconds for vevo 1 voice, 30 seconds for vevo 1.5 across all modes
        max_reference_duration = 45.0 if args.vevo_model == '1' and args.inference_mode == 'timbre' else (15.0 if args.vevo_model == '1' else 30.0)
        if reference_duration > max_reference_duration:
            raise RuntimeError('Reference audio duration of {} seconds exceeds max duration of {} seconds for {} inference mode. Please use shorter reference voice.'.format(reference_duration, max_reference_duration, args.inference_mode))
        
        if args.max_segment_duration is None:
            if args.vevo_model == '1' and args.inference_mode == 'timbre':
                args.max_segment_duration = 45.0 # only vevo 1 timbre can take a long segment
            else:
                args.max_segment_duration= 12
        
        # If --in_dir was specified, add all files
        if args.in_dir is not None:
            if os.path.isdir(args.in_dir):
                filenames = [os.path.join(dirpath,f) for (dirpath, dirnames, filenames) in os.walk(args.in_dir) for f in filenames]
                for filename in filenames:
                    category = mimetypes.guess_type(filename)[0].split('/')[0]
                    # Only add relevant files from the directory
                    if category == 'video' or category == 'audio':
                        input_filenames.append(filename)
            else:
                raise RuntimeError(f'--in_dir "{args.in_dir}" is not a directory or does not exist.')
            if args.out_dir is None:
                args.out_dir = args.in_dir + '.out'
            print(f'Output directory: "{args.out_dir}"')

        for input_filename in input_filenames:
            print(f'Processing "{input_filename}"')
            input_category, input_mimetype = mimetypes.guess_type(input_filename)[0].split('/')
            uvr_input = input_filename
            video_no_audio = None
            if input_category == 'video':
                print('Separating audio from video')
                video_no_audio, audio_no_video = separate_audio_from_video(input_filename)
                files_to_clean.extend([video_no_audio, audio_no_video])
                uvr_input = audio_no_video
            # Detect if we want to skip the uvr step
            vocal_stem = None
            intrumental_stem = None
            if not args.skip_uvr:
                vocal_stem, intrumental_stem = uvr_separate(uvr_input)
                files_to_clean.extend([vocal_stem, intrumental_stem])
            else:
                vocal_stem = uvr_input

            vocal_segments = prepare_vocal_segments(vocal_stem, args.max_segment_duration, args.min_silence_len, args.silence_thresh)
            files_to_clean.extend(vocal_segments)
            print('Total segments to process: {}'.format(len(vocal_segments)))
            if args.vevo_model == '1':
                from vevo_cli import vevo_infer
                coverted_vocals = vevo_infer(vocal_segments, reference_voice, inference_mode=args.inference_mode, flow_matching_steps = args.steps)
            elif args.vevo_model == '1.5':
                from vevosing_cli import vevosing_infer
                coverted_vocals = vevosing_infer(vocal_segments,
                                                reference_voice,
                                                inference_mode=args.inference_mode,
                                                flow_matching_steps = args.steps,
                                                src_language = args.input_language,
                                                ref_language = args.ref_language)
            files_to_clean.extend(coverted_vocals)
            reassembled_vocals = recombine_segments(uvr_input, coverted_vocals, vocal_segments, not args.skip_trim)
            files_to_clean.append(reassembled_vocals)

            # If uvr was skipped, we don't have to overlay the vocal + instrumental stems
            recombined_audio = None
            if not args.skip_uvr:
                recombined_audio = overlay_stems(uvr_input, reassembled_vocals, intrumental_stem, args.instrumental_volume, args.vocal_volume, args.audio_bitrate)
            else:
                recombined_audio = reassembled_vocals
            
            if video_no_audio is not None:
                files_to_clean.append(recombined_audio)
                recombined_video = combine_audio_and_video(video_no_audio, recombined_audio, args.audio_bitrate)
                split = os.path.splitext(os.path.basename(input_filename))
                output_filename = f'{split[0]}_(Redub-{args.inference_mode}){split[-1]}'
                if args.out_dir is not None:
                    output_filename = change_file_directory(output_filename, args.out_dir)
                shutil.move(recombined_video, output_filename)
                print('Output file: {}'.format(output_filename))
            else:
                basename = os.path.splitext(os.path.basename(input_filename))[0]
                ext = os.path.splitext(os.path.basename(recombined_audio))[-1]
                output_filename = f'{basename}_(Redub-{args.inference_mode}){ext}'
                if args.out_dir is not None:
                    output_filename = change_file_directory(output_filename, args.out_dir)
                shutil.move(recombined_audio, output_filename)
                print('Output file: {}'.format(output_filename))
    except argparse.ArgumentError as e:
        print(e)
    except ValueError as e:
        print(e)
    except Exception:
        print(traceback.format_exc())
    cleanup()