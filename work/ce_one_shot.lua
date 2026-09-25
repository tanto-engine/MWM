error('Disabled: this debugger method crashed Nioh. Use external read-only research instead.')
assert(getOpenedProcessID()==9516, 'Wrong process')
if _freshNiohProbeTimer then _freshNiohProbeTimer.destroy(); _freshNiohProbeTimer=nil end
if _freshNiohProbe and _freshNiohProbe.site then pcall(debug_removeBreakpoint,_freshNiohProbe.site) end
assert(getSettingsForm().CheckBox1.Checked==false, 'Debugger-detection patching must be off')
local base=getAddress('nioh.exe')
local site=base+0x711C16 -- observed instruction: mov [rbx+58],rdi
local check=assert(readBytes(site,4,true))
assert(check[1]==0x48 and check[2]==0x89 and check[3]==0x7B and check[4]==0x58,'Changed code')
_freshNiohProbe={site=site, armed=false, done=false}
if not debug_isDebugging() then debugProcess(1) end
assert(debug_isDebugging() and debug_getCurrentDebuggerInterface()==1,'Windows debugger did not attach')
assert(#debug_getBreakpointList()==0, 'Unexpected existing breakpoint')
local function bytes(address,count)
  if not address or address==0 then return nil end
  local r=readBytes(address,count,true)
  if not r or #r~=count then return nil end
  return r
end
debug_setBreakpoint(site,1,bptExecute,bpmDebugRegister,function()
  if not _freshNiohProbe.done then
    _freshNiohProbe.done=true
    local ok,err=pcall(function()
      local p=_freshNiohProbe
      p.rbx=RBX; p.rdi=RDI; p.rsi=RSI; p.r15=R15; p.rip=RIP
      p.previous=readQword(RBX+0x58)
      p.owner=readQword(RBX+0x50)
      p.object_bytes=bytes(RBX,0x110)
      p.previous_bytes=bytes(p.previous,0xD0)
      p.new_bytes=bytes(RDI,0xD0)
      p.payload_bytes=bytes(RSI,0x80)
    end)
    _freshNiohProbe.read_ok=ok
    _freshNiohProbe.error=ok and '' or tostring(err)
    pcall(debug_removeBreakpoint,site)
  end
  pcall(debug_continueFromBreakpoint,co_run)
  return 0
end)
_freshNiohProbe.armed=true
_freshNiohProbeTimer=createTimer(nil,false)
_freshNiohProbeTimer.Interval=60000
_freshNiohProbeTimer.OnTimer=function(t)
  t.Enabled=false
  pcall(debug_removeBreakpoint,site)
  _freshNiohProbe.expired=true
end
_freshNiohProbeTimer.Enabled=true
return 1
