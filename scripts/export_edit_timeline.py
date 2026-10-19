"""Export a portable editorial timeline using Pixar-origin OpenTimelineIO (Apache-2.0)."""
import argparse,json
from pathlib import Path
import opentimelineio as otio
p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('output');a=p.parse_args();value=json.loads(Path(a.input).read_text())
known={s['id']:s for s in value['sources']};timeline=otio.schema.Timeline(name='Frame AI Edit');track=otio.schema.Track(name='Selected clips');timeline.tracks.append(track)
for c in value['clips']:
 source=known[c['source_id']]
 # Relink by original filename, never expose server paths or signed URLs.
 ref=otio.schema.ExternalReference(target_url=source['name'],available_range=otio.opentime.TimeRange(otio.opentime.RationalTime(0,30),otio.opentime.RationalTime(round(source['duration']*30),30)))
 clip=otio.schema.Clip(name=c['reason'],media_reference=ref,source_range=otio.opentime.TimeRange(otio.opentime.RationalTime(round(c['start']*30),30),otio.opentime.RationalTime(round((c['end']-c['start'])*30),30)))
 clip.metadata['frame']={'effect':c['effect'],'note':'Source clips and timing only. Relink original files; subtitles and focus effects are baked into the MP4.'};track.append(clip)
otio.adapters.write_to_file(timeline,a.output)
