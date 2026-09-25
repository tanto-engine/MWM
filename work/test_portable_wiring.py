import importlib.util,json,os,pathlib,sys,tempfile,types
root=pathlib.Path.cwd()
package=root/'outputs'/'okatsu-prototype'
sys.path.insert(0,str(package))
import play_okatsu
with tempfile.TemporaryDirectory(dir=root/'work',prefix='portable-build-') as folder:
    play_okatsu.HERE=pathlib.Path(folder)
    play_okatsu.native_code_hash=lambda:'stable'
    requests=[]
    def run(args,**kwargs):
        requests.append(args)
        if len(requests)==1:
            (play_okatsu.HERE/'boss-session.json').write_text(json.dumps({'config_tag':'0000000000000000'}))
            return types.SimpleNamespace(returncode=0,stdout='',stderr='')
        return types.SimpleNamespace(returncode=1,stdout='',stderr='intentional mocked build stop')
    play_okatsu.subprocess.run=run
    custom=root/'work'/'MinHook path with spaces'
    assert play_okatsu.main(['--minhook',str(custom)])==1
    assert requests[1][-2:]==['-MinHook',str(custom.resolve())]
os.environ['NIOH_EXE']=str(root/'work'/'Alternate Steam Library'/'nioh.exe')
import native_loader
assert native_loader.NIOH==pathlib.Path(os.environ['NIOH_EXE'])
assert native_loader.NIOH_HASH=='0c3508c6b4d0696d84423949df9faccb3f9c6d93833854e1e17a78d66defc389'
print('Portability wiring checks passed: custom MinHook path and NIOH_EXE override; no process actions')
