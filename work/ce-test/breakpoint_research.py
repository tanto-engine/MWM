import ctypes as C
from ctypes import wintypes as W
import importlib.util
from pathlib import Path
import re
import subprocess
import time

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("ce_client", HERE.parent / "ce_research_client.py")
CLIENT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLIENT)


def lua(code):
    # Execute research Lua with a traceback persisted by the local CE server.
    # Translate its reserved failure result into a Python exception.
    # Keep script errors visible when the pipe returns only a numeric value.
    wrapped = ("local ok,result=xpcall(function()\n"
               "-- Execute only the caller's explicit disposable-target script.\n"
               "-- Convert Lua errors into tracebacks through xpcall.\n"
               "-- Preserve their details across the pipe's numeric result protocol.\n" + code + "\nend,debug.traceback)\n")
    wrapped += "if not ok then local f=assert(io.open([[" + (HERE / "ce-error.txt").as_posix() + "]],'w')); f:write(tostring(result)); f:close(); return 999999991 end; return result or 0"
    result = CLIENT.call(wrapped)
    if result == 999999991:
        raise RuntimeError((HERE / "ce-error.txt").read_text())
    return result


def checked_image(pid):
    # Verify the opened PID belongs to the disposable probe executable.
    # Read its full image path through query-only process access.
    # Prevent debugger experiments from switching to a game process.
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel.OpenProcess.restype = W.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = W.BOOL
    kernel.CloseHandle.argtypes = [W.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        raise C.WinError(C.get_last_error())
    try:
        value = C.create_unicode_buffer(32768)
        size = W.DWORD(len(value))
        if not kernel.QueryFullProcessImageNameW(handle, 0, value, C.byref(size)):
            raise C.WinError(C.get_last_error())
        path = Path(value.value)
        if path.resolve() != (HERE / "ce_probe_target.exe").resolve():
            raise RuntimeError("Unexpected target image: " + str(path))
        return path
    finally:
        kernel.CloseHandle(handle)


def main():
    # Exercise breakpoint continuation and cleanup against a disposable native target.
    # Verify identity, original code bytes and eventual normal process exit.
    # Keep debugger research isolated from the released runtime and gameplay tests.
    run_id = str(time.time_ns())
    stdout_path = HERE / ("probe-test-stdout-" + run_id + ".log")
    stderr_path = HERE / ("probe-test-stderr-" + run_id + ".log")
    with stdout_path.open("w") as output, stderr_path.open("w") as errors:
        process = subprocess.Popen([str(HERE / "ce_probe_target.exe"), "60"],
                                   stdout=output, stderr=errors,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        print("Verified target:", process.pid, checked_image(process.pid), flush=True)
        deadline = time.monotonic() + 3
        match = None
        while time.monotonic() < deadline:
            header = stdout_path.read_text()
            match = re.search(r"probe=(0x[0-9a-f]+)", header)
            if match:
                break
            time.sleep(0.05)
        if not match:
            raise RuntimeError("Disposable target failed to report its function address")
        site = int(match.group(1), 16)
        guard = f"assert(getOpenedProcessID()=={process.pid}, 'Wrong disposable target')\n"
        try:
            status = lua("assert(not debug_isDebugging(), 'CE already debugging; no switch permitted')\n"
                         "assert(getSettingsForm().CheckBox1.Checked==false, 'Debugger-detection patching must be off')\n"
                         f"openProcess({process.pid})\n" + guard +
                         "assert(#(debug_getBreakpointList() or {})==0,'Existing breakpoint')\n"
                         "debugProcess(1)\n"
                         "assert(debug_isDebugging() and debug_getCurrentDebuggerInterface()==1,'Wrong debugger')\n"
                         f"_disposableProbeSite={site}\n"
                         "_disposableProbeOriginal=readBytes(_disposableProbeSite,1,false)\n"
                         "assert(_disposableProbeOriginal==0x55,'Unexpected code byte')\nreturn 1")
            print("attach:", status, flush=True)
            for index, limit in enumerate((1, 12, 1), 1):
                if process.poll() is not None:
                    raise RuntimeError("Target exited unexpectedly")
                code = guard + """
assert(debug_isDebugging(), 'Not debugging')
assert(#debug_getBreakpointList()==0, 'Old breakpoint still present')
if _disposableProbeTimer then _disposableProbeTimer.destroy(); _disposableProbeTimer=nil end
_disposableProbe={count=0,main=0,worker=0,done=false,continued=0,continue_errors=0,remove_ok=false,expired=false}
local state=_disposableProbe
local site=_disposableProbeSite
local limit=LIMIT_VALUE
debug_setBreakpoint(site,1,bptExecute,bpmDebugRegister,function()
  -- Count breakpoint hits from both disposable target threads.
  -- Remove the breakpoint at the requested count and continue execution.
  -- Record continuation failures so a stopped target cannot count as success.
  state.count=state.count+1
  if RCX==0 then state.main=state.main+1 elseif RCX==1 then state.worker=state.worker+1 end
  state.last_rip=RIP
  if state.count>=limit and not state.done then
    state.done=true
    local ok,value=pcall(debug_removeBreakpoint,site)
    state.remove_ok=ok
    state.remove_result=tostring(value)
  end
  local ok,value=pcall(debug_continueFromBreakpoint,co_run)
  if ok then state.continued=state.continued+1 else state.continue_errors=state.continue_errors+1;state.error=tostring(value) end
  return 0
end)
assert(#debug_getBreakpointList()==1 or state.done,'Could not arm breakpoint')
assert(readBytes(site,1,false)==_disposableProbeOriginal,'Code byte changed while armed')
_disposableProbeTimer=createTimer(nil,false)
_disposableProbeTimer.Interval=5000
_disposableProbeTimer.OnTimer=function(t)
  -- Retire the disposable breakpoint if the expected hit count never arrives.
  -- Disable this timer and remove the registered breakpoint once.
  -- Mark expiry separately from successful collection for the parent check.
  t.Enabled=false
  if state.done then return end
  state.expired=true
  state.done=true
  pcall(debug_removeBreakpoint,site)
end
_disposableProbeTimer.Enabled=true
return 1
""".replace("LIMIT_VALUE", str(limit))
                print("armed:", index, lua(code), flush=True)
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    if lua(guard + "return _disposableProbe.done and 1 or 0"):
                        break
                    time.sleep(0.1)
                lua(guard + "if _disposableProbeTimer then _disposableProbeTimer.Enabled=false end; return 1")
                # CE marks removed records and reaps them asynchronously.
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if lua(guard + "return #(debug_getBreakpointList() or {})") == 0:
                        break
                    time.sleep(0.1)
                result_path = HERE / f"breakpoint-test-{index}.txt"
                snapshot = guard + """
if _disposableProbeTimer then _disposableProbeTimer.Enabled=false;_disposableProbeTimer.destroy();_disposableProbeTimer=nil end
local state=_disposableProbe
state.breakpoint_count=#debug_getBreakpointList()
state.code_byte=readBytes(_disposableProbeSite,1,false)
state.code_unchanged=state.code_byte==_disposableProbeOriginal
local rows={}
for key,value in pairs(state) do rows[#rows+1]=key..'='..tostring(value) end
table.sort(rows)
local f=assert(io.open([[RESULT_PATH]],'w'));f:write(table.concat(rows,'\\n'));f:close()
return state.done and state.count>=LIMIT_VALUE and state.breakpoint_count==0 and state.code_unchanged and state.continue_errors==0 and not state.expired and 1 or 0
""".replace("RESULT_PATH", result_path.as_posix()).replace("LIMIT_VALUE", str(limit))
                result = lua(snapshot)
                print("result:", index, result_path.read_text(), sep="\n", flush=True)
                if result != 1:
                    raise RuntimeError("Breakpoint test did not pass")
                time.sleep(0.2)
        finally:
            cleanup = guard + """
if _disposableProbeTimer then _disposableProbeTimer.Enabled=false;_disposableProbeTimer.destroy();_disposableProbeTimer=nil end
if _disposableProbeSite and debug_isDebugging() then pcall(debug_removeBreakpoint,_disposableProbeSite) end
if debug_isDebugging() then detachIfPossible() end
assert(not debug_isDebugging(),'Debugger remains attached')
assert(#(debug_getBreakpointList() or {})==0,'Breakpoint remains')
return 1
"""
            print("cleanup:", lua(cleanup), flush=True)
        # Let the disposable target prove it survives detachment and exits normally.
        code = process.wait(timeout=65)
        print("target_exit:", code, flush=True)
        if code != 0:
            raise RuntimeError("Disposable process did not exit cleanly")


if __name__ == "__main__":
    main()
