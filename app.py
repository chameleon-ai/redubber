import argparse
import os
import signal
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
            description='Redubs stuff',
            epilog='')
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
        if args.keep_temp_files:
            do_cleanup = False
        if args.input is not None: # Input was explicitly specified
            input_filename = args.input
        elif len(unknown_args) > 0: # Input was specified as an unknown argument, attempt smart context parsing
            for arg in unknown_args:
                if os.path.isfile(arg):
                    input_filename = arg
        if args.reference_voice is None:
            print('Reference voice sample required.')
        if help in args:
            parser.print_help()

        vocal_stem, intrumental_stem = uvr_separate(input_filename)
        files_to_clean.extend([vocal_stem, intrumental_stem])
        vocal_segments = prepare_vocal_segments(vocal_stem, args.max_segment_duration, args.min_silence_len, args.silence_thresh)
        files_to_clean.extend(vocal_segments)
        print('Total segments to process: {}'.format(len(vocal_segments)))
        coverted_vocals = vevo_infer(vocal_segments, args.reference_voice)
        files_to_clean.extend(coverted_vocals)
        reassembled_vocals = recombine_segments(input_filename, coverted_vocals)
        files_to_clean.append(reassembled_vocals)
        recombined = recombine_stems(input_filename, reassembled_vocals, intrumental_stem, args.instrumental_volume, args.vocal_volume)
        print('Output file: {}'.format(recombined))
        cleanup()
    except argparse.ArgumentError as e:
        print(e)
    except ValueError as e:
        print(e)
    except Exception:
        print(traceback.format_exc())