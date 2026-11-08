# ProMotion Music Sync for iOS

This companion Geode mod seeks the main song to follow the level clock when a
persistent offset develops. It is intended to be tested with the working
ProMotion launcher and CBF enabled. It does not modify CBF, input timestamps,
physics steps, TPS, frame callbacks, or playback pitch.

Download `nytrrcx.promotion_music_sync.geode` from the **ProMotion Music Sync**
Actions artifact. Install it through Geode's local-mod import, or copy it into
the existing game's `game/geode/mods` directory. Launch through the launcher so
its normal JIT-less patch/sign pipeline can configure the newly installed mod.
Keep **Auto Music Sync** enabled in this mod's settings. A launcher IPA update
is not required if the working 7dc8be4 build is installed.

The source uses Geode 5.11.2 and pinned 2.2081 iOS bindings, matching the supplied
GD 2.208 game binary. Compile-time checks compare the native level-clock and
audio-map field locations with the supplied game's instructions. No game binary
is included in the source or artifact.

The pure clock policy is tested with twenty-minute sequences in both drift
directions, a nonzero song offset, asynchronous seeks, jitter, pauses, restarts,
manual seeks and changing frame cadence. CI compiles the real iOS binding calls
and verifies the arm64 mod package. These checks do not establish that the
reported desynchronization has been fixed on the user's device.

This is a workaround with deliberate limits: it skips platformer, audio-trigger
levels, altered pitch and practice without practice-music sync. A correction is
an audio seek and may be audible. The underlying source of the phone's clock
discrepancy remains unconfirmed.
