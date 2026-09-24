"""Bounded M1c.2 engineering evidence; no official simulation cells or downloads."""
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from uc_core.h1 import analyze_h1
from uc_core.surrogate import csd_test
from uc_core.constants import analysis_rng


def serial(value):
    if is_dataclass(value):
        return serial(asdict(value))
    if isinstance(value,dict):
        return {k:serial(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):
        return [serial(v) for v in value]
    return value


def main():
    seed=1927140
    values=np.random.Generator(np.random.PCG64(seed)).uniform(1,3,size=140)
    for onset in (48,60,100):
        values[onset:onset+2]=[-1,-.6]
    started=time.perf_counter()
    outputs=analyze_h1(values,B=12,interval_B=1000)
    reference=csd_test(values,B=12,rng=analysis_rng('primary'))
    joint=outputs['joint']
    same=(joint.primary.attempts==reference.attempts and joint.primary.p_value==reference.p_value
          and joint.rng_after==reference.rng_after)
    metrics=[joint.primary,joint.trend,joint.lag1]+[outputs[n] for n in ('window32','window48','fixed','wild')]
    no_failures=all(not isinstance(r,dict) and r.failed==0 for r in metrics)
    elapsed=time.perf_counter()-started
    tests=subprocess.run([sys.executable,'-m','pytest','-q'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    files=['src/uc_core/'+n+'.py' for n in ('ar','rolling','recession','surrogate','secondary','h1','constants','validation_design')]
    files+=['tests/test_secondary.py','tests/test_h1.py','tests/test_validation_design.py',
            'docs/M1C2_SECONDARY_CONTRACT.md','prereg/H1.md','tools/verify_m1c2.py',
            'requirements.lock','.github/workflows/research-tests.yml']
    result={'milestone':'M1c.2 local engineering and protocol draft',
            'verified_at_utc':datetime.now(timezone.utc).isoformat(),
            'passed':same and no_failures and tests.returncode==0,
            'scope':'Development-only synthetic fixtures. G0/G1 and full M1 closure require external evidence and declarations.',
            'fixture':{'seed':seed,'length':140,'rng':'PCG64','input_sha256':hashlib.sha256(values.astype('<f8').tobytes()).hexdigest(),
                       'surrogate_attempts_per_mode':12,'episode_resamples':1000},
            'primary_reference_identical':same,'no_numerical_failures':no_failures,'seconds':elapsed,
            'outputs':serial(outputs),
            'pytest':{'returncode':tests.returncode,'stdout':tests.stdout,'stderr':tests.stderr},
            'file_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files}}
    (ROOT/'audit/m1c2_verification.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
    print('M1c.2 local verification:', 'PASS' if result['passed'] else 'FAIL')
    print(tests.stdout.strip())
    print('Primary equals reference:',same,'; numerical failures:',not no_failures)
    return 0 if result['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
