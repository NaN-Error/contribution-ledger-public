"""Private Docker-volume transport. No extraction through tar.extractall.

Runs only in a short-lived operator container with --network none. Original
filenames are storage identifiers, never paths from an HTTP upload.
"""
import argparse
import os
from pathlib import Path
import stat
import sys
import tarfile
from app.operations.archive import safe_name,BundleError,MAX_TOTAL,MAX_FILES
from app.security.secrets.encrypted import private_path

def export_volume(root:Path,stream):
    private_path(root);total=0;count=0
    with tarfile.open(fileobj=stream,mode="w|") as archive:
        for path in sorted(root.rglob("*")):
            private_path(path)
            info=path.lstat()
            if stat.S_ISDIR(info.st_mode):continue
            if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:raise BundleError("Volume contains an unsafe file")
            total+=info.st_size;count+=1
            if total>MAX_TOTAL or count>MAX_FILES:raise BundleError("Volume exceeds recovery bound")
            name=safe_name(path.relative_to(root).as_posix())
            item=tarfile.TarInfo(name);item.size=info.st_size;item.mode=0o600
            with path.open("rb") as src:archive.addfile(item,src)

def import_volume(root:Path,stream):
    private_path(root)
    if not root.is_dir() or any(root.iterdir()):raise BundleError("Only a new empty volume can be restored")
    total=0;names=set()
    with tarfile.open(fileobj=stream,mode="r|") as archive:
        for item in archive:
            name=safe_name(item.name)
            if not item.isreg() or name in names or item.size<0:raise BundleError("Unsafe or duplicate volume member")
            names.add(name);total+=item.size
            if total>MAX_TOTAL or len(names)>MAX_FILES:raise BundleError("Volume exceeds recovery bound")
            target=root/name;private_path(target);target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            source=archive.extractfile(item)
            fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
            count=0
            with os.fdopen(fd,"wb") as dst:
                while raw:=source.read(1024*1024):
                    count+=len(raw)
                    if count>item.size:raise BundleError("Invalid volume member size")
                    dst.write(raw)
            if count!=item.size:raise BundleError("Truncated volume member")

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("action",choices=["export","import"]);p.add_argument("root",type=Path);a=p.parse_args()
    try:
        if a.action=="export":export_volume(a.root,sys.stdout.buffer)
        else:
            import_volume(a.root,sys.stdin.buffer)
            if os.geteuid()==0:
                for path in [a.root,*a.root.rglob("*")]:
                    # The transport helper drops CAP_FOWNER. Set permissions
                    # while it still owns each path, then transfer ownership.
                    os.chmod(path,0o700 if path.is_dir() else 0o600)
                    os.chown(path,10001,10001)
    except Exception:
        print("Private volume operation failed; no source values are logged.",file=sys.stderr);return 2
    return 0
if __name__=="__main__":raise SystemExit(main())
