# Coming Soon

This directory will contain project resources.

Run `PYTHONPATH=src python3 examples/import_export_qubo.py` for the small
import-export QUBO example. It enumerates this five-bit example to verify the
formulation; it is not a general-purpose solver.

Install optional Qulacs support with `python3 -m pip install -r
requirements-quantum.txt`, then run `PYTHONPATH=src python3
examples/qulacs_qaoa.py` for a seeded QAOA simulator run and exact classical
reference on the same synthetic five-variable QUBO. The example executes a
local classical state-vector simulation; it does not use quantum hardware.
