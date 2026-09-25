// Authoritative production runtime. Addresses arrive through the Start ABI;
// rebuilding this DLL for a mission or process is never required.
// The retained resource-loader module supplies action, timing, motion and camera
// packages; this entry shares observer, input, adaptation and recovery behavior.
// Baseline tap/release C64/1220 and hold0.25s C66/1230 remain separate from the
// configured held string. The native game alone selects contact-success361.
#define RESEARCH_RUNTIME_SESSION
#define RESEARCH_REPEAT
#define RESEARCH_BOSS
#define RESEARCH_DISPATCH
#include "observer.cpp"
