"""Render the editable actual-UI screenshot timeline with local FFmpeg."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True,help='New empty render folder')
    parser.add_argument('--font',type=Path,default=Path('/System/Library/Fonts/Supplemental/Arial.ttf'))
    args=parser.parse_args()
    if args.output.exists():
        raise SystemExit('Refusing to overwrite an existing master.')
    if not args.font.is_file():
        raise SystemExit('Provide an installed readable font with --font.')
    args.work.mkdir(parents=True,exist_ok=False)
    root=Path(__file__).resolve().parent
    timeline=json.loads((root/'walkthrough.json').read_text())
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:
        raise SystemExit('Free FFmpeg is required.')
    clips=[]
    for i,shot in enumerate(timeline['shots']):
        caption=args.work/f'caption-{i}.txt'
        caption.write_text(shot['caption'])
        target=args.work/f'shot-{i}.mp4'
        filters=("scale=1138:640:force_original_aspect_ratio=decrease,"
                 "pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=0xf5f3ec,"
                 f"drawtext=fontfile={args.font}:text='InstrumentZero Edge / SOFTWARE PREVIEW':x=70:y=10:fontsize=18:fontcolor=0x222923,"
                 f"drawtext=fontfile={args.font}:text='Actual UI / edited screenshots / synthetic':x=860:y=14:fontsize=12:fontcolor=0x646e65,"
                 f"drawtext=fontfile={args.font}:textfile={caption}:x=70:y=687:fontsize=20:fontcolor=0x222923")
        command=[ffmpeg,'-hide_banner','-loglevel','error','-n','-loop','1','-i',str(root/shot['image']),
                 '-t',str(shot['seconds']),'-vf',filters,'-r',str(timeline['frames_per_second']),
                 '-c:v','libx264','-crf','18','-preset','medium','-pix_fmt','yuv420p','-an',str(target)]
        subprocess.run(command,check=True)
        clips.append(target)
    listing=args.work/'concat.txt'
    listing.write_text(''.join("file '"+str(p)+"'\n" for p in clips))
    subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-n','-f','concat','-safe','0','-i',str(listing),
                    '-c','copy','-movflags','+faststart',str(args.output)],check=True)
    print(args.output)


if __name__=='__main__':
    main()
