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
make -C vendor/ANGLEGLKit stage FINALPACKAGE=1 STRIP=0 TARGET=iphone:clang:16.5:15.0
mkdir -p /tmp/promotion-frameworks
cp -R Resources/GDFrameworks/libEGL.framework Resources/GDFrameworks/libGLESv2.framework /tmp/promotion-frameworks/
python3 scripts/collect_angle.py vendor/ANGLEGLKit/.theos /tmp/promotion-frameworks
make package FINALPACKAGE=1 STRIP=0 PROMOTION_FRAMEWORKS_DIR=/tmp/promotion-frameworks
```

Do not force an iOS 14 deployment target on all subprojects: the timing library
uses the iOS 15 `CAFrameRateRange` API. Do not substitute the old prebuilt wrapper
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
safe. The display-link hook requests an 80–120 Hz range without overriding pause
or private Core Animation classes. It loads directly before the game.

## Validation and device checks

```
python3 -m unittest discover -s tests -v
```

18 host tests cover the source correction, Mach-O enable/disable, repeated setup,
container relocation, FAT32/FAT64, payload preservation, insufficient header space,
and malformed inputs. The rewrite was also exercised on real bundled framework
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
