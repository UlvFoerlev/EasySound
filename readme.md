
# EasySound

EasySound is a plugin for StreamController that lets the user play audio files through their Stream Deck.
https://github.com/StreamController/StreamController

It provides two actions: **Play Sound**, which covers most needs on its own, and **Stop All Sounds**.
Combining several "Play Sound" actions should cover most advanced needs.

## Updating from v1

Update, then restart StreamController once. On that first start EasySound rewrites your saved pages:
old action ids are renamed and each button's single sound becomes a sound list. Every page is backed up
to `easysound-v1-page-backups` in StreamController's data directory first, and your buttons keep their
settings.

Two things to know. Give the update a moment before restarting: StreamController installs the new Python
dependencies in the background, and a backend that starts before they land has no sound until the next
restart (the log says so explicitly). And migrated pages will not work if you downgrade to v1 again,
which is what the backups are for.

## Requirements

Linux with a PulseAudio-compatible sound server, which means **PulseAudio or PipeWire**. PipeWire works
through its `pipewire-pulse` layer and is the default on current Fedora, Ubuntu and Arch, so on a normal
desktop there is nothing to install. StreamController itself is Linux-only, so this matches the platforms
it supports.

Audio output, device selection, speaker groups and spatial sound are all built on PulseAudio's sink
model. On a system running bare ALSA with no sound server, sounds will not play: the speaker dropdown
says so, and StreamController's log records a warning at startup.

## Play Sound

### Sounds

A key can hold any number of sounds. Open the **Sounds** section, press **Browse**, and select one or
several files at once — hold ctrl or shift in the file dialog to pick more than one. Each sound gets a
row with a delete button, and a sound whose file has since moved or been deleted is marked with a
warning icon.

Sounds are decoded once and cached, and every sound on a page is prepared when the page loads, so the
first press is no slower than the rest. Replacing a file on disk is noticed automatically.

### Play Order

Appears once a key has two or more sounds:

- **Random** — a fresh pick every press, repeats included.
- **In order** — steps through the list and wraps around.
- **Shuffle (no repeats)** — plays every sound once before any repeats, and avoids playing the same
  sound twice in a row across that boundary.

The position in the list is remembered while StreamController runs; it is not saved between restarts.

### Volume

Sets the playback volume for this key, from 0 to 100.

### Button Mode

There are several ways to play sounds:

#### Press
The most common option. The audio plays when the key is pressed.

#### Release
Play the audio file on key release.

#### Hold
The sound will loop as long as the key is held down, and end once it is released.

#### Turn On / Turn Off
The key will act as an on/off button. The audio is played on the relevant state.

#### Play until Turned Off
The sound starts on the first press and loops until pressed again.

This mode adds two options.

**Keep playing on other pages**

- **Off** (default) — the sound stops when you leave the page. Right for a klaxon that belongs to one
  scene.
- **On** — it plays until you turn it off, whichever page you are on. Right for an ambient bed or a
  background playlist.

**Pause instead of stopping**

- **Off** (default) — pressing again stops the sound, and the next press starts it from the beginning.
- **On** — the key pauses and resumes, keeping its place. Turns a long track into something you can
  hold and pick up again mid-scene rather than restarting.

Leaving the page still stops the sound rather than pausing it, even with this on, because a scene change
is a real stop. Combine it with "Keep playing on other pages" if you want the sound to survive the move.

Either way the loop stays under the control of the key that started it, even after switching pages and
coming back, so pressing again always stops or pauses it rather than starting a second copy.

### Fades

**Fade In** starts the sound from silence over 'n' seconds. **Fade Out** takes it back to silence over
'n' seconds: a one-shot fades over its last 'n' seconds, while a looping sound ("Hold" or "Play until
Turned Off") keeps playing for 'n' seconds after it is stopped.

### Advanced

#### Speakers

By default a sound plays on whatever output your system is using. The dropdown also offers:

- **All** — every speaker detected right now.
- **Any single speaker** — picked from the connected devices.
- **A speaker group** — see below.
- **Custom…** — opens the group editor.

Devices are looked up when the key is pressed, so nothing is pinned to a speaker that has since gone
away, and headsets, wired speakers and Bluetooth devices are each shown with their own icon.

#### Speaker Groups

A group is any number of speakers under a name you choose. Groups are shared: every action on every page
picks from the same list, because a group describes your room rather than one button.

Losing a speaker does not break a group. The sound plays on whichever members are connected at that
moment, and the missing ones are named under the dropdown. If none of them are available, the key
reports an error instead of playing silently.

#### Pitch and speed variation

Shifts each press by up to the given percentage, so a sound that fires repeatedly does not sound
identical every time. Pitch and speed move together, as they would on a tape played faster.

#### Spatial sound

Simulates a direction for a sound. Enable it, then open the map: you sit in the centre, your speakers
are around you, and an orange dot marks where the sound comes from. Drag the dot to place the sound, and
drag the speakers to match where they actually stand in your room. Each speaker's brightness shows how
much of the sound it would carry, so a sound placed behind you is carried mostly by the speakers behind
you.

A headset appears as two dots, one per ear, which you can move apart to widen the stereo image. Front
and back cannot be simulated on a headset — that needs head-tracking-style processing this plugin does
not do — but left and right work.

**Distance delay** is optional and off by default. Turn it on, set how wide your room is, and each
speaker is delayed by the time sound actually takes to travel, which strengthens the sense of direction.
The map then draws the distance to each speaker. This works best with two or more similar speakers:
Bluetooth devices add their own delay of 100 ms or more that cannot be measured or compensated, so
mixing wired and wireless speakers will not line up.

## Stop All Sounds

Stops everything EasySound is playing, from any action on any page. Useful as a panic button when
several loops are running. It has its own **Fade Out**, so everything can be taken down gently instead
of cut off.
