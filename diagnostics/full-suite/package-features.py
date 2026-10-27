#!/usr/bin/env python3
"""Package the unchanged feature workload with the SDK built from the server ref."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

source, build = map(Path, sys.argv[1:])
release = build / 'feature-package'
shutil.copytree('apps/channels-workflows', release)
sdk = release / 'node_modules/tako.sh'
sdk.mkdir(parents=True)
shutil.copytree(source / 'sdk/javascript/dist', sdk / 'dist')
shutil.copy(source / 'sdk/javascript/package.json', sdk / 'package.json')
# Copy the runtime dependencies resolved by the source checkout's frozen lock.
# No registry lookup or install occurs during timed tests.
copied = {}
def copy_dependency(name, parent):
    origin = next((p / 'node_modules' / name for p in [parent, *parent.parents]
                   if (p / 'node_modules' / name / 'package.json').exists()), None)
    if origin is None:
        raise RuntimeError(f'missing installed SDK dependency: {name}')
    origin = origin.resolve()
    info = json.loads((origin / 'package.json').read_text())
    if name in copied:
        if copied[name] != info['version']:
            raise RuntimeError(f'conflicting flattened runtime versions: {name}')
        return
    copied[name] = info['version']
    shutil.copytree(origin, release / 'node_modules' / name, ignore=shutil.ignore_patterns('node_modules'))
    for dependency in info.get('dependencies', {}):
        copy_dependency(dependency, origin)

for dependency in json.loads((sdk / 'package.json').read_text()).get('dependencies', {}):
    copy_dependency(dependency, source / 'sdk/javascript')
(release / 'runtime-dependencies.json').write_text(json.dumps(copied, indent=2) + '\n')
package = json.loads((release / 'package.json').read_text())
package['dependencies']['tako.sh'] = 'file:node_modules/tako.sh'
(release / 'package.json').write_text(json.dumps(package, indent=2) + '\n')
subprocess.run(['tar', '-cf', str(build / 'features.tar'), '-C', str(release), '.'], check=True)
