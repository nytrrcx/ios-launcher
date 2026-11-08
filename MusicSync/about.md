# ProMotion Music Sync

Keeps the main song aligned with the game's level clock during normal classic
attempts with the ProMotion launcher. Click Between Frames can stay enabled.

The mod learns the initial song offset, then checks the actual main-song position
every 100 ms. A persistent difference above 80 ms triggers a seek to the expected
position, at most once per second. It changes neither game speed nor physics/input
processing. Seeking may produce a small audible jump; this is a synchronization
workaround, not a proven correction of the underlying clock discrepancy.

Practice without practice-music sync, platformer, audio-trigger levels, altered
pitch, pause, death and end animations are excluded. Restarts and external song-position changes establish a
fresh baseline. The setting **Auto Music Sync** controls the feature.

Target: Geode 5.11.2, Geometry Dash 2.208 (iOS SDK version 2.2081), LiveContainer.
Built and tested in CI; real-device audio behavior still needs verification.
