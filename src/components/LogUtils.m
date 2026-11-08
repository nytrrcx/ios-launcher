#import "LogUtils.h"
#include "src/Utils.h"

static const NSUInteger MAX_LOG_FILE_SIZE = 1024 * 1024; // 1 MB
static dispatch_queue_t loggingQueue;
static char loggingQueueKey;

@implementation LogUtils

+ (void)initialize {
	static dispatch_once_t onceToken;
	dispatch_once(&onceToken, ^{
        loggingQueue = dispatch_queue_create("com.geode.logqueue", DISPATCH_QUEUE_SERIAL);
        dispatch_queue_set_specific(loggingQueue, &loggingQueueKey, &loggingQueueKey, NULL);
    });
}

+ (NSString*)logFilePath {
    // Resolve while still in the launcher. Guest hooks later change HOME/NSBundle.
    static NSString *path;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        NSString *documents = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
        if ([documents hasSuffix:@"GeometryDash/Documents"])
            documents = [documents stringByAppendingPathComponent:@"../../../.."];
        path = [[documents stringByAppendingPathComponent:@"app.log"] stringByStandardizingPath];
    });
    return path;
}

+ (void)log:(NSString*)format, ... {
	[LogUtils logWithLevel:LogUnk log:format];
}

+ (NSString*)logEnumToString:(LogLevel)level {
	switch (level) {
	default:
		return @"Unknown";
	case LogInfo:
		return @"Info";
	case LogWarn:
		return @"Warn";
	case LogError:
		return @"Error";
	case LogDebug:
		return @"Debug";
	}
}

+ (void)logWithLevel:(LogLevel)level log:(NSString*)format, ... {
	NSString* callSource = [[NSThread callStackSymbols] objectAtIndex:1];
	if (!callSource)
		callSource = @"[Unknown]";

	NSArray* parts = [callSource componentsSeparatedByCharactersInSet:[NSCharacterSet characterSetWithCharactersInString:@"[]"]];
	NSString* srcFunc = @"Unknown";

	if (parts.count > 1)
		srcFunc = [parts objectAtIndex:1];

	NSString* prefix;
	if (![[Utils getPrefs] boolForKey:@"LOG_LEVELS"]) {
		prefix = [NSString stringWithFormat:@"[GeodeLauncher/%@] ", [srcFunc substringToIndex:MIN([srcFunc rangeOfString:@" "].location, srcFunc.length)]];
	} else {
		prefix = [NSString
			stringWithFormat:@"[GeodeLauncher/%@] [%@] ", [srcFunc substringToIndex:MIN([srcFunc rangeOfString:@" "].location, srcFunc.length)], [LogUtils logEnumToString:level]];
	}
	format = [prefix stringByAppendingString:format];

	va_list args;
	va_start(args, format);
	NSString* message = [[NSString alloc] initWithFormat:format arguments:args];
	va_end(args);
	NSLog(@"%@", message);
	if (level == LogDebug) {
		if (![[Utils getPrefs] boolForKey:@"DEBUG_LOGS"])
			return;
	}
    // Capture the launcher path before dispatching and before the guest changes HOME.
    NSString *logPath = [self logFilePath];
	dispatch_async(loggingQueue, ^{
		[self checkLogFileSize];
		NSFileHandle* fileHandle = [NSFileHandle fileHandleForWritingAtPath:logPath];
		if (fileHandle) {
			[fileHandle seekToEndOfFile];
			[fileHandle writeData:[[message stringByAppendingString:@"\n"] dataUsingEncoding:NSUTF8StringEncoding]];
			[fileHandle closeFile];
		} else {
			[[message stringByAppendingString:@"\n"] writeToFile:logPath atomically:YES encoding:NSUTF8StringEncoding error:nil];
		}
	});
}

+ (void)flush {
    if (!dispatch_get_specific(&loggingQueueKey)) dispatch_sync(loggingQueue, ^{});
}

+ (void)checkLogFileSize {
	NSFileManager* fileManager = [NSFileManager defaultManager];
	NSString* logPath = [self logFilePath];

	if ([fileManager fileExistsAtPath:logPath]) {
		NSError* error = nil;
		NSDictionary* attrs = [fileManager attributesOfItemAtPath:logPath error:&error];
		if (!error && [attrs fileSize] > MAX_LOG_FILE_SIZE) {
			[@"" writeToFile:logPath atomically:YES encoding:NSUTF8StringEncoding error:nil];
		}
	}
}

+ (void)clearLogs:(BOOL)force {
	if ([[Utils getPrefs] integerForKey:@"LAUNCH_COUNT"] % 5 == 0 || force) {
		dispatch_sync(loggingQueue, ^{
			NSError* error = nil;
			[@"" writeToFile:[self logFilePath] atomically:YES encoding:NSUTF8StringEncoding error:&error];
		});
	}
}


@end
