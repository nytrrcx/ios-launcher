// Request ProMotion timing without interfering with pause/background lifecycle.
%config(generator = internal);
#import <UIKit/UIKit.h>
#import <QuartzCore/QuartzCore.h>
#include <stdlib.h>
#include <string.h>

static NSInteger requestedFPS(void) {
    return MIN(120, MAX(1, UIScreen.mainScreen.maximumFramesPerSecond));
}

%group ProMotionTiming
%hook CADisplayLink
- (void)addToRunLoop:(NSRunLoop*)runLoop forMode:(NSRunLoopMode)mode {
    // Configure even clients that never call a frame-rate setter (Cocos defaults).
    if (@available(iOS 15.0, *)) {
        float fps = (float)requestedFPS();
        self.preferredFrameRateRange = CAFrameRateRangeMake(MIN(80.0f, fps), fps, fps);
    } else {
        self.preferredFramesPerSecond = requestedFPS();
    }
    %orig;
}
- (void)setPreferredFrameRateRange:(CAFrameRateRange)range {
    float fps = (float)requestedFPS();
    %orig(CAFrameRateRangeMake(MIN(80.0f, fps), fps, fps));
}
- (void)setPreferredFramesPerSecond:(NSInteger)fps {
    %orig(requestedFPS());
}
- (void)setFrameInterval:(NSInteger)interval {
    %orig(1);
    if (@available(iOS 15.0, *)) {
        float fps = (float)requestedFPS();
        self.preferredFrameRateRange = CAFrameRateRangeMake(MIN(80.0f, fps), fps, fps);
    } else {
        self.preferredFramesPerSecond = requestedFPS();
    }
}
%end
%end

%ctor {
    const char *enabled = getenv("ANGLEGLKit");
    if (enabled && !strcmp(enabled, "1") && UIScreen.mainScreen.maximumFramesPerSecond > 60) {
        %init(ProMotionTiming);
    }
}
