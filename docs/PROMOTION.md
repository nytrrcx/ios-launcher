# Experimental ProMotion support for LiveContainer

This patch completes the launcher's dormant ANGLE integration. It requests up to
120 Hz; actual display timing remains controlled by iOS. It has **not** been built
with an Apple SDK or tested on an iPhone. It is a development patch, not a verified
IPA release. Target device for device testing: iPhone 17, iOS 26.5.1, LiveContainer.

## Build

Use a full checkout of https://github.com/geode-sdk/ios-launcher with its submodules
and the Theos/iOS toolchain described in the upstream README. Apply `ProMotion.patch`
to that checkout (`git apply --check` first). The working directory supplied with
this patch contains only the relevant upstream files retrieved through web access;
it is not a complete checkout. Direct git/network access was unavailable when this
patch was prepared, and the web snapshots were not pinned to a common commit.
Review/adapt any context differences against the checkout you build.

Provide matching **iOS device arm64** builds of these three frameworks:

```
/path/to/frameworks/ANGLEGLKit.framework/ANGLEGLKit
/path/to/frameworks/libEGL.framework/libEGL
/path/to/frameworks/libGLESv2.framework/libGLESv2
```

ANGLEGLKit upstream: https://github.com/khanhduytran0/ANGLEGLKit
Its README describes building ANGLE or obtaining the precompiled dependencies.
Keep upstream license notices with the frameworks. Simulator frameworks are not
suitable. No third-party binary frameworks are included in this patch.

```
make package FINALPACKAGE=1 STRIP=0 PROMOTION_FRAMEWORKS_DIR=/path/to/frameworks
```

The staging hook checks that all three framework executables exist, then copies
them into `Geode.app/Frameworks`. The installer/LiveContainer must sign embedded
frameworks when importing the resulting IPA. Without these dependencies, the
ProMotion switch is disabled and "About ProMotion 120 Hz" identifies what is missing.
The ordinary launcher build remains possible without the optional frameworks.

## Enable in LiveContainer

1. Import the rebuilt IPA as Geode. Follow the upstream LiveContainer guide for
   certificate/JIT-less setup (or JIT). Keep **Don't Inject TweakLoader** and
   **Don't Load TweakLoader** enabled in LiveContainer's settings for Geode.
2. Open Geode's Advanced settings and enable **ProMotion 120 Hz (Experimental)**.
3. Launch the game. Renderer preparation happens before signing, and the timing
   library loads directly before the game binary. LiveContainer's own TweakLoader
   is not required.
4. To restore OpenGLES, disable the option and launch again. The installed game
   and extracted mod dependencies are rewritten back to OpenGLES before signing.

Low Power Mode, Accessibility > Motion > Limit Frame Rate, and thermal policy can
reduce the delivered rate. The host LiveContainer must opt into ProMotion with
`CADisableMinimumFrameDurationOnPhone = true`; current upstream includes that key.
The patch does not modify or re-sign LiveContainer itself.

After installing/updating mods in the game, return to the launcher and launch again
so extracted binaries can be configured and signed. Hot-loading newly downloaded
OpenGLES mods into an already running ANGLE session is not covered by this patch.

## Implementation

- Detect refresh-rate capability through `UIScreen.maximumFramesPerSecond`, with
  no device-name allowlist that would exclude a non-Pro iPhone 17.
- Copy the renderer dependencies into the private game bundle and rewrite imports
  in GeometryJump, Geode, and extracted mod dylibs in both supported directory
  layouts (`unzipped/<id>` and `unzipped/binaries`). Rewrite ANGLE's own framework
  dependencies too. Absolute bundle paths avoid LiveContainer's host executable
  being used to resolve `@executable_path`; paths are refreshed on later launches.
- Use bounded Mach-O command rewriting, retaining load command order, dependency
  ordinals, file types, segment offsets and code bytes. Insufficient header padding
  stops launch with an error rather than overwriting a section. Atomic writes
  replace previously signed inodes; the existing signing pipeline runs afterwards.
- Retain renderer frameworks when disabled, so a failed/retried transition cannot
  leave partially restored files referring to deleted dependencies.
- Set the game's ProMotion plist keys. The display-link hook requests an 80–120 Hz
  range on supported screens without overriding `isPaused`, `setPaused:` or private
  Core Animation classes. The system retains authority over actual timing.
- Newly changed binaries trigger signing. Failures stop launch and remain retryable.

## Verification and remaining device work

Host tests:

```
python3 -m unittest discover -s tests -v
```

15 tests pass, including enable/disable, idempotence, container relocation,
weak/reexport imports, FAT32/FAT64, payload preservation, header space exhaustion
and malformed input. The C helper compiles with `-Wall -Wextra -Werror` and GCC static analysis on Linux.
A further 50,000 deterministic mutated inputs pass AddressSanitizer/UBSan
(leak detection disabled because this sandbox uses ptrace). The staging hooks were
checked with fixture frameworks, including an input directory containing spaces
and a missing dependency; this is not a check of IPA signing.
These tests do not validate Objective-C/Logos compilation, code signing, or rendering.

Before treating this as release-ready, build with Theos and test on the target device:

- Verify Metal rendering and **actual presentations**, e.g. with Instruments/Metal
  HUD, rather than relying solely on a game's FPS counter. Check menu and gameplay.
- Test JIT-less signatures and a second cold launch with no settings changes.
- Test both mod directory layouts and installing/updating a mod followed by restart.
- Check Geode lists, popups, scrolling/clipping and representative mods. The stencil
  and CCClippingNode issue documented in upstream issue #40 is **not resolved by
  this launcher patch**; use a Geode build with its applicable clipping fallback,
  and validate it visually. Graphics compatibility remains experimental.
- Test background/foreground and pause/resume, tapping while playing, Low Power
  Mode, Limit Frame Rate, disabling the feature, and reinstall/container relocation.

References:
- https://github.com/geode-sdk/ios-launcher/issues/40
- https://github.com/geode-sdk/ios-launcher/blob/main/LIVECONTAINER-INSTALL-GUIDE.md
- https://github.com/LiveContainer/LiveContainer/blob/main/LiveContainer/Info.plist
- https://developer.apple.com/documentation/quartzcore/optimizing-iphone-and-ipad-apps-to-support-promotion-displays
