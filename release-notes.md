# EasySound 2.0.0

A full rewrite of the audio path. EasySound can now play a list of sounds, send them to
specific speakers or groups of speakers, and place them in a room.

Requires StreamController 1.5.0-beta.15 or later.

## Added

- Multiple sounds per action, replacing the single file picker.
- Playback order for those sounds: Random, Sequence, or Shuffle.
- Speaker targeting: the default output, all outputs at once, or one named output.
- Speaker groups, so a set of outputs can be picked as one target.
- Spatial sound, with a Sound Map for placing the listener, the sound, and each speaker.
- Distance delay, which offsets each speaker by the sound's travel time across a room of a given width.
- Worn devices toggle in the Sound Map, for headsets the system does not report as worn.
- Stop All action, with its own fade-out.
- Rate variation, giving each play a random pitch and speed within a set percentage.
- Keep playing on page change, for Play until Turned Off.
- Pause instead of stop, for Play until Turned Off.
- Device-type icons in the speaker dropdown.
- A warning when no PulseAudio or PipeWire server is available.
- A logo variant for light mode.
- A test suite, run on every pull request.

## Changed

- New audio engine built on PulseAudio directly, replacing pygame. This is what makes
  per-speaker routing and spatial placement possible.
- Actions from 1.0.0 are migrated automatically on first load, including their sound paths.
- Rebuilt on StreamController's current action system.
- Runtime dependencies are now numpy, pulsectl, pasimple and soundfile.

## Removed

- The separate legacy action. Existing actions are migrated instead of running alongside it.

## Fixed

- Removing an action left its sound playing.
