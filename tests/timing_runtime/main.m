// Exercise the launcher's actual timing implementation with Apple's Objective-C
// runtime and simulated public display-link properties. No UIKit host is needed.
#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <objc/message.h>
#import <objc/runtime.h>
#import <dispatch/dispatch.h>
#import "ProMotionTiming.h"
#import "components/LogUtils.h"
#include <stdio.h>
#include <stdlib.h>
#include <math.h>

@implementation UIScreen
+ (UIScreen *)mainScreen {
    static UIScreen *screen;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ screen = [UIScreen new]; });
    return screen;
}
@end

@implementation CADisplayLink
@synthesize preferredFrameRateRange = _preferredFrameRateRange;
- (void)setPreferredFrameRateRange:(CAFrameRateRange)value {
    _preferredFrameRateRange = value;
    self.rangeWrites++;
}
@end

@implementation LogUtils
+ (void)log:(NSString *)format, ... {}
+ (void)logWithLevel:(LogLevel)level log:(NSString *)format, ... {}
+ (void)clearLogs:(BOOL)force {}
+ (void)flush {}
@end

static NSUInteger draws;
static double lastTimestamp, elapsed;
static void nativeCallback(id caller, SEL command, id sender) {
    draws++;
    if ([sender isKindOfClass:CADisplayLink.class]) {
        // The real game's doCaller: uses the display link's measured timestamp,
        // converted to float dt. Check that the observer passes it through.
        double timestamp = ((CADisplayLink *)sender).timestamp;
        if (lastTimestamp > 0) elapsed += (float)(timestamp - lastTimestamp);
        lastTimestamp = timestamp;
    }
}

static void check(BOOL result, NSString *description) {
    if (!result) {
        fprintf(stderr, "FAIL: %s\n", description.UTF8String);
        exit(1);
    }
}

static void tick(id caller, id sender) {
    ((void (*)(id, SEL, id))objc_msgSend)(caller, sel_registerName("doCaller:"), sender);
}

static void checkRange(CADisplayLink *link, float low, float high) {
    CAFrameRateRange range = link.preferredFrameRateRange;
    check(range.minimum == low && range.maximum == high && range.preferred == high,
          @"requested display-link range");
}

static void checkLongRun(id caller, CADisplayLink *link, NSInteger fps, BOOL variable) {
    link.preferredFrameRateRange = (CAFrameRateRange){fps, fps, fps};
    NSUInteger writes = link.rangeWrites, before = draws;
    double timestamp = 100, start = timestamp;
    elapsed = 0;
    lastTimestamp = 0;
    link.timestamp = timestamp;
    tick(caller, link);
    // Twenty minutes at the requested cadence, plus missed/late presentations.
    NSUInteger frames = fps * 20 * 60;
    for (NSUInteger frame = 0; frame < frames; ++frame) {
        double delta = 1.0 / fps;
        if (variable && frame % 97 == 0) delta *= 2;
        timestamp += delta;
        link.timestamp = timestamp;
        tick(caller, link);
    }
    check(draws - before == frames + 1, @"every presentation calls the original exactly once");
    check(fabs(elapsed - (timestamp - start)) < .001, @"twenty-minute timestamp clock has under 1 ms drift");
    check(link.timestamp == timestamp && link.rangeWrites == writes, @"observer never changes timestamp or cadence");
    checkRange(link, fps, fps);
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        NSString *error = nil;
        // Missing game class must report an error, never guess an ABI or crash.
        check(!GCInstallGameProMotionTiming(&error) && error.length > 0, @"missing class is rejected");
        Class callerClass = objc_allocateClassPair(NSObject.class, "CCDirectorCaller", 0);
        BOOL wrongSignature = argc > 1;
        class_addMethod(callerClass, sel_registerName("doCaller:"), (IMP)nativeCallback,
                        wrongSignature ? "i@:@" : "v@:@");
        objc_registerClassPair(callerClass);
        Method callback = class_getInstanceMethod(callerClass, sel_registerName("doCaller:"));
        if (wrongSignature) {
            error = nil;
            check(!GCInstallGameProMotionTiming(&error) && error.length > 0, @"invalid ABI is rejected");
            check(method_getImplementation(callback) == (IMP)nativeCallback, @"invalid callback is unchanged");
            puts("PASS: invalid callback signature");
            return 0;
        }
        check(GCInstallGameProMotionTiming(&error), @"game timing installs");
        IMP installed = method_getImplementation(callback);
        check(installed != (IMP)nativeCallback, @"game callback observer is installed");
        check(GCInstallGameProMotionTiming(&error), @"repeated setup succeeds");
        check(method_getImplementation(callback) == installed, @"repeated setup is idempotent");
        id caller = [callerClass new];
        CADisplayLink *link = [CADisplayLink new];
        UIScreen.mainScreen.maximumFramesPerSecond = 120;
        link.preferredFrameRateRange = (CAFrameRateRange){120, 120, 120};
        link.paused = YES;
        link.invalidated = YES;
        tick(caller, link);
        check(draws == 1 && link.rangeWrites == 1, @"first frame observes timing and calls original once");
        checkRange(link, 120, 120);
        check(link.paused && link.invalidated, @"pause and invalidation are preserved");
        tick(caller, link);
        check(draws == 2 && link.rangeWrites == 1, @"unchanged timing is not rewritten");
        // An unrelated link is never changed merely because it exists.
        CADisplayLink *other = [CADisplayLink new];
        check(other.rangeWrites == 0, @"host display links are untouched");
        tick(caller, [NSObject new]);
        tick(caller, nil);
        check(draws == 4, @"non-display-link senders still call original");
        UIScreen.mainScreen.maximumFramesPerSecond = 90;
        link.preferredFrameRateRange = (CAFrameRateRange){90, 90, 90};
        tick(caller, link);
        checkRange(link, 90, 90);
        UIScreen.mainScreen.maximumFramesPerSecond = 60;
        link.preferredFrameRateRange = (CAFrameRateRange){60, 60, 60};
        tick(caller, link);
        checkRange(link, 60, 60);
        UIScreen.mainScreen.maximumFramesPerSecond = 120;
        link.preferredFrameRateRange = (CAFrameRateRange){30, 60, 60};
        tick(caller, link);
        checkRange(link, 30, 60);
        __weak CADisplayLink *releasedLink;
        @autoreleasepool {
            CADisplayLink *recreated = [CADisplayLink new];
            recreated.preferredFrameRateRange = (CAFrameRateRange){120, 120, 120};
            tick(caller, recreated);
            checkRange(recreated, 120, 120);
            releasedLink = recreated;
        }
        check(!releasedLink, @"timing does not retain an invalidated game display link");
        for (NSInteger fps = 60; fps <= 120; fps += 30) {
            checkLongRun(caller, link, fps, NO);
            checkLongRun(caller, link, fps, YES);
        }
        puts("PASS: twenty-minute 120/90/60 Hz clocks, late frames, callback, restart, pause, and lifetime");
    }
    return 0;
}
