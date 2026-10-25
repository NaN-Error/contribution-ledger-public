# Source publication safety

Publish only tracked source and explicitly assembled release assets. Never upload
an existing installation, its personal-data directory, databases, evidence,
credentials, encryption masters, local logs or screenshots of private reports.
Git ignore rules do not protect arbitrary manual ZIP uploads or tracked secrets.

This public repository begins with a source-only history. Historical local
verification outputs and captured repository examples are excluded. Synthetic
developer fixtures are retained. The Windows package is assembled from a checked
source manifest, built assets and pinned runtime components; it contains no user
state. Bundled license/provenance notices are retained.

Before each release run scripts/check_publication.py and scripts/verify_release.py,
scan source/history and every archive for credentials, review findings, and verify
all archive entries. Keep private audit evidence outside Git. If a credential is
exposed, revoke it first. Keep GitHub secret scanning and push protection enabled.
None of these checks certifies all possible sensitive prose or operational safety.
