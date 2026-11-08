#import "ProMotion.h"
#import "PromotionMachO.h"
#import "Utils.h"
#import "LCUtils/Shared.h"

@implementation ProMotion
+ (NSArray<NSString*>*)frameworkNames {
    return @[@"ANGLEGLKit", @"libEGL", @"libGLESv2"];
}
+ (NSString*)unavailableReason {
    if (@available(iOS 15.0, *)) {} else return @"ProMotion mode requires iOS 15 or later.";
    if (![Utils isSandboxed] || [[Utils getPrefs] boolForKey:@"ENTERPRISE_MODE"])
        return @"ProMotion currently requires the sandboxed launcher (including LiveContainer).";
    if (UIScreen.mainScreen.maximumFramesPerSecond <= 60 && ![[Utils getPrefs] boolForKey:@"FORCE_ANGLE"])
        return @"A display supporting more than 60 Hz is required. Check Accessibility > Motion > Limit Frame Rate.";
    for (NSString *name in [self frameworkNames]) {
        NSString *path = [NSBundle.mainBundle.privateFrameworksPath stringByAppendingPathComponent:
                          [NSString stringWithFormat:@"%@.framework/%@", name, name]];
        if (![NSFileManager.defaultManager fileExistsAtPath:path])
            return [NSString stringWithFormat:@"This launcher build does not include %@.framework. Install a build containing the ANGLE frameworks.", name];
    }
    return nil;
}
+ (BOOL)fail:(NSError**)error message:(NSString*)message {
    if (error) *error = [NSError errorWithDomain:@"Geode.ProMotion" code:1 userInfo:@{NSLocalizedDescriptionKey: message}];
    return NO;
}
+ (BOOL)patchFile:(NSString*)path frameworks:(NSString*)frameworks enabled:(BOOL)enabled error:(NSError**)error {
    NSMutableData *data = [NSMutableData dataWithContentsOfFile:path options:0 error:error];
    if (!data) return NO;
    int result = GCPatchRenderer(data.mutableBytes, data.length, frameworks.UTF8String, enabled);
    if (result < 0) return [self fail:error message:[NSString stringWithFormat:
        @"Cannot configure renderer for %@ (%@). No changes were written to this file.", path.lastPathComponent,
        result == -2 ? @"insufficient Mach-O header space" : @"unsupported or malformed Mach-O"]];
    if (result == 0) return YES;
    // Atomic replacement avoids modifying a previously mapped, signed inode.
    if (![data writeToFile:path options:NSDataWritingAtomic error:error]) return NO;
    [[Utils getPrefs] setBool:YES forKey:@"PROMOTION_NEEDS_SIGN"];
    return YES;
}
+ (BOOL)prepare:(NSError**)error {
    NSUserDefaults *prefs = [Utils getPrefs];
    BOOL enabled = [prefs boolForKey:@"USE_MAX_FPS"];
    if (!enabled && ![prefs boolForKey:@"PROMOTION_ACTIVE"]) return YES;
    if (enabled) {
        NSString *reason = [self unavailableReason];
        if (reason) return [self fail:error message:reason];
    }
    NSFileManager *fm = NSFileManager.defaultManager;
    NSURL *bundle = [[LCPath bundlePath] URLByAppendingPathComponent:[Utils gdBundleName]];
    NSString *frameworks = [bundle URLByAppendingPathComponent:@"Frameworks"].path;
    NSString *executable = [bundle URLByAppendingPathComponent:@"GeometryJump"].path;
    if (![fm fileExistsAtPath:executable]) return [self fail:error message:@"Install Geometry Dash before configuring ProMotion."];
    if (enabled) {
        if (![fm createDirectoryAtPath:frameworks withIntermediateDirectories:YES attributes:nil error:error]) return NO;
        NSMutableString *sourceHash = [NSMutableString string];
        for (NSString *name in [self frameworkNames]) {
            NSString *binary = [NSBundle.mainBundle.privateFrameworksPath stringByAppendingPathComponent:
                               [NSString stringWithFormat:@"%@.framework/%@", name, name]];
            NSString *hash = [Utils sha256sum:binary];
            if (!hash) return [self fail:error message:@"Cannot read the bundled ANGLE frameworks."];
            [sourceHash appendString:hash];
        }
        BOOL update = ![[prefs stringForKey:@"PROMOTION_FRAMEWORKS_HASH"] isEqualToString:sourceHash];
        for (NSString *name in [self frameworkNames]) {
            NSString *directory = [name stringByAppendingString:@".framework"];
            NSString *destination = [frameworks stringByAppendingPathComponent:directory];
            if (update || ![fm fileExistsAtPath:[destination stringByAppendingPathComponent:name]]) {
                // Remember a pending transition before writing anything, so disabling can recover a partial attempt.
                [prefs setBool:YES forKey:@"PROMOTION_ACTIVE"];
                [prefs setBool:YES forKey:@"PROMOTION_NEEDS_SIGN"];
                if ([fm fileExistsAtPath:destination] && ![fm removeItemAtPath:destination error:error]) return NO;
                if (![fm copyItemAtPath:[NSBundle.mainBundle.privateFrameworksPath stringByAppendingPathComponent:directory]
                                toPath:destination error:error]) return NO;
            }
            // Absolute dependencies are intentional: @executable_path is LiveContainer's executable on some versions.
            if (![self patchFile:[destination stringByAppendingPathComponent:name] frameworks:frameworks enabled:YES error:error]) return NO;
        }
        [prefs setObject:sourceHash forKey:@"PROMOTION_FRAMEWORKS_HASH"];
    }
    [prefs setBool:YES forKey:@"PROMOTION_ACTIVE"];
    if (![self patchFile:executable frameworks:frameworks enabled:enabled error:error]) return NO;
    NSString *geode = [Utils getTweakDir];
    if (geode && [fm fileExistsAtPath:geode] && ![self patchFile:geode frameworks:frameworks enabled:enabled error:error]) return NO;
    NSURL *mods = [[LCPath dataPath] URLByAppendingPathComponent:@"game/geode/unzipped"];
    if ([fm fileExistsAtPath:mods.path]) {
        __block NSError *enumerationError = nil;
        NSDirectoryEnumerator *files = [fm enumeratorAtURL:mods includingPropertiesForKeys:@[NSURLIsRegularFileKey]
            options:NSDirectoryEnumerationSkipsHiddenFiles errorHandler:^BOOL(NSURL *url, NSError *failure) {
                enumerationError = failure;
                return NO;
            }];
        for (NSURL *file in files) {
            NSNumber *regular;
            if (![file getResourceValue:&regular forKey:NSURLIsRegularFileKey error:error]) return NO;
            if (regular.boolValue && [file.pathExtension isEqualToString:@"dylib"] &&
                ![self patchFile:file.path frameworks:frameworks enabled:enabled error:error]) return NO;
        }
        if (enumerationError) { if (error) *error = enumerationError; return NO; }
    }
    // Retain the frameworks when disabling: a failed/retried transition must not leave dangling dependencies.
    NSString *plistPath = [bundle URLByAppendingPathComponent:@"Info.plist"].path;
    NSMutableDictionary *plist = [NSMutableDictionary dictionaryWithContentsOfFile:plistPath];
    if (!plist) return [self fail:error message:@"Cannot read Geometry Dash's Info.plist."];
    if (enabled && (![plist[@"CADisableMinimumFrameDurationOnPhone"] boolValue] || ![plist[@"CADisableMinimumFrameDuration"] boolValue])) {
        plist[@"CADisableMinimumFrameDurationOnPhone"] = @YES;
        plist[@"CADisableMinimumFrameDuration"] = @YES;
        if (![plist writeToFile:plistPath atomically:YES]) return [self fail:error message:@"Cannot save the ProMotion Info.plist settings."];
        [prefs setBool:YES forKey:@"PROMOTION_NEEDS_SIGN"];
    }
    [prefs setBool:enabled forKey:@"PROMOTION_ACTIVE"];
    return YES;
}
@end
