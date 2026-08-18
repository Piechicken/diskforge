# External implementation sources

## El Torito ISO authoring

DiskForge uses the documented `pycdlib.PyCdlib.add_eltorito` API after adding the selected boot file to the new ISO. The API requires the boot file to already exist in the ISO and documents the supported media names (`noemul`, `floppy`, `hdemul`), platform IDs (including x86 and UEFI), optional boot information tables, and load segment.

- Installed package source inspected locally: `/usr/local/lib/python3.12/dist-packages/pycdlib/pycdlib.py`, `add_eltorito` lines 5499–5533.
- Project source: https://github.com/clalancette/pycdlib

## GitHub Actions runtime maintenance

Official action documentation identifies Node.js-24-compatible release lines used by the project workflow. Current sources consulted:

- https://github.com/actions/checkout
- https://github.com/actions/setup-python
- https://github.com/actions/upload-artifact
- https://github.com/actions/download-artifact

The workflow uses current hosted-runner action majors to avoid deprecated Node.js 20 action-runtime diagnostics while preserving internal artifact aggregation.
