"""Reviewed source-only release bundles; deterministic on the tested build runtime.

No deployment, database migration/cutover, secrets or learned model files.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path,PurePosixPath
import stat
import subprocess
import zipfile

MAX_FILES=5000;MAX_FILE=16*1024*1024;MAX_TOTAL=64*1024*1024
EXTENSIONS={'.py','.js','.cjs','.html','.css','.json','.md','.txt','.command','.ps1','.cpp','.h','.ino','.ini','.svg','.csv','.png','.jpg','.jpeg','.webp','.yml','.yaml'}


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
def sha(data):return hashlib.sha256(data).hexdigest()


def build(project):
    root=Path(project).resolve()
    dirty=subprocess.check_output(['git','-C',str(root),'status','--porcelain','--untracked-files=no'],text=True)
    if dirty.strip():raise ValueError('Commit and review tracked changes before building a release')
    commit=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
    prefix=subprocess.check_output(['git','-C',str(root),'rev-parse','--show-prefix'],text=True).strip()
    repository=subprocess.check_output(['git','-C',str(root),'rev-parse','--show-toplevel'],text=True).strip()
    command=['git','-C',repository,'ls-tree','-r','-z',commit]
    if prefix:command+=['--',prefix.rstrip('/')]
    objects=[]
    for entry in subprocess.check_output(command).split(b'\0'):
        if not entry:continue
        metadata,full_name=entry.decode('utf-8').split('\t',1)
        mode,kind,identity=metadata.split()
        if prefix and not full_name.startswith(prefix):raise ValueError('Unexpected Git subtree')
        name=full_name[len(prefix):]
        relative=PurePosixPath(name)
        template=relative.name in ('.gitignore','.gitattributes','.env.example') or relative.name.endswith('.env.example')
        if (relative.is_absolute() or '..' in relative.parts or any(part.startswith('.') and part not in ('.gitignore','.gitattributes','.env.example') for part in relative.parts)
            or (relative.suffix.lower() not in EXTENSIONS and not template)):continue
        if any(part in ('node_modules','__pycache__') for part in relative.parts):continue
        if relative.suffix=='.txt' and not (relative.name.startswith('requirements') or relative.name in ('CMakeLists.txt',)):continue
        if kind!='blob' or mode not in ('100644','100755'):raise ValueError('Linked or nonregular tracked release source')
        objects.append((name,identity))
    if len(objects)>MAX_FILES:raise ValueError('Release file count exceeds bound')
    request=''.join(identity+'\n' for _,identity in objects).encode('ascii')
    check=subprocess.check_output(['git','-C',repository,'cat-file','--batch-check'],input=request).decode('ascii').splitlines()
    sizes=[]
    for (name,identity),line in zip(objects,check):
        reported,kind,size=line.split()
        if reported!=identity or kind!='blob' or not 0<=int(size)<=MAX_FILE:raise ValueError('Release object exceeds bounds')
        sizes.append(int(size))
    if len(sizes)!=len(objects) or sum(sizes)>MAX_TOTAL:raise ValueError('Release payload exceeds bounds')
    records=io.BytesIO(subprocess.check_output(['git','-C',repository,'cat-file','--batch'],input=request))
    files={}
    for (name,identity),size in zip(objects,sizes):
        header=records.readline(200).decode('ascii').strip().split()
        if header!=[identity,'blob',str(size)]:raise ValueError('Release object header differs')
        data=records.read(size)
        if len(data)!=size or records.read(1)!=b'\n':raise ValueError('Incomplete Git object')
        files['project/'+name]=data
    if not files:raise ValueError('No reviewed source files')
    manifest=dict(format='edgeops-reviewed-source-release-v1',source_commit=commit,
        production_ready=False,deployment_performed=False,database_included=False,credentials_included=False,
        payload_byte_basis='Git blobs of the recorded commit; checkout line endings do not affect payload bytes',
        scope='Tracked visible source and static assets only; private/hidden files and binary archives excluded',
        files={name:dict(bytes=len(data),sha256=sha(data)) for name,data in files.items()})
    files['manifest.json']=(canonical(manifest)+'\n').encode()
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,data in sorted(files.items()):
            entry=zipfile.ZipInfo(name,(1980,1,1,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED;entry.external_attr=(stat.S_IFREG|0o600)<<16
            archive.writestr(entry,data,compresslevel=9)
    return output.getvalue(),manifest


def verify(raw):
    if len(raw)>MAX_TOTAL+2*1024*1024:raise ValueError('Release archive outside bounds')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries=archive.infolist();names=[entry.filename for entry in entries]
        if len(entries)>MAX_FILES+1 or len(names)!=len(set(n.casefold() for n in names)):raise ValueError('Release inventory invalid')
        if sum(entry.file_size for entry in entries)>MAX_TOTAL+2*1024*1024:raise ValueError('Expanded release exceeds bounds')
        if 'manifest.json' not in names or archive.getinfo('manifest.json').file_size>2*1024*1024:raise ValueError('Manifest unavailable')
        manifest=json.loads(archive.read('manifest.json'))
        if manifest.get('format')!='edgeops-reviewed-source-release-v1' or any(manifest.get(k) is not False for k in ('production_ready','deployment_performed','database_included','credentials_included')):raise ValueError('Unsupported release labels')
        if set(names)!=set(manifest['files'])|{'manifest.json'}:raise ValueError('Manifest membership mismatch')
        reserved={'con','prn','aux','nul'}|{'com'+str(i) for i in range(1,10)}|{'lpt'+str(i) for i in range(1,10)}
        for entry in entries:
            name=PurePosixPath(entry.filename);mode=entry.external_attr>>16
            if (name.is_absolute() or '..' in name.parts or name.as_posix()!=entry.filename or '\\' in entry.filename or ':' in entry.filename
                or any(part.endswith((' ','.')) or part.split('.')[0].casefold() in reserved for part in name.parts)
                or stat.S_IFMT(mode) not in (0,stat.S_IFREG) or entry.is_dir() or entry.flag_bits&1
                or entry.compress_type!=zipfile.ZIP_DEFLATED):raise ValueError('Unsafe release member')
            if entry.filename=='manifest.json':continue
            if not entry.filename.startswith('project/') or entry.file_size>MAX_FILE:raise ValueError('Release source outside scope')
            data=archive.read(entry);meta=manifest['files'][entry.filename]
            if type(meta['bytes']) is not int or len(data)!=meta['bytes'] or sha(data)!=meta['sha256']:raise ValueError('Release content hash mismatch')
    return manifest


def unpack(raw,output):
    manifest=verify(raw);destination=Path(output).absolute();destination.mkdir(mode=0o700,exist_ok=False)
    marker=destination/'INSTALL_INCOMPLETE';marker.write_text('Source unpack incomplete; do not launch.\n',encoding='utf-8')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for name in sorted(manifest['files']):
            target=destination/name;target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            descriptor=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(descriptor,'wb') as stream:stream.write(archive.read(name));stream.flush();os.fsync(stream.fileno())
    (destination/'release-manifest.json').write_text(canonical(manifest)+'\n',encoding='utf-8');marker.unlink()
    return dict(output=str(destination/'project'),source_commit=manifest['source_commit'],deployment_performed=False,
                dependencies_installed=False,database_migrated=False,production_ready=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['build','verify','unpack'])
    parser.add_argument('--project',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--source',type=Path);parser.add_argument('--output',type=Path);args=parser.parse_args()
    try:
        if args.action=='build':
            if not args.output:parser.error('build requires a new --output file')
            raw,manifest=build(args.project);verify(raw)
            descriptor=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(descriptor,'wb') as stream:stream.write(raw)
            result=dict(source_commit=manifest['source_commit'],archive_sha256=sha(raw),production_ready=False)
        else:
            if not args.source or args.source.stat().st_size>MAX_TOTAL+2*1024*1024:parser.error('Use a bounded --source archive')
            raw=args.source.read_bytes()
            if args.action=='unpack':
                if not args.output:parser.error('unpack requires a new output directory')
                result=unpack(raw,args.output)
            else:result=verify(raw)
        print(canonical(result))
    except Exception:raise SystemExit('Release operation refused. Check reviewed source, file integrity and a new destination. No live checkout or database overwritten.')


if __name__=='__main__':main()
