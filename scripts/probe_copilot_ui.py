"""Inspect a pinned public, signed-out Copilot build on a disposable Mac runner.

Only control labels and signature metadata are reported. Never run this against
a user's installed app or give the probe an existing HOME.
"""
import argparse
import ctypes
import json
import os
import plistlib
import subprocess
import tempfile
import time
from pathlib import Path


class Accessibility:
    def __init__(self):
        self.ax = ctypes.CDLL('/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices')
        self.cf = ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        pointer, integer = ctypes.c_void_p, ctypes.c_long
        functions = {
            'CFStringCreateWithCString': (pointer, [pointer, ctypes.c_char_p, ctypes.c_uint32]),
            'CFStringGetCString': (ctypes.c_bool, [pointer, pointer, integer, ctypes.c_uint32]),
            'CFGetTypeID': (ctypes.c_ulong, [pointer]), 'CFStringGetTypeID': (ctypes.c_ulong, []),
            'CFArrayGetTypeID': (ctypes.c_ulong, []), 'CFArrayGetCount': (integer, [pointer]),
            'CFArrayGetValueAtIndex': (pointer, [pointer, integer]), 'CFRelease': (None, [pointer]),
        }
        for name, (result, args) in functions.items():
            function=getattr(self.cf,name);function.restype=result;function.argtypes=args
        self.ax.AXIsProcessTrusted.restype=ctypes.c_bool
        self.ax.AXUIElementCreateApplication.restype=pointer
        self.ax.AXUIElementCreateApplication.argtypes=[ctypes.c_int]
        self.ax.AXUIElementCopyAttributeValue.argtypes=[pointer,pointer,ctypes.POINTER(pointer)]
        self.ax.AXUIElementPerformAction.argtypes=[pointer,pointer]
        self.ax.AXUIElementSetMessagingTimeout.argtypes=[pointer,ctypes.c_float]
        self.cf.CFEqual.argtypes=[pointer,pointer];self.cf.CFEqual.restype=ctypes.c_bool
        self.owned=[]

    def string(self,text):
        value=self.cf.CFStringCreateWithCString(None,text.encode(),0x08000100)
        self.owned.append(value);return value

    def attribute(self,element,name):
        value=ctypes.c_void_p()
        if self.ax.AXUIElementCopyAttributeValue(element,self.string(name),ctypes.byref(value)):
            return None
        self.owned.append(value.value);return value.value

    def text(self,value):
        if not value or self.cf.CFGetTypeID(value)!=self.cf.CFStringGetTypeID():return ''
        buffer=ctypes.create_string_buffer(1024)
        return buffer.value.decode('utf-8',errors='replace') if self.cf.CFStringGetCString(value,buffer,1024,0x08000100) else ''

    def children(self,element,name='AXChildren'):
        value=self.attribute(element,name)
        if not value or self.cf.CFGetTypeID(value)!=self.cf.CFArrayGetTypeID():return []
        return [self.cf.CFArrayGetValueAtIndex(value,i) for i in range(min(100,self.cf.CFArrayGetCount(value)))]

    def walk(self,element,depth=0):
        if depth>14:return
        yield element, self.text(self.attribute(element,'AXRole')), self.text(self.attribute(element,'AXTitle'))
        for child in self.children(element):yield from self.walk(child,depth+1)

    def close(self):
        for value in reversed(self.owned):
            if value:self.cf.CFRelease(value)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--app',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
    assert os.environ.get('GITHUB_ACTIONS')=='true', 'Disposable CI only'
    with (args.app/'Contents/Info.plist').open('rb') as f:info=plistlib.load(f)
    assert info['CFBundleIdentifier']=='com.github.githubapp'
    result={'version':info['CFBundleShortVersionString'],'controlLabels':[],'modelRequests':0}
    signed=subprocess.run(['/usr/bin/codesign','-dv','--verbose=2',str(args.app)],capture_output=True,text=True,check=True)
    result['team']=[line.partition('=')[2] for line in signed.stderr.splitlines() if line.startswith('TeamIdentifier=')]
    with tempfile.TemporaryDirectory(prefix='copilot-public-ui-') as temporary:
        home=Path(temporary);(home/'.copilot').mkdir()
        env={**os.environ,'HOME':str(home),'CODEX_HOME':str(home/'.codex')}
        # Prevent the application inheriting any CI authentication variables.
        for key in list(env):
            if any(word in key.upper() for word in ('TOKEN','SECRET','PASSWORD')):env.pop(key)
        process=subprocess.Popen([str(args.app/'Contents/MacOS'/info['CFBundleExecutable'])],env=env,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        from AppKit import NSRunningApplication
        try:
            time.sleep(12)
            ax=Accessibility()
            try:
                result['accessibilityTrusted']=bool(ax.ax.AXIsProcessTrusted())
                app=ax.ax.AXUIElementCreateApplication(process.pid);ax.owned.append(app)
                ax.ax.AXUIElementSetMessagingTimeout(app,.5)
                # Signed-out test app only: verify an actual document replacement,
                # not merely that posting an event returned successfully.
                quartz=ctypes.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
                quartz.CGEventCreateKeyboardEvent.argtypes=[ctypes.c_void_p,ctypes.c_ushort,ctypes.c_bool]
                quartz.CGEventCreateKeyboardEvent.restype=ctypes.c_void_p
                quartz.CGEventSetFlags.argtypes=[ctypes.c_void_p,ctypes.c_uint64]
                quartz.CGEventPostToPid.argtypes=[ctypes.c_int,ctypes.c_void_p]
                result['reloadShortcuts']={}
                for label,key,flags in [('command-r',15,1<<20),('command-shift-r',15,(1<<20)|(1<<17)),('f5',96,0)]:
                    areas=[element for element,role,_ in ax.walk(app) if role=='AXWebArea']
                    before=areas[0] if len(areas)==1 else None
                    for down in (True,False):
                        event=quartz.CGEventCreateKeyboardEvent(None,key,down)
                        quartz.CGEventSetFlags(event,flags);quartz.CGEventPostToPid(process.pid,event);ax.cf.CFRelease(event)
                    replaced=False
                    deadline=time.monotonic()+4
                    while before and time.monotonic()<deadline:
                        after=[element for element,role,_ in ax.walk(app) if role=='AXWebArea']
                        if len(after)==1 and not ax.cf.CFEqual(before,after[0]):replaced=True;break
                        time.sleep(.2)
                    result['reloadShortcuts'][label]={'documentReplaced':replaced,'initialWebAreas':len(areas)}
                menu=ax.attribute(app,'AXMenuBar')
                if menu:
                    controls=list(ax.walk(menu))
                    result['controlLabels']=[{'role':role,'title':title} for _,role,title in controls if title]
                    for element,role,title in controls:
                        if role=='AXMenuItem' and title.lower().rstrip('….') in {'healthcheck','health check','run health check'}:
                            result['healthcheckOpened']=ax.ax.AXUIElementPerformAction(element,ax.string('AXPress'))==0
                            time.sleep(2)
                            result['healthcheckControls']=[{'role':role,'title':title,'description':ax.text(ax.attribute(element,'AXDescription'))}
                                for element,role,title in ax.walk(app) if role in {'AXButton','AXMenuItem'}]
                            break
            finally:ax.close()
        finally:
            application=NSRunningApplication.runningApplicationWithProcessIdentifier_(process.pid)
            if application:application.terminate()
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:result['cooperativeExitPending']=True
    args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
