#import <Foundation/Foundation.h>

typedef NS_ENUM(NSInteger, LogLevel) { LogUnk, LogInfo, LogWarn, LogError, LogDebug };

@interface LogUtils : NSObject

+ (void)log:(NSString*)format, ...;
+ (void)logWithLevel:(LogLevel)level log:(NSString*)format, ...;
+ (void)clearLogs:(BOOL)force;
+ (void)flush;

@end

#define AppLogUnknown(x...) [NSClassFromString(@"LogUtils") log:x];
#define AppLog(x...) [NSClassFromString(@"LogUtils") logWithLevel:LogInfo log:x];
#define AppLogWarn(x...) [NSClassFromString(@"LogUtils") logWithLevel:LogWarn log:x];
#define AppLogError(x...) [NSClassFromString(@"LogUtils") logWithLevel:LogError log:x];
#define AppLogDebug(x...) [NSClassFromString(@"LogUtils") logWithLevel:LogDebug log:x];
