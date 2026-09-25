// Parses a Python-published command from a file; never maps or patches a process.
#include <cassert>
#include <cstdio>
#include "../../runtime/native/dispatch_protocol.h"
int main(int argc, char** argv) {
    // Verify Python-published command bytes against the native ABI and time policy.
    // Read the supplied owned fixture and test generations, expiry and consumption.
    // Cross-language layout drift must fail before an external publisher reaches gameplay.
    assert(argc == 2);
    FILE* file = std::fopen(argv[1], "rb"); assert(file);
    DispatchCommand command{};
    assert(std::fread(&command, 1, sizeof(command), file) == sizeof(command));
    std::fclose(file);
    assert(command.sequence_begin == 1 && command.sequence_end == 1);
    assert(command.player == 0x100000 && command.owner == 0x200000);
    assert(command.banks[2] == 0x600000 && command.expected_descriptor == 0x700000);
    assert(command.desired_key == 0xCF0 && command.expected_motion == 4100);
    assert(command_status(command, 1050, 1000, 7, 0, false) == Accepted);
    assert(command_status(command, 1150, 1000, 7, 0, false) == StaleHeartbeat);
    assert(command_status(command, 2100, 1000, 7, 0, false) == Expired);
    assert(command_status(command, 1050, 1000, 8, 0, false) == WrongGeneration);
    assert(command_status(command, 1050, 1000, 7, 1, false) == SequenceConsumed);
    assert(command_status(command, 1050, 1000, 7, 0, true) == ShotUsed);
    command.reserved[2] = UINT16_MAX;
    assert(command_status(command, 1050, 1000, 7, 0, false) == Accepted);
    command.reserved[2] = uint64_t(UINT16_MAX) + 1;
    assert(command_status(command, 1050, 1000, 7, 0, false) == InvalidConfig);
    command.reserved[2] = 0;
    command.held = 0;
    assert(command_status(command, 1050, 1000, 7, 0, false) == Released);
    command.armed = 0;
    assert(command_status(command, 1050, 1000, 7, 0, false) == NotArmed);
    std::puts("Python publisher/native protocol checks passed");
}
