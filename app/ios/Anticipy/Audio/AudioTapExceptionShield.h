#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// Swift cannot catch NSException. AVAudioNode uses one for tap installation
/// failures, so keep the Objective-C boundary as narrow as the single call.
@interface AudioTapExceptionShield : NSObject
+ (BOOL)perform:(NS_NOESCAPE void (^)(void))operation;
@end

NS_ASSUME_NONNULL_END
