assert(not debug_isDebugging(), 'An existing debugger must be inspected before proceeding')
assert(getOpenedProcessID()==0 or getOpenedProcessID()==9516, 'CE is attached to a different process')
openProcess(9516)
assert(getOpenedProcessID()==9516, 'Wrong process')
local base=getAddress('nioh.exe')
local candidate=base+0x711b44
local expected={0x48,0x83,0x7B,0x58,0,0x74,0x10}
local bytes=assert(readBytes(candidate,7,true))
for i=1,7 do assert(bytes[i]==expected[i], 'Candidate bytes changed') end
local f=assert(io.open(assert(os.getenv('NIOH_RESEARCH_DIR'), 'Set NIOH_RESEARCH_DIR to the repo work folder') .. '\\candidate-disassembly.txt','w'))
local a=base+0x7119c0
while a<base+0x711d35 do
  f:write(disassemble(a),'\n')
  local n=getInstructionSize(a)
  assert(n and n>0 and n<=15, 'Disassembly failed')
  a=a+n
end
f:close()
return candidate
