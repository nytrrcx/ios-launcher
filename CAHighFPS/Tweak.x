// Request ProMotion timing without interfering with pause/background lifecycle.
%config(generator = internal);
#import <UIKit/UIKit.h>
#import <QuartzCore/QuartzCore.h>
#include <stdlib.h>
#include <string.h>

static NSInteger requestedFPS(void) {
    return MIN(120, MAX(1, UIScreen.mainScreen.maximumFramesPerSecond));
}

static _Thread_local BOOL applyingRate;

static void applyGameRate(CADisplayLink *link) {
    if (applyingRate) return;
    applyingRate = YES;
    @try {
        if (@available(iOS 15.0, *)) {
            float fps = (float)requestedFPS();
            link.preferredFrameRateRange = CAFrameRateRangeMake(MIN(80.0f, fps), fps, fps);
        } else {
            link.preferredFramesPerSecond = requestedFPS();
        }
    } @finally {
        applyingRate = NO;
    }
}

%group ProMotionTiming
%hook CADisplayLink
- (void)addToRunLoop:(NSRunLoop*)runLoop forMode:(NSRunLoopMode)mode {
    // Configure even clients that never call a frame-rate setter (Cocos defaults).
    applyGameRate(self);
    %orig;
}
- (void)setPreferredFrameRateRange:(CAFrameRateRange)range {
    if (applyingRate) { %orig(range); return; }
    applyGameRate(self);
}
- (void)setPreferredFramesPerSecond:(NSInteger)fps {
    if (applyingRate) { %orig(fps); return; }
    applyGameRate(self);
}
- (void)setFrameInterval:(NSInteger)interval {
    if (applyingRate) { %orig(interval); return; }
    // One native setter per update: legacy setters can call each other on newer iOS.
    applyGameRate(self);
}
%end
%end

%ctor {
    const char *enabled = getenv("ANGLEGLKit");
    if (enabled && !strcmp(enabled, "1") && UIScreen.mainScreen.maximumFramesPerSecond > 60) {
        %init(ProMotionTiming);
    }
}
