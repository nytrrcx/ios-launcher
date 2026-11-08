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
    // Observe the first callback for diagnostics only. startMainLoop now sets
    // both the display-link rate and the director interval natively, before any
    // frames run. Overriding just the link here left the engine at 1/60 second.
    if ([sender isKindOfClass:CADisplayLink.class]) {
        CADisplayLink *link = sender;
        if (lastGameLink != link) {
            lastGameLink = link;
            if (@available(iOS 15.0, *)) {
                CAFrameRateRange range = link.preferredFrameRateRange;
                AppLog(@"[ProMotion] Native game clock: display link %.0f–%.0f Hz (preferred %.0f).",
                       range.minimum, range.maximum, range.preferred);
            } else {
                AppLog(@"[ProMotion] Native game clock: display link %ld Hz.", (long)link.preferredFramesPerSecond);
            }
            [LogUtils flush];
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
    AppLog(@"[ProMotion] Native game timing configured; callback observer installed (CCDirectorCaller doCaller:).");
    [LogUtils flush];
    return YES;
}
