local notes={}
local function note(s) notes[#notes+1]=s end
if _freshNiohProbe then _freshNiohProbe.done=true end
if _freshNiohProbeTimer then
  local t=_freshNiohProbeTimer
  pcall(function() t.Enabled=false end)
  local ok,err=pcall(function() t.destroy() end)
  note('timer_destroy='..tostring(ok)..' '..tostring(err))
  _freshNiohProbeTimer=nil
end
local pid=getOpenedProcessID()
note('ce_target_pid='..tostring(pid))
if pid==9516 then
  if debug_isDebugging() then
    if _freshNiohProbe and _freshNiohProbe.site then pcall(debug_removeBreakpoint,_freshNiohProbe.site) end
    local ok,err=pcall(detachIfPossible)
    note('detach_call='..tostring(ok)..' '..tostring(err))
  end
else
  note('Unexpected PID: no debugger operation performed')
end
note('debugging='..tostring(debug_isDebugging()))
local f=assert(io.open(assert(os.getenv('NIOH_RESEARCH_DIR'), 'Set NIOH_RESEARCH_DIR to the repo work folder') .. '\\ce-cleanup.txt','w'))
f:write(table.concat(notes,'\n')); f:close()
return debug_isDebugging() and 0 or 1
