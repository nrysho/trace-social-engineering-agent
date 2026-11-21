"""Extract teammate bench from a locally fetched ref; never calls an API/model."""
import io, subprocess, tarfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
dest=root/'runs/quality/bench_fixture'
dest.mkdir(parents=True,exist_ok=True)
raw=subprocess.check_output(['git','-c','safe.directory='+root.as_posix(),'archive','origin/neryss/profile-replay','bench'],cwd=root)
with tarfile.open(fileobj=io.BytesIO(raw)) as archive:archive.extractall(dest,filter='data')
print('Bench fixture prepared:',dest)
