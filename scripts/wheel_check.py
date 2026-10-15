"""Install a local wheel in a fresh environment outside the checkout and test native I/O."""

import argparse
import glob
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument("wheel", help="local wheel path or glob; exactly one wheel must match")
args = parser.parse_args()
wheels = glob.glob(args.wheel)
if len(wheels) != 1:
    parser.error("exactly one local wheel must match")
wheel = Path(wheels[0]).resolve()
uv = shutil.which("uv")
if uv is None:
    parser.error("uv >=0.9.13 is required")
project = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="ofi-wheel-check-") as directory:
    root = Path(directory)
    environment = root / "environment"
    executable = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env.pop("VIRTUAL_ENV", None)
    env["UV_PROJECT_ENVIRONMENT"] = str(environment)
    subprocess.run(
        [uv, "sync", "--project", str(project), "--locked", "--extra", "research",
         "--no-install-project", "--python", sys.executable],
        check=True,
        cwd=root,
        env=env,
    )
    env["VIRTUAL_ENV"] = str(environment)
    subprocess.run(
        [uv, "pip", "install", "--python", str(executable), "--no-deps", str(wheel)],
        check=True,
        cwd=root,
        env=env,
    )
    code = r"""
import importlib.machinery
import json
from pathlib import Path
import subprocess
import sys
import pyarrow.parquet as pq
from ofi_pipeline import PipelineConfig, run_pipeline, _native, MissingInputError
root=Path.cwd(); sample=root/"sample"; (sample/"data").mkdir(parents=True);(sample/"reports").mkdir()
quality="symbol,event_id,timestamp,time_ns,quote_accepted,reject_reason\n"
events="symbol,date,event_id,timestamp,time_ns,segment_id,prev_state_available,is_quote_update,bid_price_1,ask_price_1,bid_size_1,ask_size_1,event_type,event_size,event_price,direction\n"
for i,second,size,update in [(0,1,100,True),(1,10,100,False),(2,11,130,True),(3,20,130,False)]:
    stamp=f"2012-06-21T13:30:{second:02}Z"; ns=34200000000000+second*10**9
    quality+=f"A,{i},{stamp},{ns},True,\n"
    kind=4 if i==3 else 1; event_size=7 if i==3 else 1; price=1.01 if i==3 else 1; direction=-1 if i==3 else 1
    events+=f"A,2012-06-21,{i},{stamp},{ns},1,{i>0},{update},1,1.01,{size},120,{kind},{event_size},{price},{direction}\n"
(sample/"data/events_clean.csv.gz").write_bytes(__import__("gzip").compress(events.encode()))
trades="symbol,date,event_id,timestamp,time_ns,event_type,event_size,event_price,direction,quote_accepted\nA,2012-06-21,3,2012-06-21T13:30:20Z,34220000000000,4,7,1.01,-1,True\n"
(sample/"data/trades_clean.csv.gz").write_bytes(__import__("gzip").compress(trades.encode()))
# Explicit quality CSV exercises layout independence in the isolated installation.
q=sample/"reports/event_quality.csv";q.write_text(quality)
from ofi_pipeline import InputPaths
inputs=InputPaths(sample/"data/events_clean.csv.gz",sample/"data/trades_clean.csv.gz",q)
c=PipelineConfig(levels=1,threads=1,session_close="09:30:30",chunk_rows=1)
r=run_pipeline(output_dir=root/"out",inputs=inputs,config=c)
t=pq.read_table(r.features_path)
assert r.feature_rows==2 and t["ofi_l1"].to_pylist()==[30,0]
assert t["volume"].to_pylist()==[7,0] and t["trade_imbalance"].to_pylist()==[7,0]
assert t["avg_depth"].to_pylist()==[125.0,125.0]
from ofi_pipeline.research import load_features, lag_feature
features=load_features(r.features_path)
assert features["ofi_l1"].to_list()==[30,0]
lagged=lag_feature(features,"ofi_l1",bucket_seconds=10)
assert lagged["ofi_l1_lag1"].isna().iloc[0] and lagged["ofi_l1_lag1"].iloc[1]==30
assert pq.read_table(r.bucket_quality_path)["accepted"].to_pylist()==[False,True,True]
assert json.loads(r.manifest_path.read_text())["producer"]=="ofi-pipeline"
assert any(_native.__file__.endswith(s) for s in importlib.machinery.EXTENSION_SUFFIXES)
assert Path(_native.__file__).is_relative_to(Path(sys.prefix))
package=Path(_native.__file__).parent
assert (package/"py.typed").exists() and "run_pipeline" in (package/"_native.pyi").read_text()
cli=subprocess.run([sys.executable,"-m","ofi_pipeline","--events",str(inputs.events),"--trades",str(inputs.trades),"--quality",str(q),"--output-dir",str(root/"cli"),"--levels","1","--session-close","09:30:30"],check=True,capture_output=True,text=True)
assert json.loads(cli.stdout)["partitions"][0]["feature_rows"]==2
try:
    run_pipeline(root/"missing",root/"missing-output",c)
except MissingInputError:
    pass
else:
    raise AssertionError("missing-input error was not mapped")
print(json.dumps({"status":"passed","loaded_extension":_native.__file__,"python":sys.version,"accepted_rows":r.feature_rows}))
"""
    script = root / "smoke.py"
    script.write_text(code)
    subprocess.run([str(executable), str(script)], check=True, cwd=root, env=env)
print(json.dumps({"wheel": str(wheel), "isolated_install": "passed"}))
