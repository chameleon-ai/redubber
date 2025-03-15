import argparse
import os
from uvr_cli import uvr_separate

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
            prog='Redubber',
            description='Redubs stuff',
            epilog='')
    parser.add_argument('-i', '--input', type=str, help='Input video or audio to process')
    args, unknown_args = parser.parse_known_args()
    input_filename = None
    if args.input is not None: # Input was explicitly specified
        input_filename = args.input
    elif len(unknown_args) > 0: # Input was specified as an unknown argument, attempt smart context parsing
        for arg in unknown_args:
            if os.path.isfile(arg):
                input_filename = arg
    if help in args:
            parser.print_help()
    vocal_stem, intrumental_stem = uvr_separate(input_filename)
    print(vocal_stem)