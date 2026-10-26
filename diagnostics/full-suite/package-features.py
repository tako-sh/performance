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
# tsdown bundles runtime dependencies; these entrypoints do not import the
# optional React/Vite peers. No registry lookup or install occurs during tests.
package = json.loads((release / 'package.json').read_text())
package['dependencies']['tako.sh'] = 'file:node_modules/tako.sh'
(release / 'package.json').write_text(json.dumps(package, indent=2) + '\n')
subprocess.run(['tar', '-cf', str(build / 'features.tar'), '-C', str(release), '.'], check=True)
