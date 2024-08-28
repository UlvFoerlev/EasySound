
# EasySound

EasySound is a plugin for StreamController that lets the user play audio files through their Stream Deck.
https://github.com/StreamController/StreamController

## Play Sound
EasySound only have on action "Play Sound", this should cover most of the users needs. Combing multipole Play Sound actions should cover most advanced needs. 
The Actions have the following settings:

### Sound File
The path to the audio file. Use browse to open a file dialog.

### Volume
Set the volume of the played sound.

### Buttom Mode
There is several ways to play sounds:

#### Press
The most common option. The audio is press when the key is pressed.

#### Release
Play the audio file on key release.

#### Hold
The sound will loop as long as the key is held down, and end once it is released.

#### Turned On / Turned Off
The key will act as a on/off bottom. The audio is played on the relevant state.

#### Play until Turned Off
The sound will be played on "Turned On" and stop on "Turned Off", see above.

### Fade In
The sound will fade in from zero volume. Set duration in seconds.

### Fade Out
The sound will fade out to zero volume on play. Set duration in seconds. Fade Out will happen when the sound is stopped, so it causes the sound to play for longer.