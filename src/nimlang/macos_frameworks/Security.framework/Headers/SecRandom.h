/* The part of macOS's Security/SecRandom.h that Nim's std/sysrand uses, so that
   code importing std/random cross-compiles for macOS without the macOS SDK.
   The symbols resolve at run time to the system's Security framework. */
#ifndef _SECURITY_SECRANDOM_H_
#define _SECURITY_SECRANDOM_H_
#include <stddef.h>

typedef const struct __SecRandom *SecRandomRef;
extern const SecRandomRef kSecRandomDefault;
int SecRandomCopyBytes(SecRandomRef rnd, size_t count, void *bytes);

#endif
