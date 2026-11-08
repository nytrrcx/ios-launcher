#import "ProMotionTiming.h"
#import "components/LogUtils.h"
#import <UIKit/UIKit.h>
#import <QuartzCore/QuartzCore.h>
#include <objc/runtime.h>
#include <stdlib.h>
#include <string.h>

static void (*originalDoCaller)(id, SEL, id);
static __weak CADisplayLink *lastGameLink;

static void gameDoCaller(id caller, SEL selector, id sender) {
    // Cocos passes its display link as the sender of doCaller:. UIKit's own
    // display links and pause/background methods are never hooked.
    if ([sender isKindOfClass:CADisplayLink.class]) {
        CADisplayLink *link = sender;
        NSInteger fps = MIN(120, UIScreen.mainScreen.maximumFramesPerSecond);
        if (fps > 0) {
            if (@available(iOS 15.0, *)) {
                CAFrameRateRange current = link.preferredFrameRateRange;
                float minimum = MIN(80, fps);
                if (current.minimum != minimum || current.maximum != fps || current.preferred != fps) {
                    // A struct literal avoids introducing a dependency on the
                    // newer CAFrameRateRangeMake C function in the launcher.
                    link.preferredFrameRateRange = (CAFrameRateRange){minimum, (float)fps, (float)fps};
                }
            } else if (link.preferredFramesPerSecond != fps) {
                link.preferredFramesPerSecond = fps;
            }
            if (lastGameLink != link) {
                lastGameLink = link;
                AppLog(@"[ProMotion] Game display link requested %ld Hz.", (long)fps);
                [LogUtils flush];
            }
        }
    }
    originalDoCaller(caller, selector, sender);
}

BOOL GCInstallGameProMotionTiming(NSString **error) {
    if (originalDoCaller) return YES;
    Class caller = NSClassFromString(@"CCDirectorCaller");
    Method callback = class_getInstanceMethod(caller, NSSelectorFromString(@"doCaller:"));
    char *resultType = callback ? method_copyReturnType(callback) : NULL;
    char *senderType = callback && method_getNumberOfArguments(callback) == 3
        ? method_copyArgumentType(callback, 2) : NULL;
    BOOL supported = callback && resultType && !strcmp(resultType, "v") && senderType && senderType[0] == '@';
    free(resultType);
    free(senderType);
    if (!supported || !method_getImplementation(callback)) {
        if (error) *error = @"Cannot find the game's display-link callback. Disable ProMotion and send app.log with your Geometry Dash version.";
        return NO;
    }
    // The callback belongs to the loaded game, not a private Core Animation class.
    // No dynamic-library constructor, runtime-generated IMP, or TLS is needed.
    originalDoCaller = (void (*)(id, SEL, id))method_getImplementation(callback);
    method_setImplementation(callback, (IMP)gameDoCaller);
    AppLog(@"[ProMotion] Game callback timing installed (CCDirectorCaller doCaller:).");
    [LogUtils flush];
    return YES;
}
