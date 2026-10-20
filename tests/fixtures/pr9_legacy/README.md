# Public historical acceptance test sources

These 196 text files are byte-for-byte Python test/driver inputs from the retained
A3.2 independent source/wheel review trees. They contain test code, not historical
execution results, private archives, keys, database contents or credentials.
`provenance.json` binds every file to its repository-relative historical location
and original SHA-256, and retains the twenty original command argument lists for
each installation mode. The original historical acceptance registry is unchanged.

The `.py.txt` suffix keeps these old inputs out of ordinary pytest discovery and
current-source linting. `tools/pr9_deploy_inputs.py` restores them into a new
private execution directory, verifies every original SHA before restoration, and
records original/executed bytes and AST hashes plus every explicit compatibility
replacement. Physical paths are mapped to the actual current installation and
private output. The historical environment observer still verifies the immutable
original fourteen migrations and sixteen standalone SQL files, and verifies the
exact complete current migration registry (eighteen at preparation time).
`historical-migrations.json` retains only the old public file hashes and their
source hash; it contains no private fields from the historical gate document.

Each original pytest group is rerun in the real isolated source/wheel installation
and retains its actual node identities. Native script commands run inside an
actual pytest subprocess wrapper so their JUnit represents real command execution
and checked native exit, rather than fabricated status XML. All original expected
nodes must be present and the XML must contain no failures, errors or skips.
The old current-PG group uses its original exact file inventory to avoid recursively
calling the newer A33 deployment tests. The outer complete current integration
suite remains separate and unshortened.

Publication screening: no PEM private-key block, credential-bearing PostgreSQL URL,
or GitHub token pattern was found in these source-only files. Runtime-generated
test secrets and raw output belong only in mode-0700 controller evidence, never in
this fixture directory or a public artifact upload. This screening is not a claim
that the historical native data archives are safe to publish.

`trusted-capacity-members.json` is source-binding metadata only: the exact original
110 role/SHA pairs and historical binding SHA. It authorizes no upload of the
private raw capacity archive. The bridge validates all original bytes and rejects
symlink/permission/path changes before mounting only the fixed private prefix.
