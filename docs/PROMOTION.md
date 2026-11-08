# Experimental ProMotion for LiveContainer

This branch requests up to 120 Hz through ANGLE/Metal and fixes the missing default
stencil attachment in ANGLEGLKit. Target device for testing: iPhone 17, iOS 26.5.1,
LiveContainer. iOS retains authority over the actual refresh rate. Device testing
and visual verification on an iPhone are still required.

## Build with GitHub Actions

The `ProMotion IPA` workflow in `.github/workflows/promotion.yml` runs when this
branch is pushed. It installs Theos and the iOS 16.5 SDK, runs host regression tests,
builds the patched renderer from the pinned `vendor/ANGLEGLKit` submodule, packages
an IPA, verifies its contents, and uploads `Geode-ProMotion-LiveContainer`.

The artifact contains an IPA and `promotion-build.json` with the source revisions
and IPA SHA-256. It does not contain Geometry Dash. A personal signing certificate
is not needed for the Actions build: LiveContainer signs the imported application.
Follow the upstream certificate/JIT-less setup guide on your device.

The optional repository secrets `GD_DOWNLOAD`, `KEYONE`, and `KEYTWO` configure
upstream's game download feature. They are not needed to compile the launcher.
Without them, use an existing game installation in the launcher's private data or
its manual IPA import with your own game copy. These secrets are not logged.

Local build, with Theos and an iOS SDK installed:

```
git submodule update --init --recursive
python3 scripts/patch_angle_stencil.py vendor/ANGLEGLKit
python3 scripts/patch_angle_loader.py vendor/ANGLEGLKit
make -C vendor/ANGLEGLKit stage FINALPACKAGE=1 STRIP=0 TARGET=iphone:clang:16.5:15.0
mkdir -p /tmp/promotion-frameworks
cp -R Resources/GDFrameworks/libEGL.framework Resources/GDFrameworks/libGLESv2.framework /tmp/promotion-frameworks/
python3 scripts/collect_angle.py vendor/ANGLEGLKit/.theos /tmp/promotion-frameworks
make package FINALPACKAGE=1 STRIP=0 PROMOTION_FRAMEWORKS_DIR=/tmp/promotion-frameworks
```

ProMotion requires iOS 15 or later. Do not substitute the old prebuilt wrapper
from `Resources/GDFrameworks`: the runtime checks the corrected wrapper's version.

## Install and enable

1. Download the Actions artifact, unzip it and import the IPA into LiveContainer.
   Update the existing Geode entry to retain its private game/mod data; keep a backup.
2. Keep **Don't Inject TweakLoader** and **Don't Load TweakLoader** enabled in
   LiveContainer's settings for Geode, as required by the upstream guide.
3. In Geode's Advanced settings enable **ProMotion 120 Hz (Experimental)**, then Launch.
4. To restore OpenGLES, disable the switch and Launch again.

Disable Low Power Mode and Accessibility > Motion > Limit Frame Rate for testing.
The host LiveContainer must opt in using `CADisableMinimumFrameDurationOnPhone`;
current upstream does. This branch does not modify the host LiveContainer.

After installing or updating mods, return to the launcher and launch again so the
new extracted binaries are configured and signed. Hot-loading a newly downloaded
OpenGLES mod into an already running ANGLE session is not covered by this change.

## Graphics correction

ANGLEGLKit originally created the drawable with `StencilNone`, while Geode's
`CCClippingNode` caches `GL_STENCIL_BITS` during its first initialization. A zero
result sends it through a limited rectangular scissor fallback, which cannot
represent arbitrary or inverted masks accurately.

`scripts/patch_angle_stencil.py` changes the drawable defaults to depth 24/stencil 8
and asks for the same depth/stencil configuration when creating the EGL context.
The existing renderer then creates a real stencil attachment. No GL bit-count
queries are fabricated and no mask is replaced by its bounding rectangle. When
renderbuffer storage is initialized with the default framebuffer bound, the wrapper
checks the actual stencil bit count and reports failure if fewer than 8 bits exist.
The exported `GCGeodeStencilFixVersion` marker prevents accidentally loading an old
unfixed wrapper. The actual rendering result must still be checked on the device.

## Launcher integration

The launcher rewrites renderer imports in GeometryJump, Geode, and extracted mod
dylibs before signing. Both `unzipped/<id>` and `unzipped/binaries` are supported.
Absolute private-bundle paths avoid LiveContainer host `@executable_path` ambiguity.
The bounded Mach-O editor preserves ordinals, segments and code offsets, rejects
insufficient header padding, and writes changed files atomically before signing.
Disabling restores OpenGLES imports and retains unused frameworks to make retries
safe. After the game loads, the launcher installs timing on Cocos's
`CCDirectorCaller doCaller:` callback. The callback configures only the game
display link using its public frame-rate property and requests an 80–120 Hz
range. Pause, invalidation, UIKit display links, and private Core Animation
classes are left to their original implementations.

## Validation and device checks

```
python3 -m unittest discover -s tests -v
```

32 host tests cover the source corrections, Mach-O enable/disable, repeated setup,
container relocation, FAT32/FAT64, payload preservation, insufficient header space,
and malformed inputs. A separate macOS job exercises the actual timing code with
Apple's Objective-C runtime and simulated public UIKit properties. It checks
original callback dispatch, ABI validation, 120/90/60 Hz, repeated installation,
display-link recreation, pause/invalidation, and object lifetime. It does not
exercise real Core Animation presentation. Handler-storage tests cover the 2.208 and 2.2091 layouts,
missing/readonly/truncated sections and aligned offsets. The rewrite was also exercised on real bundled framework
binaries and the released Geode 5.11.2 iOS library, including rollback. Earlier
50,000 ASan/UBSan mutations and static C analysis passed.

On the iPhone verify actual presentations with Instruments or a Metal HUD, rather
than only a game's FPS counter. Check menus, gameplay, Geode scrolling/popups,
arbitrary/inverted/nested masks, mod updates and restart, pause/background/foreground,
tapping during gameplay, low power settings, and reverting to OpenGLES. Passing CI
validates compilation/packaging, not visual compatibility or sustained 120 FPS.

Sources:
- https://github.com/geode-sdk/ios-launcher/issues/40
- https://github.com/geode-sdk/geode/pull/1556
- https://github.com/khanhduytran0/ANGLEGLKit
- https://github.com/geode-sdk/ios-launcher/blob/main/LIVECONTAINER-INSTALL-GUIDE.md
- https://github.com/geode-sdk/geode/blob/main/loader/include/Geode/cocos/platform/ios/CCDirectorCaller.mm

## JIT-less launch compatibility

The original feature build inherited upstream commit d8b3a39, which changed the
fixed handler storage address to `0xa4c000` for Geometry Dash 2.2091. Geometry Dash
2.208 instead has its injected handler at `0x8b4000` and writable storage at
`0x8c4000`; using the newer constant can crash while loading Geode even with
ProMotion disabled.

Both patch generation and launch arguments now derive the storage offset from
`__STORAGE,__storage` relative to `__TEXT` in the actual game file. No game-version
address constant is used. The patch cache revision is bumped so the first Launch
after upgrading rebuilds the old trampoline. Renderer switches no longer reset
the independent hook cache. A missing or invalid writable storage section stops
launch with an error rather than guessing an address. The phone report identified
the incompatible layout; the subsequent phone test confirmed that launching with
ProMotion disabled works with this correction.

## ProMotion startup and EGL dispatch

The follow-up phone test still stopped before the game binary finished loading
with ProMotion enabled. The previous log message covered three separate loads,
so it did not identify which library failed.

The bundled libEGL dynamically searches for libGLESv2 under the main executable's
Frameworks directory. In LiveContainer that directory can belong to the host or
launcher rather than the nested game. Loading another copy also separates EGL
and GL thread-local context state. The renderer now links its EGL calls directly
to the `EGL_*` exports of the same libGLESv2 that provides GL. The framebuffer
generation shims likewise call `GL_GenFramebuffers` and `GL_GenRenderbuffers`
directly instead of resolving `RTLD_NEXT` in a process containing other renderers.
Host tests check these exports against the actual bundled backend, and IPA
verification rejects a wrapper that still depends on libEGL or native OpenGLES.

Bootstrap logs distinguish libGLESv2, ANGLEGLKit, timing, and the game;
each stage is flushed before loading. Loader errors and uncaught Objective-C
exceptions are also written to the launcher's fixed log path. These changes
address startup hazards found in the implementation; the precise phone crash
cause and successful 120 Hz presentation still require a device retest.

## Timing preload crash

The 198860b phone log confirmed that libGLESv2 and the corrected renderer both
loaded successfully, then stopped during the separate CAHighFPS preload. The
game had not loaded yet. The log identifies that stage but does not distinguish
dyld failure from execution of the timing constructor.

CAHighFPS is no longer packaged or loaded. Timing is compiled into the launcher,
installed explicitly after the game finishes loading, and applied when Cocos
calls `doCaller:` with its CADisplayLink. It has no load-time constructor, TLS,
generated block IMP, or hooks on Core Animation classes. Legacy CAHighFPS entries
in the tweak folder are skipped. The IPA verifier rejects packages containing
CAHighFPS and checks for the built-in timing implementation. The next phone test
must confirm successful launch and actual frame presentation.

## Direct GL exports and game import coverage

The next phone report passed game loading and timing installation, then stopped
inside Cocos's framebuffer creation before the first display-link callback. The
exported GeometryJump identified the last call as `glBindFramebuffer` at 0x3fcf84
(return address 0x3fcf88). All SHA-1 and SHA-256 code-page hashes in the supplied
file matched. The report's Invalid Page termination therefore does not by itself
establish that the executable on disk has damaged code pages.

The game imports 79 symbols from its renderer dependency. Two Apple MSAA functions
were absent from the bundled backend. ANGLEGLKit now defines its public GL API
with compiled arm64 tail branches to the backend's `GL_*` functions; it no longer
depends on transitive GL re-exports. The first default framebuffer/renderbuffer
allocation keeps the wrapper's existing special handling. Apple MSAA allocation
forwards to ANGLE's allocation, and backbuffer resolve blits the current read
framebuffer into the current window draw framebuffer at the EGL surface size.

Only the 79 imported symbol names are recorded as regression metadata; the
user-supplied game binaries are not part of the repository or Actions artifacts.
The package check requires direct definitions for every one of those imports.
A macOS dyld test exercises the generated arm64 bridges, including integer,
floating-point, pointer and stack arguments, return values, and both Apple MSAA
compatibility functions. ProMotion launches bind the game eagerly to surface
unresolved imports before entering game main. Another device test is required to
confirm whether this fixes the reported framebuffer crash.
