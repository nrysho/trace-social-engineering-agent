"""Extract teammate bench from a locally fetched ref; never calls an API/model."""
import io, subprocess, tarfile, sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
if (root/'bench/server.py').exists():
    print('Using the bench already merged in the repository');sys.exit(0)
dest=root/'runs/quality/bench_fixture'
dest.mkdir(parents=True,exist_ok=True)
raw=subprocess.check_output(['git','-c','safe.directory='+root.as_posix(),'archive','origin/neryss/profile-replay','bench'],cwd=root)
with tarfile.open(fileobj=io.BytesIO(raw)) as archive:archive.extractall(dest,filter='data')
print('Bench fixture prepared:',dest)
