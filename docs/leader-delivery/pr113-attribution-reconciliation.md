# PR #113 attribution reconciliation

The [source lock](leader-delivery-source-lock.md), [member provenance ledger](leader-delivery-member-provenance.csv),
[member PR traceability](leader-delivery-member-pr-traceability.md) and
[earlier attribution record](phase8-2-attribution-repin.md) describe the
original Leader delivery at `0a0b99b4269d4e25597ab524d946e224c64ace08`.
Their original SHAs identify the sources and the historical delivery snapshot.

## Delivered ancestry

Member C PR #69 supplied original head `361e73246a3a6746a39a7e2769dffdfb7b1ce486`.
The Leader delivery includes its equivalent reconstruction
`6026b8a4140bea2db541fdd0c978261295748313` as the second parent of the
reconstructed C integration merge. The original #69 head is a source
reference. The original C PRs and branches, including #60, #61 and #69,
remain the authoritative records of the contributor's submitted history.
For Member C, read the earlier `INCLUDED_VIA_ANCESTRY` rows as inclusion
through the reconstructed C lineage. A #94, A #95, B #102 and D #90
retain their exact original HEADs in the Leader ancestry.

The [commit mapping](pr113-reconstructed-commits.csv) records all 42
reconstructed commits, with original and delivered SHAs, ordered parents,
tree IDs and delivered subjects. Every mapped commit preserves its tree
and timestamps. Consequently each parent-to-child change, including
each side of a merge, is identical in content. The C head tree is identical
and the Leader includes only one C lineage. Member author and committer
identities are preserved. Four Leader merge identities use the verified
leader account, and three C commits retain their human identities with
the tool attribution removed. The necessary C merge subject changes
retain the original branch references in the commit bodies.

The reconstructed metadata-only Leader head
`48c09106c1bdf167d3af0426d487005a04cc95c8` has the same tree as
the original delivery. The later [checksum reconciliation](pr113-checksum-reconciliation.md)
records the six expected-hash corrections applied to that tree.
